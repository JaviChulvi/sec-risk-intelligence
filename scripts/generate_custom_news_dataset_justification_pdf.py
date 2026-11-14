"""Generate a one-page methodological justification for the custom news dataset."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "output/pdf/justificacion_dataset_noticias_revision_humana.pdf"

NAVY = colors.HexColor("#173653")
BLUE = colors.HexColor("#2D648C")
TEAL = colors.HexColor("#0C7A73")
TEAL_LIGHT = colors.HexColor("#E8F4F2")
INK = colors.HexColor("#203345")
MUTED = colors.HexColor("#5D6D7B")
LINE = colors.HexColor("#CBD7E1")
PAPER = colors.HexColor("#F4F7F9")
AMBER = colors.HexColor("#9B6818")
AMBER_LIGHT = colors.HexColor("#FFF4DE")
RED_LIGHT = colors.HexColor("#FCEDEB")


class CustomNewsDatasetJustificationPdf:
    """Build the one-page methodological note."""

    def __init__(self, output_path: Path = OUTPUT_PATH) -> None:
        self.output_path = output_path
        self.styles = self._styles()

    @staticmethod
    def _styles() -> dict[str, ParagraphStyle]:
        body = ParagraphStyle(
            "Body",
            fontName="Helvetica",
            fontSize=8.15,
            leading=10.7,
            textColor=INK,
            spaceAfter=0,
        )
        return {
            "kicker": ParagraphStyle(
                "Kicker",
                fontName="Helvetica-Bold",
                fontSize=7.6,
                leading=9,
                textColor=TEAL,
                spaceAfter=4,
            ),
            "title": ParagraphStyle(
                "Title",
                fontName="Helvetica-Bold",
                fontSize=21,
                leading=22.5,
                textColor=NAVY,
                spaceAfter=5,
            ),
            "subtitle": ParagraphStyle(
                "Subtitle",
                fontName="Helvetica",
                fontSize=9.1,
                leading=12.3,
                textColor=MUTED,
                spaceAfter=9,
            ),
            "section": ParagraphStyle(
                "Section",
                fontName="Helvetica-Bold",
                fontSize=11,
                leading=13,
                textColor=NAVY,
                spaceBefore=1,
                spaceAfter=5,
            ),
            "body": body,
            "body_small": ParagraphStyle(
                "BodySmall",
                parent=body,
                fontSize=7.45,
                leading=9.5,
            ),
            "decision_label": ParagraphStyle(
                "DecisionLabel",
                fontName="Helvetica-Bold",
                fontSize=8,
                leading=10,
                textColor=colors.white,
            ),
            "decision": ParagraphStyle(
                "Decision",
                fontName="Helvetica-Bold",
                fontSize=10.2,
                leading=13,
                textColor=colors.white,
            ),
            "metric_value": ParagraphStyle(
                "MetricValue",
                fontName="Helvetica-Bold",
                fontSize=15.5,
                leading=17,
                textColor=NAVY,
                alignment=TA_CENTER,
                spaceAfter=2,
            ),
            "metric_label": ParagraphStyle(
                "MetricLabel",
                fontName="Helvetica",
                fontSize=6.9,
                leading=8.5,
                textColor=MUTED,
                alignment=TA_CENTER,
            ),
            "table_header": ParagraphStyle(
                "TableHeader",
                fontName="Helvetica-Bold",
                fontSize=7.3,
                leading=8.8,
                textColor=colors.white,
            ),
            "table_key": ParagraphStyle(
                "TableKey",
                fontName="Helvetica-Bold",
                fontSize=7.15,
                leading=8.8,
                textColor=INK,
            ),
            "table_cell": ParagraphStyle(
                "TableCell",
                fontName="Helvetica",
                fontSize=7.05,
                leading=8.75,
                textColor=INK,
            ),
            "callout_label": ParagraphStyle(
                "CalloutLabel",
                fontName="Helvetica-Bold",
                fontSize=8,
                leading=10,
                textColor=AMBER,
            ),
            "callout": ParagraphStyle(
                "Callout",
                fontName="Helvetica",
                fontSize=7.65,
                leading=9.7,
                textColor=INK,
            ),
            "evidence_value": ParagraphStyle(
                "EvidenceValue",
                fontName="Helvetica-Bold",
                fontSize=16,
                leading=17,
                textColor=TEAL,
                alignment=TA_CENTER,
            ),
            "evidence": ParagraphStyle(
                "Evidence",
                fontName="Helvetica",
                fontSize=7.5,
                leading=9.5,
                textColor=INK,
            ),
            "footer": ParagraphStyle(
                "Footer",
                fontName="Helvetica",
                fontSize=6.2,
                leading=7.5,
                textColor=MUTED,
            ),
        }

    def _p(self, text: str, style: str) -> Paragraph:
        return Paragraph(text, self.styles[style])

    def _decision_band(self) -> Table:
        table = Table(
            [[
                self._p("DECISIÓN", "decision_label"),
                self._p(
                    "Usar fuentes externas para <b>adquirir noticias</b>, pero construir "
                    "internamente las <b>etiquetas de evaluación</b> mediante revisión humana.",
                    "decision",
                ),
            ]],
            colWidths=[24 * mm, 142 * mm],
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), NAVY),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEAFTER", (0, 0), (0, 0), 0.7, colors.HexColor("#7D9AB3")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        return table

    def _metric_cards(self) -> Table:
        data = [[
            [
                self._p("1", "metric_value"),
                self._p("unidad: relación noticia-empresa", "metric_label"),
            ],
            [
                self._p("2", "metric_value"),
                self._p("familias objetivo definidas operacionalmente", "metric_label"),
            ],
            [
                self._p("40 x 3", "metric_value"),
                self._p("casos comunes para calibración independiente", "metric_label"),
            ],
        ]]
        table = Table(data, colWidths=[55.3 * mm] * 3)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), PAPER),
            ("BOX", (0, 0), (-1, -1), 0.55, LINE),
            ("INNERGRID", (0, 0), (-1, -1), 0.55, colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        return table

    def _comparison_table(self) -> Table:
        rows = [
            ["Criterio", "Dataset externo sin adaptar", "Dataset propio revisado"],
            [
                "Alineación",
                "Suele responder a otra tarea: tema, sentimiento, entidad o evento genérico.",
                "Etiqueta exactamente riesgo relevante, familia y estado del acontecimiento.",
            ],
            [
                "Unidad",
                "Artículo o evento; puede perder qué empresa está realmente afectada.",
                "Relación noticia-empresa: una noticia puede ser positiva para una empresa y ruido para otra.",
            ],
            [
                "Ámbito",
                "Empresas, periodo y taxonomía fijados por terceros.",
                "MAG7, 2021-2026 y familias <i>cybersecurity</i> y <i>critical_suppliers</i>.",
            ],
            [
                "Calidad",
                "Criterios, duplicados, procedencia o cambios de etiqueta pueden ser opacos.",
                "Guía explícita, hashes, grupos de duplicados y trazabilidad hasta la fuente.",
            ],
            [
                "Validez",
                "Una etiqueta disponible no equivale automáticamente a un <i>gold standard</i> para esta pregunta.",
                "Calibración independiente, comparación de desacuerdos y adjudicación por consenso.",
            ],
        ]
        converted = []
        for row_number, row in enumerate(rows):
            if row_number == 0:
                converted.append([self._p(cell, "table_header") for cell in row])
            else:
                converted.append([
                    self._p(row[0], "table_key"),
                    self._p(row[1], "table_cell"),
                    self._p(row[2], "table_cell"),
                ])
        table = Table(converted, colWidths=[28 * mm, 67 * mm, 71 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("BACKGROUND", (0, 1), (0, -1), PAPER),
            ("BACKGROUND", (1, 1), (1, -1), RED_LIGHT),
            ("BACKGROUND", (2, 1), (2, -1), TEAL_LIGHT),
            ("GRID", (0, 0), (-1, -1), 0.45, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return table

    def _human_review_cards(self) -> Table:
        data = [[
            [
                self._p("CONTEXTO EMPRESARIAL", "callout_label"),
                self._p(
                    "Distingue una empresa realmente afectada de una mención, un competidor o una relación comercial invertida.",
                    "body_small",
                ),
            ],
            [
                self._p("SEMÁNTICA DEL RIESGO", "callout_label"),
                self._p(
                    "Confirma familia y separa impacto materializado, exposición vigente y amenaza emergente.",
                    "body_small",
                ),
            ],
            [
                self._p("CONTROL DE ETIQUETAS", "callout_label"),
                self._p(
                    "Hace visibles los desacuerdos, documenta el consenso y diferencia etiquetas <i>gold</i> de <i>silver</i>.",
                    "body_small",
                ),
            ],
        ]]
        table = Table(data, colWidths=[55.3 * mm] * 3)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), PAPER),
            ("BOX", (0, 0), (-1, -1), 0.5, LINE),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.white),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        return table

    def _evidence_box(self) -> Table:
        table = Table(
            [[
                self._p("21 / 57", "evidence_value"),
                self._p(
                    "candidatos léxicos de la muestra de 2026 fueron noticias de riesgo positivas "
                    "tras la revisión humana. Los otros 36 (63,2%) eran ruido: una coincidencia "
                    "léxica no constituye una etiqueta válida. <b>Métrica de desarrollo; no estima recall.</b>",
                    "evidence",
                ),
            ]],
            colWidths=[35 * mm, 131 * mm],
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), TEAL_LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.7, TEAL),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        return table

    def _balanced_callout(self) -> Table:
        table = Table(
            [[
                self._p("QUÉ SÍ REUTILIZAR", "callout_label"),
                self._p(
                    "Los datasets públicos siguen siendo útiles como fuente de noticias, "
                    "vocabulario, comparación o preentrenamiento. Deben incorporarse si superan "
                    "controles de licencia, cobertura, deduplicación y mapeo de etiquetas; no como "
                    "sustituto automático de la validación humana específica del proyecto.",
                    "callout",
                ),
            ]],
            colWidths=[35 * mm, 131 * mm],
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), AMBER_LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#E3C37F")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        return table

    def _footer(self, canvas, document) -> None:
        canvas.saveState()
        width, _ = A4
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(18 * mm, 13 * mm, width - 18 * mm, 13 * mm)
        canvas.setFont("Helvetica", 6.2)
        canvas.setFillColor(MUTED)
        canvas.drawString(
            18 * mm,
            8.7 * mm,
            "Base: guía de anotación, métricas de desarrollo y protocolo temporal del proyecto",
        )
        canvas.drawRightString(width - 18 * mm, 8.7 * mm, "SEC Risk Intelligence | 2026")
        canvas.restoreState()

    def build(self) -> Path:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        document = SimpleDocTemplate(
            str(self.output_path),
            pagesize=A4,
            leftMargin=22 * mm,
            rightMargin=22 * mm,
            topMargin=17 * mm,
            bottomMargin=18 * mm,
            title="Justificación del dataset propio de noticias con revisión humana",
            author="Proyecto sec-risk-intelligence",
            subject="Nota metodológica de una página",
        )
        story = [
            self._p("NOTA METODOLÓGICA | DATASET DE NOTICIAS DE RIESGO", "kicker"),
            self._p("Adquirir noticias fuera; construir las etiquetas dentro", "title"),
            self._p(
                "Por qué el análisis MAG7 2021-2026 necesita un dataset propio con revisión "
                "humana, en lugar de adoptar sin más un corpus encontrado en internet.",
                "subtitle",
            ),
            self._decision_band(),
            Spacer(1, 7),
            self._metric_cards(),
            Spacer(1, 9),
            self._p("La brecha metodológica", "section"),
            self._comparison_table(),
            Spacer(1, 8),
            self._evidence_box(),
            Spacer(1, 8),
            self._p("Qué aporta la revisión humana", "section"),
            self._human_review_cards(),
            Spacer(1, 8),
            self._balanced_callout(),
            Spacer(1, 7),
            Table(
                [[
                    self._p("ESTADO ACTUAL", "callout_label"),
                    self._p(
                        "La calibración de los tres anotadores sigue en curso. Hasta comparar "
                        "desacuerdos y resolverlos por consenso, las etiquetas no deben presentarse "
                        "como <i>gold standard</i> ni como estimación final de rendimiento.",
                        "callout",
                    ),
                ]],
                colWidths=[35 * mm, 131 * mm],
                style=TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), PAPER),
                    ("BOX", (0, 0), (-1, -1), 0.55, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]),
            ),
            Spacer(1, 5),
            self._p(
                "Fuentes internas: <font name='Courier'>reports/risk_news_annotation_guide.md</font> · "
                "<font name='Courier'>reports/eodhd_risk_news_development.md</font> · "
                "<font name='Courier'>config/eodhd_dataset_2021_2026.json</font>",
                "footer",
            ),
        ]
        document.build(story, onFirstPage=self._footer)
        return self.output_path


if __name__ == "__main__":
    print(CustomNewsDatasetJustificationPdf().build())
