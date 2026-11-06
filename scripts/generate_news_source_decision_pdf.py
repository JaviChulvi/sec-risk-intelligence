"""Generate the executive decision note comparing FNSPID with EODHD."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "output/pdf/decision_fuente_noticias_fnspid_vs_eodhd.pdf"

INK = colors.HexColor("#17212B")
MUTED = colors.HexColor("#5B6875")
BLUE = colors.HexColor("#174A7E")
BLUE_LIGHT = colors.HexColor("#EAF2FA")
TEAL = colors.HexColor("#0E6B64")
TEAL_LIGHT = colors.HexColor("#E6F4F1")
RED = colors.HexColor("#A13B35")
RED_LIGHT = colors.HexColor("#FBEDEA")
AMBER = colors.HexColor("#9A6210")
AMBER_LIGHT = colors.HexColor("#FFF4DA")
LINE = colors.HexColor("#D7DEE5")
PAPER = colors.HexColor("#F7F9FB")


class NewsSourceDecisionPdf:
    """Build a concise, evidence-based two-page decision document."""

    def __init__(self, output_path: Path = OUTPUT_PATH) -> None:
        self.output_path = output_path
        self.styles = self._styles()

    @staticmethod
    def _styles() -> dict[str, ParagraphStyle]:
        return {
            "kicker": ParagraphStyle(
                "Kicker",
                fontName="Helvetica-Bold",
                fontSize=7.5,
                leading=9,
                textColor=BLUE,
                spaceAfter=5,
            ),
            "title": ParagraphStyle(
                "Title",
                fontName="Helvetica-Bold",
                fontSize=23,
                leading=25,
                textColor=INK,
                spaceAfter=6,
            ),
            "subtitle": ParagraphStyle(
                "Subtitle",
                fontName="Helvetica",
                fontSize=9.5,
                leading=13,
                textColor=MUTED,
                spaceAfter=13,
            ),
            "decision_title": ParagraphStyle(
                "DecisionTitle",
                fontName="Helvetica-Bold",
                fontSize=12,
                leading=14,
                textColor=colors.white,
                spaceAfter=4,
            ),
            "decision_body": ParagraphStyle(
                "DecisionBody",
                fontName="Helvetica",
                fontSize=9.2,
                leading=12.5,
                textColor=colors.white,
            ),
            "section": ParagraphStyle(
                "Section",
                fontName="Helvetica-Bold",
                fontSize=12.5,
                leading=15,
                textColor=INK,
                spaceBefore=2,
                spaceAfter=7,
            ),
            "body": ParagraphStyle(
                "Body",
                fontName="Helvetica",
                fontSize=8.7,
                leading=12.2,
                textColor=INK,
                spaceAfter=6,
            ),
            "small": ParagraphStyle(
                "Small",
                fontName="Helvetica",
                fontSize=7.2,
                leading=9.5,
                textColor=MUTED,
            ),
            "metric_value": ParagraphStyle(
                "MetricValue",
                fontName="Helvetica-Bold",
                fontSize=17,
                leading=18,
                textColor=INK,
                alignment=TA_CENTER,
                spaceAfter=3,
            ),
            "metric_label": ParagraphStyle(
                "MetricLabel",
                fontName="Helvetica",
                fontSize=7.2,
                leading=9,
                textColor=MUTED,
                alignment=TA_CENTER,
            ),
            "table_header": ParagraphStyle(
                "TableHeader",
                fontName="Helvetica-Bold",
                fontSize=7.3,
                leading=9,
                textColor=colors.white,
            ),
            "table_cell": ParagraphStyle(
                "TableCell",
                fontName="Helvetica",
                fontSize=7.2,
                leading=9,
                textColor=INK,
            ),
            "table_cell_bold": ParagraphStyle(
                "TableCellBold",
                fontName="Helvetica-Bold",
                fontSize=7.2,
                leading=9,
                textColor=INK,
            ),
            "callout_title": ParagraphStyle(
                "CalloutTitle",
                fontName="Helvetica-Bold",
                fontSize=9.2,
                leading=11,
                textColor=INK,
                spaceAfter=4,
            ),
            "callout_body": ParagraphStyle(
                "CalloutBody",
                fontName="Helvetica",
                fontSize=8,
                leading=11,
                textColor=INK,
            ),
            "quote": ParagraphStyle(
                "Quote",
                fontName="Helvetica-Oblique",
                fontSize=9.5,
                leading=13.5,
                textColor=BLUE,
                leftIndent=7,
                rightIndent=7,
                alignment=TA_LEFT,
            ),
        }

    def _p(self, text: str, style: str) -> Paragraph:
        return Paragraph(text, self.styles[style])

    def _metric_cards(self) -> Table:
        data = [[
            [self._p("15 / 178", "metric_value"), self._p("pares empresa-año con artículo en FNSPID", "metric_label")],
            [self._p("5 / 6", "metric_value"), self._p("episodios conocidos recuperados por EODHD", "metric_label")],
            [self._p("81.273", "metric_value"), self._p("relaciones EODHD con texto completo o parcial", "metric_label")],
        ]]
        table = Table(data, colWidths=[55.5 * mm] * 3, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), RED_LIGHT),
            ("BACKGROUND", (1, 0), (2, 0), TEAL_LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.6, LINE),
            ("INNERGRID", (0, 0), (-1, -1), 0.6, colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ]))
        return table

    def _comparison_table(self) -> Table:
        rows = [
            ["Criterio", "FNSPID", "EODHD"],
            ["Cobertura temporal", "Finaliza el 16/12/2023; numerosos años sin resultados.", "Consultas hasta 2026 y actualización incremental."],
            ["Cobertura Mag7", "31/178 pares empresa-año con noticias; 15/178 con artículo.", "120.000 relaciones de entrenamiento adquiridas; cobertura todavía acotada."],
            ["Contenido", "48.538 asociaciones con Article no vacío, pero sin garantía de integridad.", "73.164 full y 8.109 partial; calidad registrada por artículo."],
            ["Validación por episodios", "No realizada; el propio patrón anual impide recuperar al menos 3 de 6 casos.", "5/6 episodios recuperados y 5/5 recuperados con contenido útil."],
            ["Operación", "Descarga completa de 28,96 GB y escaneo de 28,6 millones de filas.", "API, caché reanudable, paginación y paquetes derivados sin cuerpos."],
            ["Reproducibilidad", "Alta: corpus estático, revisión y hashes fijados.", "Alta sobre la caché local; dependencia externa de API y condiciones de uso."],
        ]
        converted = []
        for row_number, row in enumerate(rows):
            style = "table_header" if row_number == 0 else "table_cell"
            converted.append([self._p(cell, style) for cell in row])
        table = Table(converted, colWidths=[31 * mm, 67.5 * mm, 67.5 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BLUE),
            ("BACKGROUND", (0, 1), (0, -1), PAPER),
            ("BACKGROUND", (1, 1), (1, -1), colors.HexColor("#FFF8F7")),
            ("BACKGROUND", (2, 1), (2, -1), colors.HexColor("#F4FAF8")),
            ("GRID", (0, 0), (-1, -1), 0.45, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]))
        return table

    def _callout(self, title: str, body: str, background: colors.Color) -> Table:
        content = [[self._p(title, "callout_title")], [self._p(body, "callout_body")]]
        table = Table(content, colWidths=[166 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), background),
            ("BOX", (0, 0), (-1, -1), 0.6, LINE),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
            ("TOPPADDING", (0, 1), (-1, 1), 1),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 9),
            ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ]))
        return table

    def _limitations_table(self) -> Table:
        items = [
            ("Cobertura incompleta", "El histórico 2021-2026 alcanzó el límite de 120.000 relaciones: 125 de 345 ventanas quedaron completas y 220 incompletas."),
            ("Revisión humana", "El filtro recupera candidatos, no etiquetas finales. En la revisión inicial de 2026, 21 de 57 candidatos fueron relevantes."),
            ("Sesgo por ticker", "EODHD no recuperó IF Metall para Tesla. Hace falta una fuente complementaria para acontecimientos locales o mal asociados."),
            ("Control operativo", "Las reanudaciones acumularon 1.620 páginas. Debe implantarse un límite global, no solo por invocación."),
            ("Uso y redistribución", "Antes del dataset final deben verificarse las condiciones de conservación, publicación y redistribución del proveedor."),
        ]
        rows = []
        for title, body in items:
            rows.append([
                self._p(title, "table_cell_bold"),
                self._p(body, "table_cell"),
            ])
        table = Table(rows, colWidths=[40 * mm, 126 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), AMBER_LIGHT),
            ("GRID", (0, 0), (-1, -1), 0.45, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        return table

    def _footer(self, canvas, document) -> None:
        canvas.saveState()
        width, _ = A4
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(22 * mm, 15 * mm, width - 22 * mm, 15 * mm)
        canvas.setFont("Helvetica", 6.8)
        canvas.setFillColor(MUTED)
        canvas.drawString(22 * mm, 10.5 * mm, "Decisión de fuente de noticias - 1 de noviembre de 2026")
        canvas.drawRightString(width - 22 * mm, 10.5 * mm, f"{document.page}")
        canvas.restoreState()

    def build(self) -> Path:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        document = SimpleDocTemplate(
            str(self.output_path),
            pagesize=A4,
            leftMargin=22 * mm,
            rightMargin=22 * mm,
            topMargin=19 * mm,
            bottomMargin=21 * mm,
            title="Decisión de fuente de noticias: FNSPID frente a EODHD",
            author="Proyecto sec-risk-intelligence",
            subject="Justificación metodológica de la fuente principal de noticias",
        )

        story = [
            self._p("NOTA DE DECISIÓN METODOLÓGICA", "kicker"),
            self._p("FNSPID frente a EODHD", "title"),
            self._p(
                "Justificación de la fuente principal de noticias para el análisis longitudinal de riesgos en las Magnificent Seven.",
                "subtitle",
            ),
            Table(
                [[
                    self._p("Decisión", "decision_title"),
                    self._p(
                        "Adoptar <b>EODHD como fuente principal</b>, complementada con una búsqueda dirigida para episodios locales. "
                        "Descartar FNSPID como pipeline principal por su cobertura temporal y empresarial insuficiente.",
                        "decision_body",
                    ),
                ]],
                colWidths=[27 * mm, 139 * mm],
                style=TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), BLUE),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 9),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                    ("LINEAFTER", (0, 0), (0, 0), 0.7, colors.HexColor("#7CA0C5")),
                ]),
            ),
            Spacer(1, 10),
            self._metric_cards(),
            Spacer(1, 13),
            self._p("Evidencia comparativa", "section"),
            self._comparison_table(),
            Spacer(1, 9),
            self._callout(
                "El volumen de FNSPID no compensa sus huecos",
                "FNSPID procesó 28,6 millones de filas y produjo 56.736 asociaciones empresa-noticia, pero no existe un solo año con artículos para las siete compañías. "
                "Meta tiene 432 registros y cero artículos; Apple carece de 2021 y Microsoft solo dispone de artículos en 2022-2023. "
                "El segundo CSV, de 5,73 GB, no añadió ninguna noticia Mag7 única.",
                RED_LIGHT,
            ),
            Spacer(1, 11),
            self._p("Ventaja decisiva", "section"),
            self._p(
                "En seis episodios conocidos y revisados humanamente, EODHD recuperó cinco (83,3 %) y los cinco disponían de "
                "contenido útil. Bajo el filtro del notebook, FNSPID no podría recuperar al menos tres de esos seis casos: Apple-NSO de "
                "2021 y los dos episodios de Microsoft de 2024. Esto no prueba un recall global, pero sí establece una diferencia "
                "práctica suficiente para la elección de fuente.",
                "body",
            ),
            self._callout(
                "Cautela metodológica",
                "Los ceros de FNSPID significan ausencia de noticias recuperadas mediante Stock_symbol, no ausencia de acontecimientos. "
                "Buscar nombres en los 9,8 millones de filas sin ticker podría recuperar registros adicionales, pero no resolvería el corte en 2023 ni la discontinuidad observada. "
                "Por ello no se recomienda invertir más desarrollo en FNSPID como fuente principal.",
                BLUE_LIGHT,
            ),
            PageBreak(),
            self._p("ALCANCE DE LA DECISIÓN", "kicker"),
            self._p("Condiciones para adoptar EODHD", "title"),
            self._p(
                "EODHD ofrece la mejor base disponible en el proyecto, pero debe utilizarse con controles explícitos de cobertura, revisión humana, consumo y derechos de uso.",
                "subtitle",
            ),
            self._p("Limitaciones que deben acompañar a EODHD", "section"),
            self._limitations_table(),
            Spacer(1, 12),
            self._p("Decisión aplicada al proyecto", "section"),
            KeepTogether([
                self._callout(
                    "1. Fuente principal",
                    "EODHD para adquisición, normalización, deduplicación y construcción del dataset de cybersecurity y critical_suppliers.",
                    TEAL_LIGHT,
                ),
                Spacer(1, 5),
                self._callout(
                    "2. Complemento dirigido",
                    "Otra fuente para sucesos locales o con asociación deficiente al ticker, como la huelga de IF Metall en Suecia.",
                    PAPER,
                ),
                Spacer(1, 5),
                self._callout(
                    "3. Papel residual de FNSPID",
                    "Conservarlo únicamente como contraste metodológico o fuente auxiliar puntual para 2022-2023; no como base del dataset longitudinal.",
                    RED_LIGHT,
                ),
            ]),
            Spacer(1, 12),
            Table(
                [[self._p(
                    "“Se descarta FNSPID como fuente principal porque su gran volumen nominal no se traduce en cobertura temporal, empresarial ni documental suficiente. "
                    "EODHD ofrece una base más actual, auditable y validada por episodios, aunque debe utilizarse con revisión humana y una fuente complementaria.”",
                    "quote",
                )]],
                colWidths=[166 * mm],
                style=TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), BLUE_LIGHT),
                    ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#AFC5DB")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 9),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                    ("TOPPADDING", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ]),
            ),
            Spacer(1, 9),
            self._p(
                "Fuentes internas: notebooks/mag7_fnspid_news.ipynb; reports/eodhd_known_episode_recovery.md; "
                "reports/eodhd_candidate_filter_human_review.md; "
                "data/processed/eodhd_mag7/datasets/mag7-risk-train-2021-2026-bf1/dataset_manifest.json.",
                "small",
            ),
        ]

        document.build(story, onFirstPage=self._footer, onLaterPages=self._footer)
        return self.output_path


if __name__ == "__main__":
    print(NewsSourceDecisionPdf().build())
