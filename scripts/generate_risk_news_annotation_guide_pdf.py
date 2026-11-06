"""Generate the two-page risk-news annotation guide PDF."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
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
OUTPUT_PATH = PROJECT_ROOT / "output/pdf/risk_news_annotation_guide.pdf"

NAVY = colors.HexColor("#193651")
TEAL = colors.HexColor("#0C807C")
TEAL_LIGHT = colors.HexColor("#EAF4F4")
INK = colors.HexColor("#21354A")
MUTED = colors.HexColor("#5B6C7C")
GRID = colors.HexColor("#C9D7E2")
ROW_ALT = colors.HexColor("#F3F6F9")
AMBER = colors.HexColor("#E7A33E")
AMBER_LIGHT = colors.HexColor("#FFF5E7")


class RiskNewsAnnotationGuidePdf:
    """Build the compact operational guide used during calibration."""

    def __init__(self, output_path: Path = OUTPUT_PATH) -> None:
        self.output_path = output_path
        self.styles = self._create_styles()

    @staticmethod
    def _create_styles() -> dict[str, ParagraphStyle]:
        body = ParagraphStyle(
            "Body",
            fontName="Helvetica",
            fontSize=8.1,
            leading=10.6,
            textColor=INK,
            spaceAfter=4,
        )
        return {
            "kicker": ParagraphStyle(
                "Kicker",
                fontName="Helvetica-Bold",
                fontSize=8.3,
                leading=10,
                textColor=TEAL,
                spaceAfter=5,
            ),
            "title": ParagraphStyle(
                "Title",
                fontName="Helvetica-Bold",
                fontSize=21,
                leading=22,
                textColor=NAVY,
                spaceAfter=7,
            ),
            "section": ParagraphStyle(
                "Section",
                fontName="Helvetica-Bold",
                fontSize=11.5,
                leading=13,
                textColor=NAVY,
                spaceBefore=3,
                spaceAfter=5,
            ),
            "body": body,
            "body_tight": ParagraphStyle(
                "BodyTight",
                parent=body,
                fontSize=7.8,
                leading=9.8,
                spaceAfter=2,
            ),
            "small": ParagraphStyle(
                "Small",
                parent=body,
                fontSize=7.2,
                leading=8.8,
                textColor=MUTED,
                spaceAfter=2,
            ),
            "meta": ParagraphStyle(
                "Meta",
                parent=body,
                fontSize=7.4,
                leading=9,
                spaceAfter=0,
            ),
            "table_header": ParagraphStyle(
                "TableHeader",
                fontName="Helvetica-Bold",
                fontSize=7.4,
                leading=9,
                textColor=colors.white,
            ),
            "table_cell": ParagraphStyle(
                "TableCell",
                parent=body,
                fontSize=7.1,
                leading=8.8,
                spaceAfter=0,
            ),
            "table_cell_bold": ParagraphStyle(
                "TableCellBold",
                parent=body,
                fontName="Helvetica-Bold",
                fontSize=7.1,
                leading=8.8,
                spaceAfter=0,
            ),
            "code": ParagraphStyle(
                "Code",
                fontName="Courier",
                fontSize=7.1,
                leading=9.2,
                textColor=MUTED,
                leftIndent=8,
                bulletIndent=0,
                spaceAfter=2,
            ),
            "callout_label": ParagraphStyle(
                "CalloutLabel",
                fontName="Helvetica-Bold",
                fontSize=7.5,
                leading=9,
                textColor=TEAL,
            ),
            "callout_body": ParagraphStyle(
                "CalloutBody",
                parent=body,
                fontSize=7.5,
                leading=9.4,
                spaceAfter=0,
            ),
            "number": ParagraphStyle(
                "Number",
                fontName="Helvetica-Bold",
                fontSize=8,
                leading=10,
                textColor=TEAL,
            ),
        }

    def _p(self, text: str, style: str = "body") -> Paragraph:
        return Paragraph(text, self.styles[style])

    def _section(self, title: str) -> Paragraph:
        return self._p(title, "section")

    def _table(
        self,
        rows: list[list[str | Paragraph]],
        widths: list[float],
        *,
        header: bool = True,
        teal_grid: bool = False,
        compact: bool = False,
    ) -> Table:
        converted: list[list[Paragraph]] = []
        for row_number, row in enumerate(rows):
            converted_row = []
            for cell in row:
                if isinstance(cell, Paragraph):
                    converted_row.append(cell)
                else:
                    style = "table_header" if header and row_number == 0 else "table_cell"
                    converted_row.append(self._p(cell, style))
            converted.append(converted_row)

        line_color = TEAL if teal_grid else GRID
        table = Table(converted, colWidths=widths, repeatRows=1 if header else 0)
        commands = [
            ("GRID", (0, 0), (-1, -1), 0.45, line_color),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 3 if compact else 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3 if compact else 4),
        ]
        if header:
            commands.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
            first_body_row = 1
        else:
            first_body_row = 0
        for row_number in range(first_body_row, len(rows)):
            if (row_number - first_body_row) % 2 == 1:
                commands.append(("BACKGROUND", (0, row_number), (-1, row_number), ROW_ALT))
        table.setStyle(TableStyle(commands))
        return table

    def _callout(
        self,
        label: str,
        body: str,
        *,
        amber: bool = False,
        widths: tuple[float, float] = (31 * mm, 135 * mm),
    ) -> Table:
        background = AMBER_LIGHT if amber else TEAL_LIGHT
        border = AMBER if amber else TEAL
        table = Table(
            [[self._p(label, "callout_label"), self._p(body, "callout_body")]],
            colWidths=list(widths),
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), background),
                    ("BOX", (0, 0), (-1, -1), 0.65, border),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        return table

    def _numbered_steps(self) -> Table:
        steps = [
            ("1", "<b>Leer</b> el título y el contenido disponible. Si no basta, abrir <font name='Courier'>link</font> o consultar la caché restringida."),
            ("2", "<b>Comprobar la empresa.</b> El hecho debe afectarla o exponerla realmente; una mención como cliente, proveedor, competidor o ejemplo no basta."),
            ("3", "<b>Decidir relevancia.</b> Usar <font name='Courier'>true</font> cuando exista un riesgo concreto y respaldado; <font name='Courier'>false</font> para ruido, otra empresa o una mención insuficiente."),
            ("4", "<b>No forzar casos dudosos.</b> Si la evidencia no permite decidir, mantener <font name='Courier'>review_status=pending</font> y remitir la fila al grupo."),
            ("5", "<b>Completar la etiqueta.</b> En positivos, confirmar familia y estado; en negativos, indicar el tipo de ruido. Añadir revisor y nota antes de marcar <font name='Courier'>reviewed</font>."),
        ]
        rows = [[self._p(number, "number"), self._p(text, "body_tight")] for number, text in steps]
        table = Table(rows, colWidths=[5 * mm, 161 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ]
            )
        )
        return table

    def _bullet_list(self, items: list[str]) -> Table:
        rows = [[self._p("&#8226;", "number"), self._p(item, "body_tight")] for item in items]
        table = Table(rows, colWidths=[5 * mm, 161 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 0.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5),
                ]
            )
        )
        return table

    def _draw_header_footer(self, canvas, document) -> None:
        canvas.saveState()
        width, height = A4
        canvas.setFillColor(NAVY)
        canvas.rect(0, height - 20 * mm, width, 20 * mm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(20 * mm, height - 12.5 * mm, "SEC RISK INTELLIGENCE")

        canvas.setStrokeColor(GRID)
        canvas.setLineWidth(0.6)
        canvas.line(20 * mm, 14 * mm, width - 20 * mm, 14 * mm)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 6.8)
        canvas.drawString(20 * mm, 9 * mm, "Guía de anotación de noticias de riesgo - versión 1.0")
        canvas.drawRightString(width - 20 * mm, 9 * mm, f"Página {document.page}")
        canvas.restoreState()

    def _page_one(self) -> list:
        risk_rows = [
            ["Valor", "Criterio de aplicación"],
            ["<b>cybersecurity</b>", "Ataque, intrusión, ransomware, malware, acceso no autorizado, filtración o incidente de seguridad que afecte o exponga de forma concreta a la empresa, sus sistemas, datos, productos o usuarios. Privacidad, regulación, litigios o venta de seguridad no bastan por sí solos."],
            ["<b>critical_suppliers</b>", "Dependencia o fallo material de un proveedor, fabricante, componente, servicio cloud, software crítico u otra dependencia externa. Incluye escasez, interrupción, cierre, actualización defectuosa o capacidad restringida con vínculo concreto; no una escasez sectorial genérica."],
            ["<b>materialized</b>", "El incidente o impacto ya ha ocurrido."],
            ["<b>exposure</b>", "Existe una dependencia o vulnerabilidad real, aunque el daño aún no se haya materializado."],
            ["<b>emerging</b>", "Amenaza nueva y respaldada por hechos que está desarrollándose; no una hipótesis genérica."],
        ]

        calibration_rows = [
            [self._p("EMPRESAS", "callout_label"), self._p("FAMILIAS DESIGNADAS", "callout_label"), self._p("PERIODO", "callout_label")],
            ["<b>10</b> por empresa", "<b>20</b> critical_suppliers + <b>20</b> cybersecurity", "<b>2021-2026</b>"],
            [self._p("CONTENIDO", "callout_label"), self._p("DUPLICADOS", "callout_label"), self._p("SEMILLA FIJA", "callout_label")],
            ["<b>25</b> full | <b>8</b> partial | <b>7</b> summary_only", "<b>16</b> relaciones en grupos de duplicados", "<font name='Courier'>mag7-risk-calibration-2021-2026-v1</font>"],
        ]

        event_rows = [
            ["MATERIALIZED", "EXPOSURE", "EMERGING"],
            ["<b>El hecho o impacto ya ocurrió.</b><br/>Brecha confirmada, interrupción o daño efectivo.", "<b>Dependencia o vulnerabilidad actual.</b><br/>Todavía no se describe incidente ni daño.", "<b>Amenaza nueva y específica en desarrollo.</b><br/>Creíble, pero aún sin impacto materializado."],
        ]

        return [
            self._p("GUÍA OPERATIVA - DATASET DE ENTRENAMIENTO", "kicker"),
            self._p("Anotación de noticias de riesgo", "title"),
            self._table(
                [["<b>Unidad:</b> relación noticia-empresa", "<b>Archivo:</b> risk_news_candidates_review.csv", "<b>Familias:</b> cybersecurity - critical_suppliers"]],
                [44 * mm, 66 * mm, 56 * mm],
                header=False,
                compact=True,
            ),
            Spacer(1, 5),
            self._section("Objetivo"),
            self._p(
                "Decidir si una noticia describe un riesgo, exposición o acontecimiento adverso real para la empresa indicada y, en caso afirmativo, confirmar la familia correcta. <b>El filtro solo propone candidatos:</b> una coincidencia léxica o la familia sugerida no constituyen una etiqueta válida."
            ),
            self._callout(
                "REGLA DE<br/>INDEPENDENCIA",
                "Evaluar primero la noticia sin consultar el 10-K asociado. Así se evita condicionar la etiqueta y se conserva una comparación posterior limpia entre noticia y riesgo previo.",
                amber=True,
            ),
            Spacer(1, 4),
            self._section("Decisión por fila"),
            self._numbered_steps(),
            Spacer(1, 2),
            self._section("Familias y estado del riesgo"),
            self._table(risk_rows, [33 * mm, 133 * mm], compact=True),
            Spacer(1, 5),
            self._p(
                "En <font name='Courier'>confirmed_risk_families</font> <b>usar exactamente</b> <font name='Courier'>cybersecurity</font>, <font name='Courier'>critical_suppliers</font> o <font name='Courier'>cybersecurity|critical_suppliers</font>. <b>Puede diferir de la familia propuesta.</b>",
                "body_tight",
            ),
            Spacer(1, 8),
            self._section("Muestra común de calibración (40 noticias)"),
            self._p("Las tres copias contienen las mismas relaciones y el mismo orden; solo cambia el revisor preasignado.", "body_tight"),
            self._table(calibration_rows, [55 * mm, 55 * mm, 56 * mm], header=False, teal_grid=True, compact=True),
            self._table(
                [
                    ["<b>Copias:</b> calibration_sample_40_javi.csv | calibration_sample_40_hugo.csv | calibration_sample_40_higinio.csv"],
                    ["<b>Trabajo independiente:</b> cada miembro anota solo su copia y no consulta las demás hasta completar las 40 filas. La selección, el algoritmo y los hashes se conservan en calibration_sample_40_manifest.json."],
                ],
                [166 * mm],
                header=False,
                teal_grid=True,
                compact=True,
            ),
            Spacer(1, 4),
            self._section("Cómo usar event_status"),
            self._p("Solo en positivos. Prioridad: impacto ocurrido &gt; exposición actual &gt; amenaza nueva respaldada. Una hipótesis genérica es negativa.", "small"),
            self._table(event_rows, [55.3 * mm] * 3, teal_grid=True, compact=True),
        ]

    def _page_two(self) -> list:
        completion_rows = [
            ["Resultado", "Campos que deben completarse"],
            ["<b>Positivo</b>", "<font name='Courier'>relevant_risk_news=true</font>; <font name='Courier'>company_relevance=true</font>; <font name='Courier'>event_status</font>; <font name='Courier'>confirmed_risk_families</font>; <font name='Courier'>reviewer</font>; <font name='Courier'>notes</font>. Dejar <font name='Courier'>noise_type</font> vacío."],
            ["<b>Negativo</b>", "<font name='Courier'>relevant_risk_news=false</font>; <font name='Courier'>company_relevance=true</font>, <font name='Courier'>false</font> o <font name='Courier'>unclear</font>; <font name='Courier'>noise_type</font>; <font name='Courier'>reviewer</font>; <font name='Courier'>notes</font>. Dejar vacíos los campos positivos."],
        ]
        company_rows = [
            ["VALOR", "CUÁNDO USARLO", "EJEMPLO DE RESULTADO"],
            ["<font name='Courier'><b>true</b></font>", "La empresa es protagonista, está afectada o presenta una exposición concreta.", "Puede combinarse con relevant_risk_news=true o false."],
            ["<font name='Courier'><b>false</b></font>", "La empresa solo se menciona o el riesgo corresponde realmente a otra entidad.", "Normalmente relevant_risk_news=false."],
            ["<font name='Courier'><b>unclear</b></font>", "El contenido no permite establecer con seguridad el vínculo empresarial.", "Si podría existir riesgo, mantener pending y escalar."],
        ]
        negative_cases = [
            "La noticia trata principalmente de otra empresa y la empresa objetivo solo aparece mencionada.",
            "Se invierte la relación comercial: ser cliente de un proveedor no prueba un fallo de suministro para la empresa objetivo.",
            "Se anuncia un producto o servicio de ciberseguridad sin incidente ni exposición concreta.",
            "El asunto es regulatorio, legal, de privacidad o competencia, sin componente real de ciberseguridad.",
            "Es análisis bursátil, recomendación, predicción o módulo editorial.",
            "Existe una escasez sectorial, pero no se demuestra un efecto o dependencia material para la empresa.",
        ]
        quality_items = [
            "<b>Calibración:</b> todos los miembros anotan de forma independiente las mismas 30-50 filas y después resuelven discrepancias por consenso.",
            "<b>Doble anotación:</b> revisar por dos personas una muestra del 10-20 %.",
            "<b>Gold:</b> la decisión final debe quedar confirmada por una persona. Las etiquetas generadas únicamente por IA se identifican como <i>silver labels</i>.",
            "<b>Procedencia:</b> no editar las columnas de <font name='Courier'>review_order</font> a <font name='Courier'>link</font>.",
        ]
        noise_lines = [
            "other_company   wrong_relationship_direction   sector_level_only",
            "product_or_service_promotion   stock_analysis   recommendation_widget",
            "regulatory_not_cyber   legal_not_cyber   privacy_compliance_not_cyber",
            "hypothetical   contextual_mention_insufficient   lexical_ambiguity",
            "wrong_risk_family   demand_not_supplier_failure",
        ]

        return [
            self._p("CAMPOS, CASOS DE RUIDO Y CONTROL DE CALIDAD", "kicker"),
            self._p("Cómo completar la hoja", "title"),
            self._table(completion_rows, [27 * mm, 139 * mm], compact=True),
            Spacer(1, 5),
            self._section("Tipos de ruido"),
            self._p("Usar una categoría existente. Si ninguna encaja, acordar un valor común antes de crear otro:", "body_tight"),
            *[self._p(f"&#8226;&nbsp;&nbsp;{line}", "code") for line in noise_lines],
            self._callout(
                "RECOMMENDATION_WIDGET",
                "Usar cuando la coincidencia proceda de titulares, enlaces o bloques automáticos como «Most Read», «Related Articles» o «Recommended», y no del contenido principal de la noticia.",
                widths=(43 * mm, 123 * mm),
            ),
            Spacer(1, 4),
            self._section("Casos que suelen ser negativos"),
            self._bullet_list(negative_cases),
            Spacer(1, 3),
            self._callout(
                "DUPLICADOS",
                "Una publicación duplicada o sindicada no es negativa por ser duplicada. Debe recibir la misma decisión semántica y controlarse después mediante los grupos de duplicados o eventos.",
            ),
            Spacer(1, 4),
            self._section("Notas y control de calidad"),
            self._p(
                "En <font name='Courier'>notes</font>, escribir una justificación breve y basada en evidencia. Ejemplo: «La noticia confirma una interrupción del proveedor X que reduce la producción de la empresa; riesgo materializado de critical_suppliers». No copiar cuerpos completos ni información de los 10-K.",
                "body_tight",
            ),
            self._bullet_list(quality_items),
            Spacer(1, 4),
            self._section("Cómo usar company_relevance"),
            self._p("Responde si el hecho se atribuye a la empresa de la fila, no si pertenece a una familia objetivo.", "small"),
            self._table(company_rows, [22 * mm, 80 * mm, 64 * mm], teal_grid=True, compact=True),
            self._table(
                [["<b>Combinaciones clave:</b> true + false es válido cuando la noticia sí trata de la empresa pero no describe un riesgo objetivo; false + false corresponde a otra empresa o relación invertida. Toda fila positiva debe tener company_relevance=true."]],
                [166 * mm],
                header=False,
                teal_grid=True,
                compact=True,
            ),
        ]

    def build(self) -> Path:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        document = SimpleDocTemplate(
            str(self.output_path),
            pagesize=A4,
            leftMargin=22 * mm,
            rightMargin=22 * mm,
            topMargin=27 * mm,
            bottomMargin=19 * mm,
            title="Guía de anotación de noticias de riesgo",
            author="Proyecto sec-risk-intelligence",
            subject="Criterios operativos para la calibración del dataset de noticias",
        )
        story = [*self._page_one(), PageBreak(), *self._page_two()]
        document.build(
            story,
            onFirstPage=self._draw_header_footer,
            onLaterPages=self._draw_header_footer,
        )
        return self.output_path


if __name__ == "__main__":
    print(RiskNewsAnnotationGuidePdf().build())
