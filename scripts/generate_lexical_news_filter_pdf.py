"""Generate a one-page explanation of the lexical risk-news filter."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "output/pdf/funcionamiento_filtro_lexico_noticias.pdf"

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


class LexicalNewsFilterPdf:
    """Build the compact technical explanation of RiskFamilyFilter."""

    def __init__(self, output_path: Path = OUTPUT_PATH) -> None:
        self.output_path = output_path
        self.styles = self._styles()

    @staticmethod
    def _styles() -> dict[str, ParagraphStyle]:
        body = ParagraphStyle(
            "Body",
            fontName="Helvetica",
            fontSize=8.05,
            leading=10.5,
            textColor=INK,
            spaceAfter=0,
        )
        return {
            "kicker": ParagraphStyle(
                "Kicker",
                fontName="Helvetica-Bold",
                fontSize=7.5,
                leading=9,
                textColor=TEAL,
                spaceAfter=4,
            ),
            "title": ParagraphStyle(
                "Title",
                fontName="Helvetica-Bold",
                fontSize=21.5,
                leading=23,
                textColor=NAVY,
                spaceAfter=5,
            ),
            "subtitle": ParagraphStyle(
                "Subtitle",
                fontName="Helvetica",
                fontSize=9.2,
                leading=12.3,
                textColor=MUTED,
                spaceAfter=9,
            ),
            "section": ParagraphStyle(
                "Section",
                fontName="Helvetica-Bold",
                fontSize=11.3,
                leading=13.2,
                textColor=NAVY,
                spaceBefore=1,
                spaceAfter=5,
            ),
            "body": body,
            "body_small": ParagraphStyle(
                "BodySmall",
                parent=body,
                fontSize=7.35,
                leading=9.35,
            ),
            "band_label": ParagraphStyle(
                "BandLabel",
                fontName="Helvetica-Bold",
                fontSize=7.8,
                leading=9.5,
                textColor=colors.white,
            ),
            "band": ParagraphStyle(
                "Band",
                fontName="Helvetica-Bold",
                fontSize=9.9,
                leading=12.5,
                textColor=colors.white,
            ),
            "metric_value": ParagraphStyle(
                "MetricValue",
                fontName="Helvetica-Bold",
                fontSize=15.5,
                leading=16.5,
                textColor=NAVY,
                alignment=TA_CENTER,
                spaceAfter=2,
            ),
            "metric_label": ParagraphStyle(
                "MetricLabel",
                fontName="Helvetica",
                fontSize=6.8,
                leading=8.4,
                textColor=MUTED,
                alignment=TA_CENTER,
            ),
            "number": ParagraphStyle(
                "Number",
                fontName="Helvetica-Bold",
                fontSize=12,
                leading=13,
                textColor=TEAL,
                alignment=TA_CENTER,
            ),
            "step_title": ParagraphStyle(
                "StepTitle",
                fontName="Helvetica-Bold",
                fontSize=8.05,
                leading=9.7,
                textColor=NAVY,
                spaceAfter=2,
            ),
            "step_body": ParagraphStyle(
                "StepBody",
                fontName="Helvetica",
                fontSize=7.25,
                leading=9.1,
                textColor=INK,
            ),
            "table_header": ParagraphStyle(
                "TableHeader",
                fontName="Helvetica-Bold",
                fontSize=7.2,
                leading=8.7,
                textColor=colors.white,
            ),
            "table_cell": ParagraphStyle(
                "TableCell",
                fontName="Helvetica",
                fontSize=7.15,
                leading=8.9,
                textColor=INK,
            ),
            "table_key": ParagraphStyle(
                "TableKey",
                fontName="Helvetica-Bold",
                fontSize=7.15,
                leading=8.9,
                textColor=INK,
            ),
            "code": ParagraphStyle(
                "Code",
                fontName="Courier",
                fontSize=6.9,
                leading=8.6,
                textColor=INK,
            ),
            "callout_label": ParagraphStyle(
                "CalloutLabel",
                fontName="Helvetica-Bold",
                fontSize=7.9,
                leading=9.5,
                textColor=AMBER,
            ),
            "callout": ParagraphStyle(
                "Callout",
                fontName="Helvetica",
                fontSize=7.55,
                leading=9.6,
                textColor=INK,
            ),
            "source": ParagraphStyle(
                "Source",
                fontName="Courier",
                fontSize=6.1,
                leading=7.5,
                textColor=MUTED,
            ),
        }

    def _p(self, text: str, style: str) -> Paragraph:
        return Paragraph(text, self.styles[style])

    def _purpose_band(self) -> Table:
        table = Table(
            [[
                self._p("FUNCIÓN", "band_label"),
                self._p(
                    "Recuperar candidatos de alta cobertura y explicar por qué se seleccionaron. "
                    "No es un clasificador final ni genera etiquetas <i>gold</i>.",
                    "band",
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
                self._p("0", "metric_value"),
                self._p("modelos entrenados o llamadas a un LLM", "metric_label"),
            ],
            [
                self._p("±180", "metric_value"),
                self._p("caracteres de contexto alrededor de la empresa", "metric_label"),
            ],
            [
                self._p("2", "metric_value"),
                self._p("familias objetivo del dataset principal", "metric_label"),
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

    def _pipeline(self) -> Table:
        steps = [
            (
                "1",
                "Normalizar texto",
                "Une título y cuerpo; convierte a minúsculas, sustituye puntuación por espacios y colapsa blancos.",
                "title + content -> normalized_text",
            ),
            (
                "2",
                "Acotar a la empresa",
                "Busca alias configurados (p. ej., Microsoft, Windows o Azure) y conserva ventanas de ±180 caracteres. Sin alias, no hay evidencia.",
                "company_alias_patterns",
            ),
            (
                "3",
                "Activar familias",
                "Aplica expresiones regulares etiquetadas. Una noticia puede activar varias familias y varios términos a la vez.",
                "risk_rules[family]",
            ),
            (
                "4",
                "Exigir adversidad",
                "Descarta todas las coincidencias si el contexto no contiene un patrón de ataque, fallo, interrupción, pérdida u otro daño.",
                "adverse_event_patterns",
            ),
            (
                "5",
                "Suprimir y registrar",
                "Resuelve ambigüedades conocidas y guarda familias candidatas y etiquetas activadoras para auditoría.",
                "risk_family_candidates + risk_match_terms",
            ),
        ]
        rows = [
            [
                self._p(number, "number"),
                [self._p(title, "step_title"), self._p(body, "step_body")],
                self._p(code, "code"),
            ]
            for number, title, body, code in steps
        ]
        table = Table(rows, colWidths=[11 * mm, 105 * mm, 50 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), TEAL_LIGHT),
            ("BACKGROUND", (2, 0), (2, -1), PAPER),
            ("GRID", (0, 0), (-1, -1), 0.45, LINE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return table

    def _example_table(self) -> Table:
        rows = [
            ["Etapa", "Resultado para el ejemplo Microsoft"],
            [
                "Texto",
                "“Global IT outage affects Microsoft Windows. A faulty update caused the outage; it was not a cyberattack.”",
            ],
            [
                "Coincidencias",
                "critical_suppliers: technology outage + software update failure; cybersecurity: cyberattack.",
            ],
            [
                "Supresión",
                "La negación y el vínculo update/outage eliminan cybersecurity cuando critical_suppliers también está presente.",
            ],
            [
                "Salida",
                "critical_suppliers, conservando los términos que justifican la selección.",
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
                ])
        table = Table(converted, colWidths=[29 * mm, 137 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BLUE),
            ("BACKGROUND", (0, 1), (0, -1), PAPER),
            ("GRID", (0, 0), (-1, -1), 0.45, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return table

    def _limits_callout(self) -> Table:
        table = Table(
            [[
                self._p("LÍMITE CLAVE", "callout_label"),
                self._p(
                    "El filtro reconoce patrones, no significado completo. Puede confundir otra "
                    "empresa, publicidad, regulación o una mención hipotética. La revisión humana "
                    "decide relevancia, corrige la familia, asigna el estado del riesgo y documenta "
                    "el ruido. Sus activaciones son candidatos, no verdad de terreno.",
                    "callout",
                ),
            ]],
            colWidths=[31 * mm, 135 * mm],
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), AMBER_LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#E1BF78")),
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
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 6.3)
        canvas.drawString(18 * mm, 8.7 * mm, "Filtro léxico de noticias | Selección auditable de candidatos")
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
            title="Funcionamiento del filtro léxico de noticias",
            author="Proyecto sec-risk-intelligence",
            subject="Explicación de RiskFamilyFilter y su papel en la revisión humana",
        )
        story = [
            self._p("NOTA TÉCNICA | PIPELINE DE NOTICIAS EODHD", "kicker"),
            self._p("Cómo funciona el filtro léxico de riesgo", "title"),
            self._p(
                "De una noticia normalizada a una relación noticia-empresa candidata para "
                "cybersecurity o critical_suppliers.",
                "subtitle",
            ),
            self._purpose_band(),
            Spacer(1, 7),
            self._metric_cards(),
            Spacer(1, 9),
            self._p("Pipeline de selección", "section"),
            self._pipeline(),
            Spacer(1, 9),
            self._p("Ejemplo de una ambigüedad resuelta", "section"),
            self._example_table(),
            Spacer(1, 8),
            self._limits_callout(),
            Spacer(1, 5),
            self._p(
                "Fuentes: src/news/risk_filter.py · src/news/normalize.py · "
                "config/eodhd_pilot.json · src/tests/test_news_risk_filter.py",
                "source",
            ),
        ]
        document.build(story, onFirstPage=self._footer)
        return self.output_path


if __name__ == "__main__":
    print(LexicalNewsFilterPdf().build())
