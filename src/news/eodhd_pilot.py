from __future__ import annotations

import json
import subprocess
import time
from collections import Counter, deque
from datetime import date, timedelta
from pathlib import Path
from statistics import median

from .common import config_fingerprint, digest, file_sha256, now_utc, write_bytes, write_csv, write_json
from .deduplicate import ArticleDeduplicator
from .eodhd_config import EodhdPilotConfig
from .event_cluster import EventClusterer
from .normalize import EodhdNormalizer
from .providers import AuthenticationError, EodhdProvider, NewsProvider, ProviderError
from .quality import ContentQualityClassifier
from .risk_filter import RiskFamilyFilter
from .schemas import NormalizedArticle, PageRequest, ProviderPage, QueryWindow


class WindowLimitError(RuntimeError):
    pass


def monthly_windows(company: str, ticker: str, start: date, end: date) -> list[QueryWindow]:
    if start > end:
        raise ValueError("from date must not be after to date")
    windows = []
    cursor = start
    while cursor <= end:
        next_month = date(cursor.year + (cursor.month == 12), 1 if cursor.month == 12 else cursor.month + 1, 1)
        window_end = min(end, next_month - timedelta(days=1))
        windows.append(QueryWindow(company, ticker, cursor, window_end))
        cursor = window_end + timedelta(days=1)
    return windows


