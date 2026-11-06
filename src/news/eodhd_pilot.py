from __future__ import annotations

import json
import subprocess
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from statistics import median

from .acquisition_budget import AcquisitionBudget
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


@dataclass
class _BreadthFirstCursor:
    window: QueryWindow
    prior_status: dict | None = None
    offset: int = 0
    rows: list[NormalizedArticle] = field(default_factory=list)
    pages: int = 0
    acquisition_calls: int = 0
    acquisition_retries: int = 0
    calls_this_run: int = 0
    retries_this_run: int = 0
    cached_pages: int = 0
    provider_records_received: int = 0
    buffered_page: ProviderPage | None = None
    buffered_index: int = 0


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
            namespace = Path(derived_namespace)
            if namespace.is_absolute() or ".." in namespace.parts or not namespace.parts:
                raise ValueError("derived_namespace must be a safe relative path")
            self.derived_root /= namespace
        self.state_path = self.raw_root / "state.json"
        self.provider = provider
        quality = config["content_quality"]
        self.normalizer = EodhdNormalizer(ContentQualityClassifier(
            partial_min_words=quality["partial_min_words"],
            full_min_words=quality["full_min_words"],
        ))
        self.risk_filter = RiskFamilyFilter(
            config["risk_rules"],
            config.values.get("risk_filter"),
        )
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

    def plan(
        self,
        *,
        mode: str,
        start: date,
        end: date,
        companies: list[str] | None = None,
        interleave_companies: bool = False,
    ) -> list[QueryWindow]:
        if mode not in self.config["modes"]:
            raise ValueError(f"Unknown execution mode: {mode}")
        selected_companies = companies or list(self.config["companies"])
        unknown_companies = set(selected_companies) - set(self.config["companies"])
        if unknown_companies:
            raise ValueError(f"Unknown companies: {sorted(unknown_companies)}")
        if len(set(selected_companies)) != len(selected_companies):
            raise ValueError("Companies must be unique")
        allowed = set(self.config["modes"][mode].get("tickers", []))
        company_windows = []
        company_rank = {company: index for index, company in enumerate(selected_companies)}
        ticker_rank = {}
        for company in selected_companies:
            details = self.config["companies"][company]
            ticker_windows = []
            for index, ticker in enumerate(details["query_tickers"]):
                if allowed and ticker not in allowed:
                    continue
                ticker_rank[(company, ticker)] = index
                ticker_windows.append(monthly_windows(company, ticker, start, end))
            company_windows.append([window for group in ticker_windows for window in group])
        if interleave_companies:
            return sorted(
                (window for windows in company_windows for window in windows),
                key=lambda window: (
                    window.start,
                    company_rank[window.company],
                    ticker_rank[(window.company, window.ticker)],
                ),
            )
        return [window for windows in company_windows for window in windows]

    def dry_run(
        self,
        *,
        mode: str,
        start: date,
        end: date,
        companies: list[str] | None = None,
        interleave_companies: bool = False,
        breadth_first_pages: bool = False,
        acquisition_budget: AcquisitionBudget | None = None,
    ) -> dict:
        windows = self.plan(
            mode=mode,
            start=start,
            end=end,
            companies=companies,
            interleave_companies=interleave_companies,
        )
        return {
            "provider": "eodhd",
            "mode": mode,
            "from": start.isoformat(),
            "to": end.isoformat(),
            "windows": [window.to_dict() for window in windows],
            "planned_windows": len(windows),
            "planned_initial_calls": len(windows),
            "window_order": (
                "chronological_interleaved_by_company"
                if interleave_companies
                else "configured"
            ),
            "page_traversal": "breadth_first" if breadth_first_pages else "window_depth_first",
            "article_budget_unit": (
                "unique_company_article_relation"
                if breadth_first_pages
                else "provider_record"
            ),
            "acquisition_budget": (acquisition_budget or AcquisitionBudget()).snapshot(),
            "api_called": False,
        }

    def run(
        self,
        *,
        mode: str,
        start: date,
        end: date,
        companies: list[str] | None = None,
        interleave_companies: bool = False,
        breadth_first_pages: bool = False,
        acquisition_budget: AcquisitionBudget | None = None,
    ) -> dict:
        return self.run_windows(
            mode=mode,
            windows=self.plan(
                mode=mode,
                start=start,
                end=end,
                companies=companies,
                interleave_companies=interleave_companies,
            ),
            query_from=start,
            query_to=end,
            breadth_first_pages=breadth_first_pages,
            acquisition_budget=acquisition_budget,
        )

    def run_windows(
        self,
        *,
        mode: str,
        windows: list[QueryWindow],
        query_from: date | None = None,
        query_to: date | None = None,
        source_query_manifest: dict | None = None,
        breadth_first_pages: bool = False,
        acquisition_budget: AcquisitionBudget | None = None,
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
        budget = acquisition_budget or AcquisitionBudget()
        if breadth_first_pages:
            articles, window_results, breadth_counters = self._fetch_breadth_first(
                windows, state, budget
            )
            counters.update(breadth_counters)
        else:
            for window_index, window in enumerate(windows):
                if not budget.require_article_capacity():
                    counters["windows_skipped_budget"] += len(windows) - window_index
                    break
                if state["windows"].get(window.key, {}).get("status") == "complete":
                    cached, truncated = budget.admit(self._load_normalized(window))
                    articles.extend(cached)
                    counters["windows_resumed"] += 1
                    result = {
                        **state["windows"][window.key],
                        "http_calls_this_run": 0,
                        "retries_this_run": 0,
                        "resumed": True,
                        "articles_admitted_this_run": len(cached),
                    }
                    if truncated:
                        result["cached_status"] = result["status"]
                        result["status"] = "budget_exhausted"
                        result["budget_stop_reason"] = budget.stop_reason
                        counters["windows_skipped_budget"] += len(windows) - window_index - 1
                    window_results.append(result)
                    if truncated:
                        break
                    continue
                try:
                    result, rows = self._fetch_window_tree(window, state, budget)
                    articles.extend(rows)
                    window_results.extend(result)
                    if any(item["status"] == "budget_exhausted" for item in result):
                        counters["windows_skipped_budget"] += len(windows) - window_index - 1
                        break
                except AuthenticationError:
                    self._save_state(state)
                    raise
                except (ProviderError, WindowLimitError) as exc:
                    error = self._window_error(window, exc)
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
        acquisition_complete = (
            bool(window_results)
            and all(result.get("status") in {"complete", "split"} for result in window_results)
            and not counters["windows_failed"]
            and not counters["windows_skipped_budget"]
        )
        manifest = {
            "provider": "eodhd",
            "mode": mode,
            "started_at_utc": started_at,
            "finished_at_utc": now_utc(),
            "elapsed_seconds": time.monotonic() - started,
            "query_from": query_from.isoformat(),
            "query_to": query_to.isoformat(),
            "companies": sorted({window.company for window in windows}),
            "query_tickers": sorted({window.ticker for window in windows}),
            "planned_windows": len(windows),
            "page_traversal": "breadth_first" if breadth_first_pages else "window_depth_first",
            "article_budget_unit": (
                "unique_company_article_relation"
                if breadth_first_pages
                else "provider_record"
            ),
            "acquisition_complete": acquisition_complete,
            "acquisition_budget": budget.snapshot(),
            "config_path": str(self.config.source_path),
            "config_sha256": config_fingerprint(self.config.values),
            "code": self._code_version(),
            "counts": dict(counters),
            "content_availability": dict(Counter(row.content_available for row in articles)),
            "content_length_words_median": median(row.content_length_words for row in articles) if articles else None,
            "storage_paths": {
                "raw_restricted": str(self.raw_root.relative_to(self.repository)),
                "normalized_restricted": str(self.normalized_root.relative_to(self.repository)),
                "derived_without_bodies": str(self.derived_root.relative_to(self.repository)),
            },
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

    def _fetch_breadth_first(
        self,
        windows: list[QueryWindow],
        state: dict,
        budget: AcquisitionBudget,
    ) -> tuple[list[NormalizedArticle], list[dict], Counter]:
        """Visit one bounded page slice per window and repeat in rounds."""
        pending = deque(
            _BreadthFirstCursor(window, state["windows"].get(window.key))
            for window in windows
        )
        articles: list[NormalizedArticle] = []
        results: list[dict] = []
        counters = Counter()
        configured_limit = self.config["pagination"]["limit"]

        while pending:
            if not budget.require_article_capacity():
                skipped = sum(not cursor.pages and not cursor.rows for cursor in pending)
                counters["windows_skipped_budget"] += skipped
                counters["windows_incomplete_budget"] += len(pending) - skipped
                results.extend(self._finalize_breadth_partials(pending, state, budget))
                break

            current_round = [pending.popleft() for _ in range(len(pending))]
            remaining = budget.remaining_articles
            slice_limit = configured_limit
            if remaining is not None:
                slice_limit = max(1, min(configured_limit, remaining // len(current_round)))
            next_round: deque[_BreadthFirstCursor] = deque()
            stopped = False

            for index, cursor in enumerate(current_round):
                try:
                    outcome, admitted, status = self._fetch_breadth_slice(
                        cursor, state, budget, slice_limit
                    )
                except AuthenticationError:
                    self._save_state(state)
                    raise
                except (ProviderError, WindowLimitError) as exc:
                    error = self._cursor_error(cursor, exc)
                    state["windows"][cursor.window.key] = error
                    self._write_error(cursor.window, error)
                    self._save_state(state)
                    results.append(error)
                    counters["windows_failed"] += 1
                    continue

                articles.extend(admitted)
                if outcome == "continue":
                    next_round.append(cursor)
                elif outcome == "split":
                    results.append(status)
                    left, right = cursor.window.split()
                    next_round.extend((
                        _BreadthFirstCursor(left, state["windows"].get(left.key)),
                        _BreadthFirstCursor(right, state["windows"].get(right.key)),
                    ))
                else:
                    results.append(status)

                if outcome == "budget_exhausted":
                    untouched = current_round[index + 1:]
                    next_round.extend(untouched)
                    skipped = sum(
                        not pending_cursor.pages and not pending_cursor.rows
                        for pending_cursor in next_round
                    )
                    counters["windows_skipped_budget"] += skipped
                    counters["windows_incomplete_budget"] += (
                        1 + len(next_round) - skipped
                    )
                    results.extend(
                        self._finalize_breadth_partials(next_round, state, budget)
                    )
                    stopped = True
                    break

            if stopped:
                break
            pending = next_round

        counters["provider_records_received"] = sum(
            result.get("provider_records_received", 0) for result in results
        )
        counters["records_deduplicated_before_budget"] = budget.duplicate_records_skipped
        counters["windows_resumed"] = sum(bool(result.get("resumed")) for result in results)
        return articles, results, counters

    def _fetch_breadth_slice(
        self,
        cursor: _BreadthFirstCursor,
        state: dict,
        budget: AcquisitionBudget,
        slice_limit: int,
    ) -> tuple[str, list[NormalizedArticle], dict | None]:
        window = cursor.window
        if cursor.buffered_page is None:
            page = self._page_from_cache(window, cursor.offset)
            if page is None:
                request_limit = budget.page_limit(slice_limit)
                if request_limit is None:
                    status = self._breadth_status(cursor, "budget_exhausted", budget)
                    self._store_breadth_partial(cursor, state, status)
                    return "budget_exhausted", [], status
                attempt_limit = budget.http_attempt_limit(
                    getattr(self.provider, "max_attempts", 1)
                )
                if attempt_limit is None:
                    status = self._breadth_status(cursor, "budget_exhausted", budget)
                    self._store_breadth_partial(cursor, state, status)
                    return "budget_exhausted", [], status
                budget.register_network_page()
                try:
                    page = self.provider.fetch_page(
                        PageRequest(window, request_limit, cursor.offset),
                        max_attempts=attempt_limit,
                    )
                except ProviderError as exc:
                    budget.register_http_attempts(exc.attempts)
                    cursor.acquisition_calls += exc.attempts
                    cursor.acquisition_retries += max(0, exc.attempts - 1)
                    cursor.calls_this_run += exc.attempts
                    cursor.retries_this_run += max(0, exc.attempts - 1)
                    raise
                budget.register_http_attempts(page.attempts)
                self._write_raw_page(page)
                cursor.calls_this_run += page.attempts
                cursor.retries_this_run += page.attempts - 1
            else:
                cursor.cached_pages += 1
            cursor.buffered_page = page
            cursor.buffered_index = 0
            cursor.pages += 1
            cursor.acquisition_calls += page.attempts
            cursor.acquisition_retries += page.attempts - 1
            cursor.provider_records_received += len(page.articles)

        page = cursor.buffered_page
        end = min(len(page.articles), cursor.buffered_index + slice_limit)
        raw_slice = page.articles[cursor.buffered_index:end]
        raw_sha = digest(page.raw_bytes)
        normalized = []
        for raw in raw_slice:
            article = self.normalizer.normalize(
                raw,
                window=window,
                retrieved_at_utc=page.retrieved_at_utc,
                raw_sha256=raw_sha,
            )
            self.risk_filter.apply(article)
            normalized.append(article)
        admitted, truncated = budget.admit_unique(
            normalized,
            identity=lambda article: (article.company, article.article_id),
        )
        cursor.rows.extend(admitted)
        cursor.buffered_index = end

        if truncated:
            status = self._breadth_status(cursor, "budget_exhausted", budget)
            self._store_breadth_partial(cursor, state, status)
            return "budget_exhausted", admitted, status
        if cursor.buffered_index < len(page.articles):
            return "continue", admitted, None

        page_complete = len(page.articles) < page.request.limit
        cursor.buffered_page = None
        cursor.buffered_index = 0
        if page_complete:
            self._write_normalized(window, cursor.rows)
            status = self._breadth_status(cursor, "complete", budget)
            state["windows"][window.key] = status
            self._save_state(state)
            return "complete", admitted, status

        next_offset = cursor.offset + page.request.limit
        if next_offset >= self.config["pagination"]["max_offset"]:
            if window.start == window.end:
                raise WindowLimitError(f"One-day window reached offset ceiling for {window.company}")
            self._write_partial_normalized(window, cursor.rows)
            status = self._breadth_status(cursor, "split", budget)
            state["windows"][window.key] = status
            self._save_state(state)
            return "split", admitted, status

        cursor.offset = next_offset
        if not budget.require_article_capacity():
            status = self._breadth_status(cursor, "budget_exhausted", budget)
            self._store_breadth_partial(cursor, state, status)
            return "budget_exhausted", admitted, status
        return "continue", admitted, None

    def _finalize_breadth_partials(
        self,
        cursors: deque[_BreadthFirstCursor],
        state: dict,
        budget: AcquisitionBudget,
    ) -> list[dict]:
        results = []
        while cursors:
            cursor = cursors.popleft()
            if not cursor.pages and not cursor.rows:
                continue
            status = self._breadth_status(cursor, "budget_exhausted", budget)
            self._store_breadth_partial(cursor, state, status)
            results.append(status)
        return results

    def _store_breadth_partial(
        self,
        cursor: _BreadthFirstCursor,
        state: dict,
        status: dict,
    ) -> None:
        self._write_partial_normalized(cursor.window, cursor.rows)
        if not cursor.prior_status or cursor.prior_status.get("status") != "complete":
            state["windows"][cursor.window.key] = status
            self._save_state(state)

    @staticmethod
    def _breadth_status(
        cursor: _BreadthFirstCursor,
        status: str,
        budget: AcquisitionBudget,
    ) -> dict:
        result = {
            "status": status,
            "articles": len(cursor.rows),
            "pages": cursor.pages,
            "acquisition_calls": cursor.acquisition_calls,
            "acquisition_retries": cursor.acquisition_retries,
            "http_calls_this_run": cursor.calls_this_run,
            "retries_this_run": cursor.retries_this_run,
            "cached_pages_used": cursor.cached_pages,
            "provider_records_received": cursor.provider_records_received,
            **cursor.window.to_dict(),
        }
        if status == "budget_exhausted":
            result["budget_stop_reason"] = budget.stop_reason
        if cursor.prior_status and cursor.prior_status.get("status") == "complete":
            result["resumed"] = True
        return result

    @staticmethod
    def _window_error(window: QueryWindow, exc: Exception) -> dict:
        return {
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

    def _cursor_error(self, cursor: _BreadthFirstCursor, exc: Exception) -> dict:
        return {
            **self._window_error(cursor.window, exc),
            "acquisition_calls": cursor.acquisition_calls,
            "acquisition_retries": cursor.acquisition_retries,
            "http_calls_this_run": cursor.calls_this_run,
            "retries_this_run": cursor.retries_this_run,
            "cached_pages_used": cursor.cached_pages,
            "provider_records_received": cursor.provider_records_received,
        }

    def _fetch_window_tree(
        self,
        root: QueryWindow,
        state: dict,
        budget: AcquisitionBudget,
    ) -> tuple[list[dict], list[NormalizedArticle]]:
        pending = deque([root])
        results, all_rows = [], []
        while pending:
            window = pending.popleft()
            status, rows = self._fetch_one_window(window, state, budget)
            if status["status"] == "split":
                results.append(status)
                left, right = window.split()
                pending.extendleft((right, left))
            else:
                results.append(status)
                all_rows.extend(rows)
                if status["status"] == "budget_exhausted":
                    break
        return results, all_rows

    def _fetch_one_window(
        self,
        window: QueryWindow,
        state: dict,
        budget: AcquisitionBudget,
    ) -> tuple[dict, list[NormalizedArticle]]:
        pagination = self.config["pagination"]
        limit, max_offset = pagination["limit"], pagination["max_offset"]
        offset, rows = 0, []
        pages = 0
        calls_this_run = retries_this_run = acquisition_calls = acquisition_retries = cached_pages = 0
        while True:
            if not budget.require_article_capacity():
                return self._budget_exhausted_status(
                    window, state, budget, rows, pages, acquisition_calls,
                    acquisition_retries, calls_this_run, retries_this_run, cached_pages,
                )
            page = self._page_from_cache(window, offset)
            if page is None:
                request_limit = budget.page_limit(limit)
                if request_limit is None:
                    return self._budget_exhausted_status(
                        window, state, budget, rows, pages, acquisition_calls,
                        acquisition_retries, calls_this_run, retries_this_run, cached_pages,
                    )
                attempt_limit = budget.http_attempt_limit(
                    getattr(self.provider, "max_attempts", 1)
                )
                if attempt_limit is None:
                    return self._budget_exhausted_status(
                        window, state, budget, rows, pages, acquisition_calls,
                        acquisition_retries, calls_this_run, retries_this_run, cached_pages,
                    )
                budget.register_network_page()
                try:
                    page = self.provider.fetch_page(
                        PageRequest(window, request_limit, offset),
                        max_attempts=attempt_limit,
                    )
                except ProviderError as exc:
                    budget.register_http_attempts(exc.attempts)
                    raise
                budget.register_http_attempts(page.attempts)
                self._write_raw_page(page)
                calls_this_run += page.attempts
                retries_this_run += page.attempts - 1
            else:
                cached_pages += 1
            pages += 1
            acquisition_calls += page.attempts
            acquisition_retries += page.attempts - 1
            raw_sha = digest(page.raw_bytes)
            admitted, truncated = budget.admit(page.articles)
            for raw in admitted:
                article = self.normalizer.normalize(
                    raw,
                    window=window,
                    retrieved_at_utc=page.retrieved_at_utc,
                    raw_sha256=raw_sha,
                )
                self.risk_filter.apply(article)
                rows.append(article)
            page_complete = len(page.articles) < page.request.limit
            if truncated or (not page_complete and budget.remaining_articles == 0):
                budget.require_article_capacity()
                return self._budget_exhausted_status(
                    window, state, budget, rows, pages, acquisition_calls,
                    acquisition_retries, calls_this_run, retries_this_run, cached_pages,
                )
            if page_complete:
                break
            next_offset = offset + page.request.limit
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
            "pages": pages,
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

    def _budget_exhausted_status(
        self,
        window: QueryWindow,
        state: dict,
        budget: AcquisitionBudget,
        rows: list[NormalizedArticle],
        pages: int,
        acquisition_calls: int,
        acquisition_retries: int,
        calls_this_run: int,
        retries_this_run: int,
        cached_pages: int,
    ) -> tuple[dict, list[NormalizedArticle]]:
        self._write_partial_normalized(window, rows)
        status = {
            "status": "budget_exhausted",
            "budget_stop_reason": budget.stop_reason,
            "articles": len(rows),
            "pages": pages,
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

    def _write_partial_normalized(self, window: QueryWindow, rows: list[NormalizedArticle]) -> None:
        path = self._window_directory(self.normalized_root, window) / "articles.partial.jsonl"
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
            "risk_filter": self.config.values.get("risk_filter", {}),
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
