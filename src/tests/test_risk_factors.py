from src.text_analysis.risk_factors import (
    BoldHeadingDetector,
    HeuristicHeadingDetector,
    RiskFactorSegmenter,
    normalize,
)


SECTION = "\n".join(
    [
        "Regulatory",
        "Our businesses are highly regulated and could be adversely affected.",
        "A" * 400,
        "B" * 400,
        "Resolving regulatory investigations can subject us to penalties.",
        "C" * 400,
        "Market",
        "Changes in interest rates can adversely affect our earnings.",
        "D" * 400,
    ]
)

BOLD_RUNS = [
    "Regulatory",
    "Our businesses are highly regulated and could be adversely affected.",
    "Resolving regulatory investigations can subject us to penalties.",
    "Market",
    "Changes in interest rates can adversely affect our earnings.",
]


def test_normalize_collapses_whitespace_and_case() -> None:
    assert normalize("  Highly   Regulated\nBusinesses ") == "highly regulated businesses"


def test_bold_detector_segments_factors_under_their_category() -> None:
    segmenter = RiskFactorSegmenter(BoldHeadingDetector(BOLD_RUNS))

    factors = segmenter.segment(SECTION)

    assert [(f.order, f.category) for f in factors] == [
        (1, "Regulatory"),
        (2, "Regulatory"),
        (3, "Market"),
    ]
    assert factors[0].heading.startswith("Our businesses are highly regulated")
    assert factors[0].body == "\n".join(["A" * 400, "B" * 400])


def test_bold_detector_treats_short_unpunctuated_runs_as_categories() -> None:
    detector = BoldHeadingDetector(BOLD_RUNS)

    assert detector.is_category("Regulatory")
    assert not detector.is_category("Changes in interest rates can adversely affect our earnings.")
    assert detector.is_heading("Changes in interest rates can adversely affect our earnings.", "")


def test_bold_detector_ignores_page_furniture() -> None:
    detector = BoldHeadingDetector(["Part I", "Item 1A. Risk Factors", "Summary"])

    assert not detector.is_heading("Part I", "X" * 400)
    assert not detector.is_heading("Item 1A. Risk Factors", "X" * 400)
    assert not detector.is_category("Summary")


def test_bold_detector_ignores_lines_that_are_not_bold() -> None:
    detector = BoldHeadingDetector(["Our businesses are highly regulated."])

    assert not detector.is_heading("An ordinary body sentence.", "X" * 400)


def test_bold_detector_from_html_reads_font_weight_and_tags() -> None:
    html = (
        '<div><span style="font-weight:700">Regulatory</span></div>'
        '<div><span style="font-weight:400">body text</span></div>'
        "<div><b>Bold tag heading.</b></div>"
    )

    detector = BoldHeadingDetector.from_html(html)

    assert detector.is_category("Regulatory")
    assert detector.is_heading("Bold tag heading.", "X" * 400)
    assert not detector.is_heading("body text", "X" * 400)


def test_heuristic_detector_accepts_short_line_before_long_body() -> None:
    detector = HeuristicHeadingDetector()

    assert detector.is_heading("We may experience fluctuations in our results of operations.", "X" * 400)


def test_heuristic_detector_rejects_bullet_lead_ins_and_fragments() -> None:
    detector = HeuristicHeadingDetector()

    assert not detector.is_heading("Factors that may affect our results include:", "X" * 400)
    assert not detector.is_heading("• a bulleted risk item that is long enough to pass", "X" * 400)
    assert not detector.is_heading("or uncertain intellectual property laws apply here.", "X" * 400)
    assert not detector.is_heading("A heading with no body following it at all here.", "short")


def test_heuristic_detector_reports_no_categories() -> None:
    assert not HeuristicHeadingDetector().is_category("Regulatory")


def test_segmenter_skips_lines_before_the_first_heading() -> None:
    segmenter = RiskFactorSegmenter(BoldHeadingDetector(BOLD_RUNS))

    factors = segmenter.segment("Some introductory prose.\n" + SECTION)

    assert len(factors) == 3
    assert factors[0].category == "Regulatory"


def test_risk_factor_counts_heading_and_body() -> None:
    segmenter = RiskFactorSegmenter(BoldHeadingDetector(BOLD_RUNS))

    factor = segmenter.segment(SECTION)[2]

    assert factor.word_count == len("Changes in interest rates can adversely affect our earnings.".split()) + 1
    assert factor.sentence_count >= 1
