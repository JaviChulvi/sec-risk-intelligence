"""Generate the customer-concentration exclusion decision PDF."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "output/pdf/eodhd_customer_concentration_exclusion.pdf"

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
RED = colors.HexColor("#A4423D")
RED_LIGHT = colors.HexColor("#FCEDEB")


class CustomerConcentrationExclusionPdf:
    """Build a concise two-page decision note from the project report."""

    def __init__(self, output_path: Path = OUTPUT_PATH) -> None:
        self.output_path = output_path
        self.styles = self._styles()

    @staticmethod
    def _styles() -> dict[str, ParagraphStyle]:
        body = ParagraphStyle(
            "Body",
            fontName="Helvetica",
            fontSize=8.25,
            leading=11.1,
            textColor=INK,
            spaceAfter=5,
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
                fontSize=9.2,
                leading=12.2,
                textColor=MUTED,
                spaceAfter=10,
            ),
            "section": ParagraphStyle(
                "Section",
                fontName="Helvetica-Bold",
                fontSize=11.5,
                leading=13.5,
                textColor=NAVY,
                spaceBefore=2,
                spaceAfter=6,
            ),
            "body": body,
            "body_tight": ParagraphStyle(
                "BodyTight",
                parent=body,
                fontSize=7.7,
                leading=9.8,
                spaceAfter=2,
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
                fontSize=10.1,
                leading=13,
                textColor=colors.white,
            ),
            "metric_value": ParagraphStyle(
                "MetricValue",
                fontName="Helvetica-Bold",
                fontSize=16,
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
                fontSize=7.25,
                leading=8.8,
                textColor=colors.white,
            ),
            "table_cell": ParagraphStyle(
                "TableCell",
                fontName="Helvetica",
                fontSize=7.25,
                leading=9,
                textColor=INK,
            ),
            "table_key": ParagraphStyle(
                "TableKey",
                fontName="Helvetica-Bold",
                fontSize=7.25,
                leading=9,
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
                fontSize=7.75,
                leading=10,
                textColor=INK,
            ),
            "number": ParagraphStyle(
                "Number",
                fontName="Helvetica-Bold",
                fontSize=12,
                leading=13,
                textColor=TEAL,
                alignment=TA_CENTER,
            ),
            "card_title": ParagraphStyle(
                "CardTitle",
                fontName="Helvetica-Bold",
                fontSize=8.2,
                leading=10,
                textColor=NAVY,
                spaceAfter=3,
            ),
            "card_body": ParagraphStyle(
                "CardBody",
                fontName="Helvetica",
                fontSize=7.5,
                leading=9.7,
                textColor=INK,
            ),
            "source": ParagraphStyle(
                "Source",
                fontName="Courier",
                fontSize=6.35,
                leading=8.1,
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
                    "Excluir <font name='Courier'>customer_concentration</font> como clase "
                    "objetivo del dataset principal de noticias EODHD. Mantener "
                    "<font name='Courier'>cybersecurity</font> y "
                    "<font name='Courier'>critical_suppliers</font>.",
                    "decision",
                ),
            ]],
            colWidths=[25 * mm, 141 * mm],
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), NAVY),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEAFTER", (0, 0), (0, 0), 0.7, colors.HexColor("#7D9AB3")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ]))
        return table

    def _scope_callout(self) -> Table:
        table = Table(
            [[
                self._p("ALCANCE", "callout_label"),
                self._p(
                    "La exclusión afecta solo al experimento de noticias. La familia sigue siendo "
                    "válida en la taxonomía y en el análisis de los 10-K. Reglas, candidatos y "
                    "evidencias históricas se conservan para trazabilidad y exploración.",
                    "callout",
                ),
            ]],
            colWidths=[27 * mm, 139 * mm],
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

    def _metric_cards(self) -> Table:
        data = [[
            [
                self._p("13 / 13", "metric_value"),
                self._p("asignaciones de familia incorrectas en desarrollo", "metric_label"),
            ],
            [
                self._p("0", "metric_value"),
                self._p("episodios independientes elegibles en el benchmark", "metric_label"),
            ],
            [
                self._p("1 / 5", "metric_value"),
                self._p("familia confirmada en la muestra amplia de 2026", "metric_label"),
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
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        return table

    def _term_table(self) -> Table:
        rows = [
            ["Término", "Activaciones", "Falsos positivos", "Precisión observada"],
            ["major customer", "8", "7", "12,5 %"],
            ["key customer", "4", "4", "0,0 %"],
            ["customer concentration", "2", "2", "0,0 %"],
        ]
        converted = []
        for row_number, row in enumerate(rows):
            style = "table_header" if row_number == 0 else "table_cell"
            converted.append([self._p(cell, style) for cell in row])
        table = Table(converted, colWidths=[65 * mm, 30 * mm, 35 * mm, 36 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("BACKGROUND", (0, 1), (0, -1), PAPER),
            ("GRID", (0, 0), (-1, -1), 0.45, LINE),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return table

    def _acquisition_table(self) -> Table:
        rows = [
            ["Familia", "Candidatos léxicos"],
            ["cybersecurity", "36"],
            ["critical_suppliers", "16"],
            ["customer_concentration", "5"],
        ]
        converted = []
        for row_number, row in enumerate(rows):
            style = "table_header" if row_number == 0 else "table_cell"
            converted.append([self._p(cell, style) for cell in row])
        table = Table(converted, colWidths=[106 * mm, 60 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BLUE),
            ("BACKGROUND", (0, 1), (0, -1), PAPER),
            ("GRID", (0, 0), (-1, -1), 0.45, LINE),
            ("ALIGN", (1, 1), (1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return table

    def _problem_cards(self) -> Table:
        cards = [
            (
                "1",
                "Clase extremadamente minoritaria",
                "Cinco candidatos entre 9.861 relaciones (aprox. 0,05 %): volumen insuficiente para entrenamiento, validación y test separados.",
            ),
            (
                "2",
                "Evidencia positiva insuficiente",
                "Solo un caso confirmado en 2026; ninguno en el corpus de desarrollo y ningún episodio independiente para medir recuperación.",
            ),
            (
                "3",
                "Riesgo de aprender ruido",
                "Los términos major customer y key customer activan relaciones comerciales o menciones que no demuestran concentración de clientes.",
            ),
        ]
        rows = [
            [
                self._p(number, "number"),
                [self._p(title, "card_title"), self._p(body, "card_body")],
            ]
            for number, title, body in cards
        ]
        table = Table(rows, colWidths=[12 * mm, 154 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), TEAL_LIGHT),
            ("BACKGROUND", (1, 0), (1, -1), PAPER),
            ("GRID", (0, 0), (-1, -1), 0.45, LINE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        return table

    def _conditions_table(self) -> Table:
        items = [
            (
                "1",
                "Búsqueda dirigida",
                "Definir antes una estrategia adecuada para exposiciones estructurales, no solo noticias episódicas.",
            ),
            (
                "2",
                "Muestra humana suficiente",
                "Obtener positivos confirmados que permitan partición y evaluación separadas.",
            ),
            (
                "3",
                "Validez demostrable",
                "Probar precisión y relevancia empresarial, no solo coincidencias léxicas.",
            ),
            (
                "4",
                "Reglas congeladas",
                "Ajustar únicamente con entrenamiento y congelar las reglas antes de consultar validación o test.",
            ),
        ]
        rows = [
            [
                self._p(number, "number"),
                self._p(title, "card_title"),
                self._p(body, "card_body"),
            ]
            for number, title, body in items
        ]
        table = Table(rows, colWidths=[12 * mm, 44 * mm, 110 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), TEAL_LIGHT),
            ("BACKGROUND", (1, 0), (1, -1), PAPER),
            ("GRID", (0, 0), (-1, -1), 0.45, LINE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        return table

    def _final_callout(self) -> Table:
        table = Table(
            [[
                self._p("CONDICIÓN VIGENTE", "callout_label"),
                self._p(
                    "Hasta cumplir las cuatro condiciones, los cinco candidatos existentes se "
                    "mantienen como material exploratorio, no como ejemplos de una clase entrenable.",
                    "callout",
                ),
            ]],
            colWidths=[38 * mm, 128 * mm],
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), AMBER_LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#E1BF78")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        return table

    def _sources(self) -> Table:
        sources = [
            "reports/eodhd_risk_news_development.md",
            "reports/eodhd_reference_filter_report.md",
            "reports/eodhd_known_episode_recovery.md",
            "data/processed/eodhd_mag7/datasets/mag7-risk-train-2026-bf1/dataset_manifest.json",
            "data/processed/eodhd_mag7/datasets/mag7-risk-train-2026-bf1/risk_news_candidates_review.csv",
        ]
        rows = [[self._p("•", "body_tight"), self._p(source, "source")] for source in sources]
        table = Table(rows, colWidths=[5 * mm, 161 * mm])
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        return table

    def _footer(self, canvas, document) -> None:
        canvas.saveState()
        width, _ = A4
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(22 * mm, 14 * mm, width - 22 * mm, 14 * mm)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 6.6)
        canvas.drawString(22 * mm, 9.5 * mm, "Decisión customer_concentration | Consolidada 30/10/2026")
        canvas.drawRightString(width - 22 * mm, 9.5 * mm, f"Página {document.page} de 2")
        canvas.restoreState()

    def _page_one(self) -> list:
        return [
            self._p("NOTA DE DECISIÓN METODOLÓGICA | NOTICIAS EODHD", "kicker"),
            self._p("Exclusión de customer_concentration", "title"),
            self._p(
                "Evidencia, alcance y condiciones para excluir provisionalmente esta familia del "
                "dataset principal de noticias.",
                "subtitle",
            ),
            self._decision_band(),
            Spacer(1, 7),
            self._scope_callout(),
            Spacer(1, 10),
            self._metric_cards(),
            Spacer(1, 11),
            self._p("Evidencia del filtro de desarrollo", "section"),
            self._p(
                "Las 13 asignaciones de familia observadas fueron incorrectas. Las activaciones "
                "por término pueden solaparse y la precisión siguiente mide selección de noticias "
                "de riesgo; no confirma por sí sola que la familia propuesta fuera correcta.",
                "body",
            ),
            self._term_table(),
            Spacer(1, 10),
            self._p("Evidencia de cobertura", "section"),
            self._p(
                "El inventario auditado no contiene episodios independientes y elegibles de "
                "customer_concentration. En la adquisición amplia de enero-septiembre de 2026 se "
                "examinaron 9.861 relaciones artículo-empresa y se obtuvieron 57 candidatos.",
                "body",
            ),
            self._acquisition_table(),
            Spacer(1, 7),
            self._p(
                "Los cinco candidatos de customer_concentration equivalen a aproximadamente el "
                "0,05 % del universo admitido. La revisión humana confirmó uno en esa familia; "
                "otro pertenecía a critical_suppliers y tres fueron falsos positivos. Precisión "
                "de familia observada: <b>1/5 (20,0 %)</b>.",
                "body",
            ),
            Spacer(1, 8),
            self._p("Fuentes auditables", "section"),
            self._sources(),
        ]

    def _page_two(self) -> list:
        return [
            self._p("JUSTIFICACIÓN Y REAPERTURA", "kicker"),
            self._p("Por qué no es una clase entrenable hoy", "title"),
            self._p(
                "La concentración de clientes suele ser una exposición estructural, no un "
                "acontecimiento noticioso puntual. Los 10-K, cuentas anuales y publicaciones "
                "financieras específicas son fuentes más naturales para observarla.",
                "subtitle",
            ),
            self._p("Tres riesgos metodológicos", "section"),
            self._problem_cards(),
            Spacer(1, 10),
            Table(
                [[
                    self._p("VOLUMEN", "callout_label"),
                    self._p(
                        "La exclusión no resuelve el problema general de escala: el paquete pasa "
                        "de 57 a 52 candidatos. Aún es necesario revisar la precisión y mejorar "
                        "la recuperación de cybersecurity y critical_suppliers antes de considerar "
                        "alcanzable el tamaño objetivo.",
                        "callout",
                    ),
                ]],
                colWidths=[28 * mm, 138 * mm],
                style=TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), RED_LIGHT),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#D9A4A0")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]),
            ),
            Spacer(1, 12),
            self._p("Condiciones para reconsiderar la decisión", "section"),
            self._p(
                "La reapertura solo puede apoyarse en evidencia nueva obtenida sobre entrenamiento, "
                "sin utilizar validación ni test para ajustar reglas.",
                "body",
            ),
            self._conditions_table(),
            Spacer(1, 11),
            self._final_callout(),
        ]

    def build(self) -> Path:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        document = SimpleDocTemplate(
            str(self.output_path),
            pagesize=A4,
            leftMargin=22 * mm,
            rightMargin=22 * mm,
            topMargin=18 * mm,
            bottomMargin=20 * mm,
            title="Decisión sobre customer_concentration en noticias EODHD",
            author="Proyecto sec-risk-intelligence",
            subject="Exclusión provisional de una clase objetivo del dataset de noticias",
        )
        story = [*self._page_one(), PageBreak(), *self._page_two()]
        document.build(story, onFirstPage=self._footer, onLaterPages=self._footer)
        return self.output_path


if __name__ == "__main__":
    print(CustomerConcentrationExclusionPdf().build())
