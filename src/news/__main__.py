from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from src.settings import load_dotenv

from .common import require_env
from .eodhd_config import EodhdPilotConfig
from .eodhd_pilot import EodhdPilot
from .eodhd_report import EodhdReportBuilder
from .episode_windows import EpisodeWindowPlanner
from .known_episode_metrics import KnownEpisodeMetricsBuilder
from .known_episode_candidate_review import KnownEpisodeCandidateReviewBuilder
from .known_episode_candidate_metrics import KnownEpisodeCandidateMetricsBuilder
from .review_metrics import ReviewMetricsBuilder
from .reference_filter import ReferenceEpisodeFilter


DEFAULT_CONFIG = Path("config/eodhd_pilot.json")


def parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def effective_dates(args, config: EodhdPilotConfig) -> tuple[date, date]:
    if bool(args.from_date) != bool(args.to_date):
        raise ValueError("--from and --to must be supplied together")
    if args.from_date:
        return args.from_date, args.to_date
    if args.mode == "pilot":
        raise ValueError("Pilot mode requires explicit --from and --to dates")
    end = date.today()
    days = config["modes"]["demo"]["lookback_days"]
    return end - timedelta(days=days - 1), end


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Auditable EODHD news pilot; no scraping or LLM labelling")
    providers = parser.add_subparsers(dest="provider", required=True)
    eodhd = providers.add_parser("eodhd")
    commands = eodhd.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="Plan or execute a bounded EODHD query")
    run.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    run.add_argument("--mode", choices=("demo", "pilot"), default="demo")
    run.add_argument("--from", dest="from_date", type=parse_iso_date)
    run.add_argument("--to", dest="to_date", type=parse_iso_date)
    run.add_argument("--dry-run", action="store_true")

    report = commands.add_parser("report", help="Build a report without repeating downloads")
    report.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    report.add_argument("--manifest", type=Path, default=Path("data/processed/eodhd_mag7/manifest.json"))
    report.add_argument("--output", type=Path, default=Path("reports/eodhd_pilot_report.md"))

    review = commands.add_parser("review", help="Validate annotations and derive review metrics")
    review.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    review.add_argument("--csv", type=Path, default=Path("data/processed/eodhd_mag7/review_sample.csv"))
    review.add_argument("--manifest", type=Path, default=Path("data/processed/eodhd_mag7/manifest.json"))
    review.add_argument("--output", type=Path, default=Path("data/processed/eodhd_mag7/review_metrics.json"))

    reference_filter = commands.add_parser(
        "reference-filter", help="Filter the 49-card inventory into eligible known episodes"
    )
    reference_filter.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    reference_filter.add_argument(
        "--review-csv", type=Path,
        default=Path("data/reference/news_mag7/known_cases_review.csv"),
    )
    reference_filter.add_argument(
        "--rules", type=Path, default=Path("config/eodhd_reference_filter.json")
    )
    reference_filter.add_argument(
        "--output", type=Path,
        default=Path("data/reference/news_mag7/eligible_known_episodes.json"),
    )
    reference_filter.add_argument(
        "--report", type=Path,
        default=Path("reports/eodhd_reference_filter_report.md"),
    )

    episode_dry_run = commands.add_parser(
        "episode-dry-run",
        help="Write a credential-free EODHD query manifest for known episodes",
    )
    episode_dry_run.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    episode_dry_run.add_argument(
        "--episodes", type=Path,
        default=Path("data/reference/news_mag7/eligible_known_episodes.json"),
    )
    episode_dry_run.add_argument(
        "--output", type=Path,
        default=Path("data/processed/eodhd_mag7/known_episode_query_manifest.json"),
    )
    episode_dry_run.add_argument("--days-before", type=int, default=3)
    episode_dry_run.add_argument("--days-after", type=int, default=7)

    episode_run = commands.add_parser(
        "episode-run",
        help="Execute exactly the bounded windows in a validated dry-run manifest",
    )
    episode_run.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    episode_run.add_argument(
        "--manifest", type=Path,
        default=Path("data/processed/eodhd_mag7/known_episode_query_manifest.json"),
    )

    episode_metrics = commands.add_parser(
        "episode-metrics", help="Calculate human-confirmed known-episode recovery metrics"
    )
    episode_metrics.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    episode_metrics.add_argument(
        "--episodes", type=Path,
        default=Path("data/reference/news_mag7/eligible_known_episodes.json"),
    )
    episode_metrics.add_argument(
        "--query-manifest", type=Path,
        default=Path("data/processed/eodhd_mag7/known_episode_query_manifest.json"),
    )
    episode_metrics.add_argument(
        "--acquisition-manifest", type=Path,
        default=Path("data/processed/eodhd_mag7/known_episode_probe/manifest.json"),
    )
    episode_metrics.add_argument(
        "--metadata", type=Path,
        default=Path("data/processed/eodhd_mag7/known_episode_probe/articles_metadata.csv"),
    )
    episode_metrics.add_argument(
        "--review", type=Path,
        default=Path("config/eodhd_known_episode_recovery_review.json"),
    )
    episode_metrics.add_argument(
        "--output", type=Path,
        default=Path("data/processed/eodhd_mag7/known_episode_probe/recovery_metrics.json"),
    )
    episode_metrics.add_argument(
        "--report", type=Path,
        default=Path("reports/eodhd_known_episode_recovery.md"),
    )

    candidate_review = commands.add_parser(
        "episode-candidate-review", help="Prepare all known-window lexical candidates for review"
    )
    candidate_review.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    candidate_review.add_argument(
        "--metadata", type=Path,
        default=Path("data/processed/eodhd_mag7/known_episode_probe/articles_metadata.csv"),
    )
    candidate_review.add_argument(
        "--acquisition-manifest", type=Path,
        default=Path("data/processed/eodhd_mag7/known_episode_probe/manifest.json"),
    )
    candidate_review.add_argument(
        "--query-manifest", type=Path,
        default=Path("data/processed/eodhd_mag7/known_episode_query_manifest.json"),
    )
    candidate_review.add_argument(
        "--confirmed-review", type=Path,
        default=Path("config/eodhd_known_episode_recovery_review.json"),
    )
    candidate_review.add_argument(
        "--output", type=Path,
        default=Path("data/processed/eodhd_mag7/known_episode_probe/known_episode_candidate_review.csv"),
    )

    candidate_metrics = commands.add_parser(
        "episode-candidate-metrics", help="Calculate confirmed article-level candidate precision"
    )
    candidate_metrics.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    candidate_metrics.add_argument(
        "--review", type=Path,
        default=Path("data/processed/eodhd_mag7/known_episode_probe/known_episode_candidate_review.csv"),
    )
    candidate_metrics.add_argument(
        "--metadata", type=Path,
        default=Path("data/processed/eodhd_mag7/known_episode_probe/articles_metadata.csv"),
    )
    candidate_metrics.add_argument(
        "--acquisition-manifest", type=Path,
        default=Path("data/processed/eodhd_mag7/known_episode_probe/manifest.json"),
    )
    candidate_metrics.add_argument(
        "--query-manifest", type=Path,
        default=Path("data/processed/eodhd_mag7/known_episode_query_manifest.json"),
    )
    candidate_metrics.add_argument(
        "--episode-metrics", type=Path,
        default=Path("data/processed/eodhd_mag7/known_episode_probe/recovery_metrics.json"),
    )
    candidate_metrics.add_argument(
        "--output", type=Path,
        default=Path("data/processed/eodhd_mag7/known_episode_probe/candidate_review_metrics.json"),
    )
    candidate_metrics.add_argument(
        "--report", type=Path,
        default=Path("reports/eodhd_known_episode_candidate_precision.md"),
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = EodhdPilotConfig.load(args.config)
    if args.command == "episode-candidate-metrics":
        print(json.dumps(KnownEpisodeCandidateMetricsBuilder().build(
            args.review,
            args.metadata,
            args.acquisition_manifest,
            args.query_manifest,
            args.episode_metrics,
            args.output,
            args.report,
        ), indent=2))
        return
    if args.command == "episode-candidate-review":
        print(json.dumps(KnownEpisodeCandidateReviewBuilder().build(
            args.metadata,
            args.acquisition_manifest,
            args.query_manifest,
            args.confirmed_review,
            args.output,
        ), indent=2))
        return
    if args.command == "episode-metrics":
        print(json.dumps(KnownEpisodeMetricsBuilder(config).build(
            args.episodes,
            args.query_manifest,
            args.acquisition_manifest,
            args.metadata,
            args.review,
            args.output,
            args.report,
        ), indent=2))
        return
    if args.command == "episode-dry-run":
        print(json.dumps(EpisodeWindowPlanner(config).build(
            args.episodes,
            args.output,
            days_before=args.days_before,
            days_after=args.days_after,
        ), indent=2))
        return
    if args.command == "episode-run":
        windows, source_manifest = EpisodeWindowPlanner(config).load_query_windows(args.manifest)
        load_dotenv()
        pilot = EodhdPilot.with_eodhd_provider(
            config,
            repository=Path.cwd(),
            api_token=require_env("EODHD_API_TOKEN"),
            derived_namespace="known_episode_probe",
        )
        print(json.dumps(pilot.run_windows(
            mode="known_episode_probe",
            windows=windows,
            source_query_manifest=source_manifest,
        ), indent=2))
        return
    if args.command == "reference-filter":
        print(json.dumps(ReferenceEpisodeFilter().build(
            args.review_csv, args.rules, args.output, args.report,
        ), indent=2))
        return
    if args.command == "review":
        print(json.dumps(ReviewMetricsBuilder().build(args.csv, args.manifest, args.output), indent=2))
        return
    if args.command == "report":
        print(json.dumps(EodhdReportBuilder(config).build(args.manifest, args.output), indent=2))
        return
    try:
        start, end = effective_dates(args, config)
    except ValueError as exc:
        parser.error(str(exc))
    if args.dry_run:
        pilot = EodhdPilot(config, repository=Path.cwd())
        print(json.dumps(pilot.dry_run(mode=args.mode, start=start, end=end), indent=2))
        return
    if args.mode == "pilot":
        load_dotenv()
    token = "demo" if args.mode == "demo" else require_env("EODHD_API_TOKEN")
    pilot = EodhdPilot.with_eodhd_provider(config, repository=Path.cwd(), api_token=token)
    print(json.dumps(pilot.run(mode=args.mode, start=start, end=end), indent=2))


if __name__ == "__main__":
    main()
