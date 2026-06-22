#!/usr/bin/env python3
"""
demo.py – SEC 10-K interactive subsection explorer (US banking sector).

Fetches the latest 10-K for a given ticker from SEC EDGAR, lets the user
pick an item from an interactive menu, and uses DeepSeek to break it down
into structured subsections.

Usage:
    python demo.py --ticker JPM
    python demo.py --ticker BAC --item 7
    python demo.py --ticker WFC --item 1A
"""
from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_extraction import extract_filing_section
from src.data_extraction.sec_filings import SecCompanyClient, SecFilingError
from src.llm.deepseek import DEFAULT_MAX_TOKENS, DeepSeekClient
from src.prompts.subsection_breakdown import build_subsection_breakdown_messages


BANKING_TICKERS = [
    "JPM", "BAC", "WFC", "C", "GS", "MS", "USB", "PNC",
    "TFC", "COF", "KEY", "FITB", "RF", "HBAN", "MTB",
    "CFG", "ZION", "CMA", "STT", "BK", "NTRS", "WAL",
]

ITEM_MENU = [
    ("1",  "Business"),
    ("1A", "Risk Factors"),
    ("1B", "Unresolved Staff Comments"),
    ("1C", "Cybersecurity"),
    ("2",  "Properties"),
    ("3",  "Legal Proceedings"),
    ("7",  "Management's Discussion and Analysis (MD&A)"),
    ("7A", "Quantitative and Qualitative Disclosures About Market Risk"),
    ("9A", "Controls and Procedures"),
    ("10", "Directors, Executive Officers and Corporate Governance"),
    ("11", "Executive Compensation"),
]

SEPARATOR = "─" * 72


def pick_item_interactive() -> str:
    print("\nAvailable 10-K items:\n")
    for i, (code, desc) in enumerate(ITEM_MENU, start=1):
        print(f"  [{i:2d}]  Item {code:<4}  {desc}")
    print()
    while True:
        raw = input("Select item number: ").strip()
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(ITEM_MENU):
                code, desc = ITEM_MENU[idx]
                print(f"\n  Selected: Item {code} – {desc}\n")
                return code
        print(f"  Enter a number between 1 and {len(ITEM_MENU)}.")


def item_description(code: str) -> str:
    for c, d in ITEM_MENU:
        if c == code.upper():
            return d
    return ""


def print_result(result: dict) -> None:
    subsections = result.get("subsections", [])
    company = result.get("company", "")
    ticker = result.get("ticker", "")
    year = result.get("year", "")
    item = result.get("item", "")

    print(f"\n{SEPARATOR}")
    print(f"  {company} ({ticker})  ·  {year} 10-K  ·  {item}")
    print(SEPARATOR)

    if not subsections:
        print("\n  No subsections found in the extracted text.\n")
        return

    for sub in subsections:
        order = sub.get("order", "")
        title = sub.get("title", "")
        summary = sub.get("summary", "")
        key_points = sub.get("key_points") or []

        print(f"\n  {order}. {title}")
        print(f"  {'─' * (len(str(order)) + 2 + len(title))}")

        if summary:
            wrapped = textwrap.fill(
                summary, width=68, initial_indent="  ", subsequent_indent="  "
            )
            print(wrapped)

        if key_points:
            print()
            for kp in key_points:
                wrapped = textwrap.fill(
                    f"• {kp}",
                    width=66,
                    initial_indent="  ",
                    subsequent_indent="    ",
                )
                print(wrapped)

    print(f"\n{SEPARATOR}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse a 10-K section for a US bank using DeepSeek.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Available tickers (US banking sector):\n"
            f"  {', '.join(BANKING_TICKERS)}\n\n"
            "Examples:\n"
            "  python demo.py --ticker JPM\n"
            "  python demo.py --ticker BAC --item 7\n"
            "  python demo.py --ticker WFC --item 1A 7 1C\n"
            "  python demo.py --ticker JPM --year 2023 --item 1A\n"
        ),
    )
    parser.add_argument(
        "--ticker", required=True,
        help="Company ticker symbol (e.g. JPM, BAC, WFC)",
    )
    parser.add_argument(
        "--item", default=None, nargs="+",
        help="10-K item code(s) (e.g. 1A 7 7A). Omit to see an interactive menu.",
    )
    parser.add_argument(
        "--year", default=None, type=int, nargs="+",
        help="Fiscal year(s) of the 10-K (e.g. 2023 2024). Omit for the latest filing.",
    )
    args = parser.parse_args()

    ticker = args.ticker.upper()
    item_codes = [i.upper() for i in args.item] if args.item else None
    years = args.year  # list[int] | None

    # ── 1. Resolve items ──────────────────────────────────────────────────────
    if item_codes is None:
        item_codes = [pick_item_interactive()]

    # ── 2. Fetch 10-K filing metadata ─────────────────────────────────────────
    year_label = " & ".join(str(y) for y in sorted(years)) if years else "latest"
    print(f"Fetching {year_label} 10-K(s) for {ticker} from SEC EDGAR …")
    try:
        client = SecCompanyClient()
        filings = client.filing_metadata(
            ticker,
            form="10-K",
            limit=len(years) if years else 1,
            report_years=set(years) if years else None,
        )
    except SecFilingError as exc:
        sys.exit(f"Error: {exc}")

    if not filings:
        not_found = f"fiscal year(s) {year_label}" if years else ticker
        sys.exit(f"No 10-K filing found for {not_found}.")

    # ── 3. Init DeepSeek client once ──────────────────────────────────────────
    try:
        ds_client = DeepSeekClient.from_env(env_path=PROJECT_ROOT / ".env")
    except Exception as exc:
        sys.exit(f"DeepSeek init error: {exc}")

    # ── 4. Process each filing × each item ───────────────────────────────────
    for metadata in filings:
        print(
            f"\n{metadata.company}  |  {metadata.form} filed {metadata.filing_date}"
            f"  (period ending {metadata.report_date})"
        )
        for item_code in item_codes:
            desc = item_description(item_code)
            section_name = f"Item {item_code}. {desc}" if desc else f"Item {item_code}"

            print(f"\nExtracting {section_name} via edgar-crawler …")
            try:
                section = extract_filing_section(
                    client=client,
                    metadata=metadata,
                    item=item_code,
                    section=section_name,
                    cache_dir=PROJECT_ROOT / "data" / "edgar_crawler_live",
                )
            except SecFilingError as exc:
                print(f"  Extraction error: {exc} — skipping.")
                continue

            word_count = section.word_count
            char_count = len(section.text)
            print(f"  Extracted {word_count:,} words ({char_count:,} chars)")

            if char_count > 200_000:
                print(
                    f"  Warning: section is very long ({char_count:,} chars)."
                    " DeepSeek will process the full text; this may take a moment."
                )

            print("Sending to DeepSeek for subsection breakdown …")
            eval_case = section.to_eval_case(case_id_suffix="subsection-breakdown")
            messages = build_subsection_breakdown_messages(eval_case, section.text)

            try:
                result, response = ds_client.chat_json(
                    messages, max_tokens=DEFAULT_MAX_TOKENS, temperature=0.0
                )
            except Exception as exc:
                print(f"  DeepSeek error: {exc} — skipping.")
                continue

            usage = response.usage or {}
            print(
                f"  Model: {response.model}  |  "
                f"prompt tokens: {usage.get('prompt_tokens', '?')}  |  "
                f"completion tokens: {usage.get('completion_tokens', '?')}"
            )

            print_result(result)


if __name__ == "__main__":
    main()
