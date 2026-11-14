from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from src.settings import load_dotenv

from .acquisition_budget import AcquisitionBudget
from .common import require_env
from .dataset_split import NewsDatasetSplit
from .eodhd_config import EodhdPilotConfig
from .eodhd_pilot import EodhdPilot
from .eodhd_report import EodhdReportBuilder
from .episode_windows import EpisodeWindowPlanner
from .known_episode_metrics import KnownEpisodeMetricsBuilder
from .known_episode_candidate_review import KnownEpisodeCandidateReviewBuilder
from .known_episode_candidate_metrics import KnownEpisodeCandidateMetricsBuilder
from .review_metrics import ReviewMetricsBuilder
from .reference_filter import ReferenceEpisodeFilter
from .risk_news_development_review import RiskNewsDevelopmentReviewBuilder
from .risk_news_development_metrics import RiskNewsDevelopmentMetricsBuilder
from .risk_news_revised_candidate_review import RevisedRiskNewsCandidateReviewBuilder
from .risk_news_calibration_comparison import RiskNewsCalibrationComparator
from .risk_news_calibration_consensus import RiskNewsCalibrationConsensusBuilder
from .risk_news_calibration_sample import RiskNewsCalibrationSampler
from .risk_news_review_sheet import PackagedRiskNewsReviewBuilder
from .risk_news_dataset import RiskNewsDatasetPackager


DEFAULT_CONFIG = Path("config/eodhd_pilot.json")


def parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


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

    dataset = commands.add_parser(
        "dataset",
        help="Acquire and package a bounded, bodyless risk-news candidate dataset",
    )
    dataset.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    dataset.add_argument("--dataset-id", required=True)
    dataset.add_argument("--from", dest="from_date", type=parse_iso_date, required=True)
    dataset.add_argument("--to", dest="to_date", type=parse_iso_date, required=True)
    dataset.add_argument("--companies", nargs="+")
    dataset.add_argument(
        "--risk-families",
        nargs="+",
        help="Defaults to every risk family configured for the pilot",
    )
    dataset.add_argument("--max-acquired-articles", type=positive_int, required=True)
    dataset.add_argument("--max-network-pages", type=positive_int)
    dataset.add_argument("--max-http-attempts", type=positive_int, required=True)
    dataset.add_argument("--max-candidates", type=positive_int, required=True)
    dataset.add_argument("--selection-seed", default="eodhd-risk-dataset-v1")
    dataset.add_argument("--split-config", type=Path)
    dataset.add_argument("--split-stage", choices=("train", "validation", "test", "all"))
    dataset.add_argument("--dry-run", action="store_true")

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

    development_review = commands.add_parser(
        "risk-development-review",
        help="Build selection/classification development labels without conflating episode matching",
    )
    development_review.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    development_review.add_argument(
        "--recent-review", type=Path,
        default=Path("data/processed/eodhd_mag7/review_sample.csv"),
    )
    development_review.add_argument(
        "--recent-metadata", type=Path,
        default=Path("data/processed/eodhd_mag7/articles_metadata.csv"),
    )
    development_review.add_argument(
        "--episode-review", type=Path,
        default=Path(
            "data/processed/eodhd_mag7/known_episode_probe/known_episode_candidate_review.csv"
        ),
    )
    development_review.add_argument(
        "--output", type=Path,
        default=Path("data/processed/eodhd_mag7/risk_news_development_review.csv"),
    )
    development_metrics = commands.add_parser(
        "risk-development-metrics",
        help="Validate development labels and compare stored versus revised local filters",
    )
    development_metrics.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    development_metrics.add_argument(
        "--review", type=Path,
        default=Path("data/processed/eodhd_mag7/risk_news_development_review.csv"),
    )
    development_metrics.add_argument(
        "--recent-metadata", type=Path,
        default=Path("data/processed/eodhd_mag7/articles_metadata.csv"),
    )
    development_metrics.add_argument(
        "--episode-metadata", type=Path,
        default=Path("data/processed/eodhd_mag7/known_episode_probe/articles_metadata.csv"),
    )
    development_metrics.add_argument(
        "--normalized-root", type=Path,
        default=Path("data/restricted/news/eodhd/normalized"),
    )
    development_metrics.add_argument(
        "--output", type=Path,
        default=Path("data/processed/eodhd_mag7/risk_news_development_metrics.json"),
    )
    development_metrics.add_argument(
        "--report", type=Path,
        default=Path("reports/eodhd_risk_news_development.md"),
    )
    development_metrics.add_argument(
        "--revised-new-review", type=Path,
        default=Path(
            "data/processed/eodhd_mag7/risk_news_revised_new_candidates_review.csv"
        ),
    )
    revised_review = commands.add_parser(
        "risk-revised-candidate-review",
        help="Export candidates newly introduced by the revised local filter",
    )
    revised_review.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    revised_review.add_argument(
        "--normalized-root", type=Path,
        default=Path("data/restricted/news/eodhd/normalized"),
    )
    revised_review.add_argument(
        "--output", type=Path,
        default=Path("data/processed/eodhd_mag7/risk_news_revised_new_candidates_review.csv"),
    )
    dataset_review = commands.add_parser(
        "dataset-review-sheet",
        help="Create a derived human-review sheet from a packaged risk-news candidate CSV",
    )
    dataset_review.add_argument("--candidates", type=Path, required=True)
    dataset_review.add_argument("--output", type=Path, required=True)
    calibration = commands.add_parser(
        "dataset-calibration-sample",
        help="Build a reproducible stratified calibration sample for independent annotators",
    )
    calibration.add_argument("--review", type=Path, required=True)
    calibration.add_argument("--candidates", type=Path, required=True)
    calibration.add_argument("--output-dir", type=Path, required=True)
    calibration.add_argument("--annotators", nargs="+", required=True)
    calibration.add_argument("--sample-size", type=positive_int, default=40)
    calibration.add_argument(
        "--seed", default="mag7-risk-calibration-2021-2026-v1"
    )
    calibration_compare = commands.add_parser(
        "dataset-calibration-compare",
        help="Validate completed calibration reviews and write exact agreement metrics",
    )
    calibration_compare.add_argument("--manifest", type=Path, required=True)
    calibration_compare.add_argument(
        "--reviews",
        type=Path,
        nargs="+",
        required=True,
        help="Completed independent annotator CSV files",
    )
    calibration_compare.add_argument("--output", type=Path, required=True)
    calibration_consensus = commands.add_parser(
        "dataset-calibration-consensus-sheet",
        help="Create a protected consensus CSV from calibration discrepancies",
    )
    calibration_consensus.add_argument("--comparison", type=Path, required=True)
    calibration_consensus.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "dataset-calibration-sample":
        print(json.dumps(RiskNewsCalibrationSampler(seed=args.seed).build(
            review_path=args.review,
            candidates_path=args.candidates,
            output_dir=args.output_dir,
            annotators=args.annotators,
            sample_size=args.sample_size,
        ), indent=2))
        return
    if args.command == "dataset-calibration-compare":
        print(json.dumps(RiskNewsCalibrationComparator().build(
            manifest_path=args.manifest,
            review_paths=args.reviews,
            output_path=args.output,
        ), indent=2))
        return
    if args.command == "dataset-calibration-consensus-sheet":
        print(json.dumps(RiskNewsCalibrationConsensusBuilder().build(
            comparison_path=args.comparison,
            output_path=args.output,
        ), indent=2))
        return
    if args.command == "dataset-review-sheet":
        print(json.dumps(PackagedRiskNewsReviewBuilder().build(
            args.candidates,
            args.output,
        ), indent=2))
        return
    config = EodhdPilotConfig.load(args.config)
    if args.command == "dataset":
        try:
            dataset_id = RiskNewsDatasetPackager.validate_dataset_id(args.dataset_id)
            if args.from_date > args.to_date:
                raise ValueError("--from must not be after --to")
            risk_families = args.risk_families or list(config["risk_rules"])
            split_protocol = None
            split_stage = None
            companies = args.companies
            if args.split_config:
                split_protocol = NewsDatasetSplit.load(
                    args.split_config,
                    configured_companies=set(config["companies"]),
                )
                if split_protocol.target_risk_families is not None:
                    if (
                        args.risk_families is not None
                        and set(args.risk_families)
                        != set(split_protocol.target_risk_families)
                    ):
                        raise ValueError(
                            "--risk-families must match the split protocol target families: "
                            f"{split_protocol.target_risk_families}"
                        )
                    risk_families = split_protocol.target_risk_families
                split_stage = args.split_stage or "train"
                companies = split_protocol.validate_request(
                    start=args.from_date,
                    end=args.to_date,
                    stage=split_stage,
                    companies=args.companies,
                )
                expected_candidates = (
                    split_protocol.values["target_candidates"]["total"]
                    if split_stage == "all"
                    else split_protocol.values["target_candidates"][split_stage]
                )
                if args.max_candidates != expected_candidates:
                    raise ValueError(
                        f"Split stage {split_stage} requires --max-candidates "
                        f"{expected_candidates}"
                    )
            elif args.split_stage:
                raise ValueError("--split-stage requires --split-config")
            unknown_families = set(risk_families) - set(config["risk_rules"])
            if unknown_families:
                raise ValueError(f"Unknown risk families: {sorted(unknown_families)}")
            if len(set(risk_families)) != len(risk_families):
                raise ValueError("--risk-families values must be unique")
            budget = AcquisitionBudget(
                max_articles=args.max_acquired_articles,
                max_network_pages=args.max_network_pages,
                max_http_attempts=args.max_http_attempts,
            )
            namespace = RiskNewsDatasetPackager.namespace(dataset_id)
            output_root = Path.cwd() / config["paths"]["derived"] / namespace
            packager = RiskNewsDatasetPackager(
                repository=Path.cwd(),
                selection_seed=args.selection_seed,
            )
            if args.dry_run:
                plan = EodhdPilot(config, repository=Path.cwd()).dry_run(
                    mode="pilot",
                    start=args.from_date,
                    end=args.to_date,
                    companies=companies,
                    interleave_companies=True,
                    breadth_first_pages=True,
                    acquisition_budget=budget,
                )
                plan["dataset"] = {
                    "dataset_id": dataset_id,
                    "risk_families": risk_families,
                    "max_candidates": args.max_candidates,
                    "selection_seed": args.selection_seed,
                    "output_directory": str(Path(config["paths"]["derived"]) / namespace),
                    "writes_files": False,
                }
                if split_protocol:
                    plan["dataset"]["split_protocol"] = split_protocol.manifest(
                        stage=split_stage
                    )
                print(json.dumps(plan, indent=2))
                return
            packager.ensure_destination_available(output_root)
            load_dotenv()
            pilot = EodhdPilot.with_eodhd_provider(
                config,
                repository=Path.cwd(),
                api_token=require_env("EODHD_API_TOKEN"),
                derived_namespace=namespace,
            )
            pilot.run(
                mode="pilot",
                start=args.from_date,
                end=args.to_date,
                companies=companies,
                interleave_companies=True,
                breadth_first_pages=True,
                acquisition_budget=budget,
            )
            print(json.dumps(packager.build(
                dataset_id=dataset_id,
                metadata_path=output_root / "articles_metadata.csv",
                acquisition_manifest_path=output_root / "manifest.json",
                output_root=output_root,
                risk_families=risk_families,
                max_candidates=args.max_candidates,
                company_splits=split_protocol.company_roles if split_protocol else None,
                split_protocol=(
                    split_protocol.manifest(stage=split_stage) if split_protocol else None
                ),
            ), indent=2))
        except (ValueError, FileExistsError) as exc:
            parser.error(str(exc))
        return
    if args.command == "risk-revised-candidate-review":
        print(json.dumps(RevisedRiskNewsCandidateReviewBuilder(config.values).build(
            args.normalized_root,
            args.output,
        ), indent=2))
        return
    if args.command == "risk-development-metrics":
        print(json.dumps(RiskNewsDevelopmentMetricsBuilder(config.values).build(
            args.review,
            args.recent_metadata,
            args.episode_metadata,
            args.normalized_root,
            args.output,
            args.report,
            args.revised_new_review,
        ), indent=2))
        return
    if args.command == "risk-development-review":
        print(json.dumps(RiskNewsDevelopmentReviewBuilder().build(
            args.recent_review,
            args.recent_metadata,
            args.episode_review,
            args.output,
        ), indent=2))
        return
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