class EodhdPilot:
    def __init__(
        self,
        config: EodhdPilotConfig,
        *,
        repository: Path,
        provider: NewsProvider | None = None,
        derived_namespace: str | None = None,
    ):
        self.config = config
        self.repository = repository.resolve()
        self.raw_root = self.repository / config["paths"]["raw"]
        self.normalized_root = self.repository / config["paths"]["normalized"]
        self.derived_root = self.repository / config["paths"]["derived"]
        if derived_namespace:
            if Path(derived_namespace).name != derived_namespace:
                raise ValueError("derived_namespace must be a single path component")
            self.derived_root /= derived_namespace
        self.state_path = self.raw_root / "state.json"
        self.provider = provider
        quality = config["content_quality"]
        self.normalizer = EodhdNormalizer(ContentQualityClassifier(
            partial_min_words=quality["partial_min_words"],
            full_min_words=quality["full_min_words"],
        ))
        self.risk_filter = RiskFamilyFilter(config["risk_rules"])
        dedupe = config["deduplication"]
        self.deduplicator = ArticleDeduplicator(
            date_tolerance_days=dedupe["date_tolerance_days"],
            title_similarity_threshold=dedupe["title_similarity_threshold"],
        )
        clustering = config["event_clustering"]
        self.clusterer = EventClusterer(
            max_days=clustering["max_days"],
            similarity_threshold=clustering["similarity_threshold"],
        )

    @classmethod
    def with_eodhd_provider(
        cls,
        config: EodhdPilotConfig,
        *,
        repository: Path,
        api_token: str,
        derived_namespace: str | None = None,
    ) -> "EodhdPilot":
        http = config["http"]
        provider = EodhdProvider(
            endpoint=config["endpoint"],
            api_token=api_token,
            timeout_seconds=http["timeout_seconds"],
            max_attempts=http["max_attempts"],
            backoff_base_seconds=http["backoff_base_seconds"],
            backoff_max_seconds=http["backoff_max_seconds"],
            jitter_seconds=http["jitter_seconds"],
        )
        return cls(
            config,
            repository=repository,
            provider=provider,
            derived_namespace=derived_namespace,
        )

    def plan(self, *, mode: str, start: date, end: date) -> list[QueryWindow]:
        if mode not in self.config["modes"]:
            raise ValueError(f"Unknown execution mode: {mode}")
        allowed = set(self.config["modes"][mode].get("tickers", []))
        windows = []
        for company, details in self.config["companies"].items():
            for ticker in details["query_tickers"]:
                if allowed and ticker not in allowed:
                    continue
                windows.extend(monthly_windows(company, ticker, start, end))
        return windows

    def dry_run(self, *, mode: str, start: date, end: date) -> dict:
        windows = self.plan(mode=mode, start=start, end=end)
        return {
            "provider": "eodhd",
            "mode": mode,
            "from": start.isoformat(),
            "to": end.isoformat(),
            "windows": [window.to_dict() for window in windows],
            "planned_windows": len(windows),
            "planned_initial_calls": len(windows),
            "api_called": False,
        }

    def run(self, *, mode: str, start: date, end: date) -> dict:
        return self.run_windows(
            mode=mode,
            windows=self.plan(mode=mode, start=start, end=end),
            query_from=start,
            query_to=end,
        )

    def run_windows(
        self,
        *,
        mode: str,
        windows: list[QueryWindow],
        query_from: date | None = None,
        query_to: date | None = None,
        source_query_manifest: dict | None = None,
    ) -> dict:
        if self.provider is None:
            raise ValueError("A provider is required for a live run")
        if not windows:
            raise ValueError("At least one query window is required")
        if len({window.key for window in windows}) != len(windows):
            raise ValueError("Explicit query windows must be unique")
        query_from = query_from or min(window.start for window in windows)
        query_to = query_to or max(window.end for window in windows)
        started = time.monotonic()
        started_at = now_utc()
        state = self._load_state()
        articles: list[NormalizedArticle] = []
        counters = Counter()
        window_results = []
        for window in windows:
            if state["windows"].get(window.key, {}).get("status") == "complete":
                cached = self._load_normalized(window)
                articles.extend(cached)
                counters["windows_resumed"] += 1
                window_results.append({
                    **state["windows"][window.key],
                    "http_calls_this_run": 0,
                    "retries_this_run": 0,
                    "resumed": True,
                })
                continue
            try:
                result, rows = self._fetch_window_tree(window, state)
                articles.extend(rows)
                window_results.extend(result)
            except AuthenticationError:
                self._save_state(state)
                raise
            except (ProviderError, WindowLimitError) as exc:
                error = {
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "status_code": getattr(exc, "status_code", None),
                    "payload": getattr(exc, "sanitized_payload", None),
                    "acquisition_calls": getattr(exc, "attempts", 0),
                    "acquisition_retries": max(0, getattr(exc, "attempts", 0) - 1),
                    "http_calls_this_run": getattr(exc, "attempts", 0),
                    "retries_this_run": max(0, getattr(exc, "attempts", 0) - 1),
                    **window.to_dict(),
                }
                state["windows"][window.key] = error
                self._write_error(window, error)
                self._save_state(state)
                window_results.append(error)
                counters["windows_failed"] += 1

        duplicate_groups = self.deduplicator.assign(articles)
        event_proposals = self.clusterer.propose(articles)
        self._write_derived(articles, duplicate_groups, event_proposals)
        candidates = [row for row in articles if row.risk_family_candidates]
        useful_candidates = [row for row in candidates if row.content_available in {"full", "partial"}]
        counters.update({
            "articles": len(articles),
            "unique_article_ids": len({row.article_id for row in articles}),
            "duplicate_groups": len(duplicate_groups),
            "duplicate_excess_records": sum(group["count"] - 1 for group in duplicate_groups),
            "event_proposals": len(event_proposals),
            "risk_candidates": len(candidates),
            "useful_risk_candidates": len(useful_candidates),
            "http_calls": sum(result.get("acquisition_calls", 0) for result in window_results),
            "http_calls_this_run": sum(result.get("http_calls_this_run", 0) for result in window_results),
            "retries": sum(result.get("acquisition_retries", 0) for result in window_results),
            "retries_this_run": sum(result.get("retries_this_run", 0) for result in window_results),
            "cached_pages_used": sum(result.get("cached_pages_used", 0) for result in window_results),
            "windows_complete": sum(result.get("status") == "complete" for result in window_results),
        })
        manifest = {
            "provider": "eodhd",
            "mode": mode,
            "started_at_utc": started_at,
            "finished_at_utc": now_utc(),
            "elapsed_seconds": time.monotonic() - started,
            "query_from": query_from.isoformat(),
            "query_to": query_to.isoformat(),
            "config_path": str(self.config.source_path),
            "config_sha256": config_fingerprint(self.config.values),
            "code": self._code_version(),
            "counts": dict(counters),
            "content_availability": dict(Counter(row.content_available for row in articles)),
            "content_length_words_median": median(row.content_length_words for row in articles) if articles else None,
            "storage_bytes": {
                "raw_restricted": self._directory_size(self.raw_root),
                "normalized_restricted": self._directory_size(self.normalized_root),
                "derived_without_bodies": self._directory_size(self.derived_root),
            },
            "windows": window_results,
            "limitations": [
                "Candidate rules and event clusters are proposals requiring human review",
                "No result means no evidence located, not proof that no event occurred",
                "Sentiment is retained as provider metadata and is not an adverse-event label",
            ],
        }
        if source_query_manifest:
            manifest["source_query_manifest"] = source_query_manifest
        write_json(self.derived_root / "manifest.json", manifest)
        return manifest

    def _fetch_window_tree(self, root: QueryWindow, state: dict) -> tuple[list[dict], list[NormalizedArticle]]:
        pending = deque([root])
        results, all_rows = [], []
        while pending:
            window = pending.popleft()
            status, rows = self._fetch_one_window(window, state)
            if status["status"] == "split":
                results.append(status)
                left, right = window.split()
                pending.extendleft((right, left))
            else:
                results.append(status)
                all_rows.extend(rows)
        return results, all_rows

    def _fetch_one_window(self, window: QueryWindow, state: dict) -> tuple[dict, list[NormalizedArticle]]:
        pagination = self.config["pagination"]
        limit, max_offset = pagination["limit"], pagination["max_offset"]
        offset, rows = 0, []
        calls_this_run = retries_this_run = acquisition_calls = acquisition_retries = cached_pages = 0
        while True:
            page = self._page_from_cache(window, offset)
            if page is None:
                page = self.provider.fetch_page(PageRequest(window, limit, offset))
                self._write_raw_page(page)
                calls_this_run += page.attempts
                retries_this_run += page.attempts - 1
            else:
                cached_pages += 1
            acquisition_calls += page.attempts
            acquisition_retries += page.attempts - 1
            raw_sha = digest(page.raw_bytes)
            for raw in page.articles:
                article = self.normalizer.normalize(
                    raw,
                    window=window,
                    retrieved_at_utc=page.retrieved_at_utc,
                    raw_sha256=raw_sha,
                )
                self.risk_filter.apply(article)
                rows.append(article)
            if len(page.articles) < limit:
                break
            next_offset = offset + limit
            if next_offset >= max_offset:
                if window.start == window.end:
                    raise WindowLimitError(f"One-day window reached offset ceiling for {window.company}")
                status = {
                    "status": "split",
                    "acquisition_calls": acquisition_calls,
                    "acquisition_retries": acquisition_retries,
                    "http_calls_this_run": calls_this_run,
                    "retries_this_run": retries_this_run,
                    "cached_pages_used": cached_pages,
                    **window.to_dict(),
                }
                state["windows"][window.key] = status
                self._save_state(state)
                return status, []
            offset = next_offset
        self._write_normalized(window, rows)
        status = {
            "status": "complete",
            "articles": len(rows),
            "pages": offset // limit + 1,
            "acquisition_calls": acquisition_calls,
            "acquisition_retries": acquisition_retries,
            "http_calls_this_run": calls_this_run,
            "retries_this_run": retries_this_run,
            "cached_pages_used": cached_pages,
            **window.to_dict(),
        }
        state["windows"][window.key] = status
        self._save_state(state)
        return status, rows

    def _window_directory(self, root: Path, window: QueryWindow) -> Path:
        safe_ticker = window.ticker.replace(".", "_")
        return root / window.company / safe_ticker / f"{window.start.isoformat()}__{window.end.isoformat()}"

    def _write_raw_page(self, page: ProviderPage) -> None:
        directory = self._window_directory(self.raw_root, page.request.window)
        destination = directory / f"offset_{page.request.offset:05}.json"
        write_bytes(destination, page.raw_bytes)
        write_json(destination.with_suffix(".meta.json"), {
            **page.request.window.to_dict(),
            "offset": page.request.offset,
            "limit": page.request.limit,
            "status_code": page.status_code,
            "retrieved_at_utc": page.retrieved_at_utc,
            "attempts": page.attempts,
            "article_count": len(page.articles),
            "sha256": digest(page.raw_bytes),
        })

    def _page_from_cache(self, window: QueryWindow, offset: int) -> ProviderPage | None:
        directory = self._window_directory(self.raw_root, window)
        path = directory / f"offset_{offset:05}.json"
        metadata_path = path.with_suffix(".meta.json")
        if not path.exists() and not metadata_path.exists():
            return None
        if not path.exists() or not metadata_path.exists():
            raise ValueError(f"Incomplete raw cache for {window.key} offset {offset}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        raw = path.read_bytes()
        if digest(raw) != metadata["sha256"]:
            raise ValueError(f"Raw cache hash mismatch for {window.key} offset {offset}")
        payload = json.loads(raw)
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise ValueError(f"Invalid cached page for {window.key} offset {offset}")
        return ProviderPage(
            request=PageRequest(window, metadata["limit"], offset),
            articles=payload,
            raw_bytes=raw,
            status_code=metadata["status_code"],
            retrieved_at_utc=metadata["retrieved_at_utc"],
            attempts=metadata["attempts"],
            from_cache=True,
        )

    def _write_normalized(self, window: QueryWindow, rows: list[NormalizedArticle]) -> None:
        path = self._window_directory(self.normalized_root, window) / "articles.jsonl"
        payload = "".join(json.dumps(row.to_dict(), ensure_ascii=False) + "\n" for row in rows).encode("utf-8")
        write_bytes(path, payload)

    def _load_normalized(self, window: QueryWindow) -> list[NormalizedArticle]:
        path = self._window_directory(self.normalized_root, window) / "articles.jsonl"
        if not path.exists():
            raise ValueError(f"Completed window has no normalized cache: {window.key}")
        return [NormalizedArticle(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines()]

    def _write_error(self, window: QueryWindow, error: dict) -> None:
        write_json(self._window_directory(self.raw_root, window) / "error.sanitized.json", error)

    def _write_derived(self, articles, duplicate_groups, event_proposals) -> None:
        rows = [article.to_dict(include_content=False) for article in articles]
        fields = list(rows[0]) if rows else list(NormalizedArticle.__dataclass_fields__)
        fields = [field for field in fields if field != "content"]
        write_csv(self.derived_root / "articles_metadata.csv", fields, rows)
        write_json(self.derived_root / "duplicate_groups.json", duplicate_groups)
        write_json(self.derived_root / "event_proposals.json", event_proposals)
        self._write_review_sample(articles)

    def _write_review_sample(self, articles: list[NormalizedArticle]) -> None:
        settings = self.config["review_sample"]
        selected = []
        for company in self.config["companies"]:
            company_rows = [row for row in articles if row.company == company]
            strata = (
                ("risk_candidate", [row for row in company_rows if row.risk_family_candidates], settings["per_company_candidates"]),
                ("other", [row for row in company_rows if not row.risk_family_candidates], settings["per_company_other"]),
            )
            for label, rows, limit in strata:
                ranked = sorted(rows, key=lambda row: digest(settings["seed"] + company + label + row.article_id))
                for row in ranked[:limit]:
                    selected.append({
                        "article_id": row.article_id,
                        "company": row.company,
                        "published_at_utc": row.published_at_utc,
                        "title": row.title,
                        "content_available": row.content_available,
                        "content_length_words": row.content_length_words,
                        "risk_family_candidates": "|".join(row.risk_family_candidates),
                        "duplicate_group_id": row.duplicate_group_id or "",
                        "selection_stratum": label,
                        "review_status": "pending",
                        "relevant_event": "",
                        "noise_type": "",
                        "episode_id": "",
                        "reviewer": "",
                        "notes": "",
                    })
        fields = list(selected[0]) if selected else [
            "article_id", "company", "published_at_utc", "title", "content_available",
            "content_length_words", "risk_family_candidates", "duplicate_group_id",
            "selection_stratum", "review_status", "relevant_event", "noise_type",
            "episode_id", "reviewer", "notes",
        ]
        destination = self.derived_root / "review_sample.csv"
        if destination.exists():
            destination = self.derived_root / "review_sample.template.csv"
        write_csv(destination, fields, selected)

    def _load_state(self) -> dict:
        acquisition_fingerprint = self._acquisition_fingerprint()
        processing_fingerprint = self._processing_fingerprint()
        if self.state_path.exists():
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            if "acquisition_config_sha256" not in state:
                if state.get("config_sha256") != config_fingerprint(self.config.values):
                    raise ValueError("Legacy EODHD cache belongs to a different configuration; use a new data path")
                state["acquisition_config_sha256"] = acquisition_fingerprint
                state["processing_config_sha256"] = processing_fingerprint
            if state["acquisition_config_sha256"] != acquisition_fingerprint:
                raise ValueError("EODHD raw cache belongs to a different acquisition configuration")
            if state["processing_config_sha256"] != processing_fingerprint:
                for status in state["windows"].values():
                    if status.get("status") == "complete":
                        status["status"] = "raw_cached_reprocessing_required"
                state["processing_config_sha256"] = processing_fingerprint
            return state
        return {
            "created_at_utc": now_utc(),
            "acquisition_config_sha256": acquisition_fingerprint,
            "processing_config_sha256": processing_fingerprint,
            "windows": {},
        }

    def _save_state(self, state: dict) -> None:
        state["updated_at_utc"] = now_utc()
        write_json(self.state_path, state)

    @staticmethod
    def _directory_size(path: Path) -> int:
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file()) if path.exists() else 0

    def _acquisition_fingerprint(self) -> str:
        values = {
            "provider": self.config["provider"],
            "endpoint": self.config["endpoint"],
            "pagination": self.config["pagination"],
            "companies": self.config["companies"],
            "modes": self.config["modes"],
        }
        return config_fingerprint(values)

    def _processing_fingerprint(self) -> str:
        directory = Path(__file__).parent
        values = {
            "content_quality": self.config["content_quality"],
            "risk_rules": self.config["risk_rules"],
            "deduplication": self.config["deduplication"],
            "event_clustering": self.config["event_clustering"],
            "review_sample": self.config["review_sample"],
            "code": {
                name: file_sha256(directory / name)
                for name in ("normalize.py", "quality.py", "risk_filter.py", "deduplicate.py", "event_cluster.py")
            },
        }
        return config_fingerprint(values)

    @staticmethod
    def _code_version() -> dict:
        try:
            revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
            dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip())
        except (OSError, subprocess.CalledProcessError):
            revision, dirty = None, None
        directory = Path(__file__).parent
        hashes = {str(path.relative_to(directory)): file_sha256(path) for path in sorted(directory.rglob("*.py"))}
        return {"git_revision": revision, "working_tree_dirty": dirty, "news_module_sha256": hashes}
