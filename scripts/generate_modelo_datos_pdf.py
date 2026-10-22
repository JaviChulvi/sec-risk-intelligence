"""Generate the presentation views and data-model dictionary used in tutor meetings."""

from dataclasses import dataclass
from math import atan2, cos, sin
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    Flowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "modelo_datos_tfm_10k.pdf"


@dataclass(frozen=True)
class DiagramNode:
    key: str
    label: str
    subtitle: str
    x: float
    y: float
    fill: colors.Color
    width: float = 110
    height: float = 45


class EntityViewDiagram(Flowable):
    """Compact vector view of a subset of the entity model."""

    def __init__(
        self,
        nodes: list[DiagramNode],
        edges: list[tuple[str, str]],
        *,
        width: float = 503,
        height: float = 555,
    ) -> None:
        super().__init__()
        self.nodes = nodes
        self.edges = edges
        self.width = width
        self.height = height

    @staticmethod
    def _connection_points(
        source: DiagramNode,
        target: DiagramNode,
    ) -> tuple[float, float, float, float]:
        source_x = source.x + source.width / 2
        source_y = source.y + source.height / 2
        target_x = target.x + target.width / 2
        target_y = target.y + target.height / 2
        delta_x = target_x - source_x
        delta_y = target_y - source_y

        source_scale = 1 / max(
            abs(delta_x) / (source.width / 2),
            abs(delta_y) / (source.height / 2),
        )
        target_scale = 1 / max(
            abs(delta_x) / (target.width / 2),
            abs(delta_y) / (target.height / 2),
        )
        return (
            source_x + delta_x * source_scale,
            source_y + delta_y * source_scale,
            target_x - delta_x * target_scale,
            target_y - delta_y * target_scale,
        )

    def _draw_arrow(self, source: DiagramNode, target: DiagramNode) -> None:
        start_x, start_y, end_x, end_y = self._connection_points(source, target)
        self.canv.setStrokeColor(colors.HexColor("#8290A1"))
        self.canv.setLineWidth(0.75)
        self.canv.line(start_x, start_y, end_x, end_y)

        angle = atan2(end_y - start_y, end_x - start_x)
        arrow_size = 5
        left_x = end_x - arrow_size * cos(angle - 0.48)
        left_y = end_y - arrow_size * sin(angle - 0.48)
        right_x = end_x - arrow_size * cos(angle + 0.48)
        right_y = end_y - arrow_size * sin(angle + 0.48)
        path = self.canv.beginPath()
        path.moveTo(end_x, end_y)
        path.lineTo(left_x, left_y)
        path.lineTo(right_x, right_y)
        path.close()
        self.canv.setFillColor(colors.HexColor("#8290A1"))
        self.canv.drawPath(path, stroke=0, fill=1)

    def _draw_node(self, node: DiagramNode) -> None:
        self.canv.setFillColor(node.fill)
        self.canv.setStrokeColor(colors.HexColor("#637083"))
        self.canv.setLineWidth(0.75)
        self.canv.roundRect(
            node.x,
            node.y,
            node.width,
            node.height,
            6,
            stroke=1,
            fill=1,
        )

        label_lines = node.label.split("\n")
        label_size = 7.5 if len(label_lines) == 1 else 6.6
        while max(
            stringWidth(line, "Helvetica-Bold", label_size) for line in label_lines
        ) > node.width - 10:
            label_size -= 0.25
        self.canv.setFillColor(colors.HexColor("#182230"))
        self.canv.setFont("Helvetica-Bold", label_size)
        first_line_y = node.y + node.height / 2 + (7 if len(label_lines) > 1 else 4)
        for line_number, line in enumerate(label_lines):
            self.canv.drawCentredString(
                node.x + node.width / 2,
                first_line_y - line_number * 7,
                line,
            )

        self.canv.setFillColor(colors.HexColor("#596579"))
        self.canv.setFont("Helvetica", 5.6 if len(label_lines) > 1 else 5.9)
        self.canv.drawCentredString(
            node.x + node.width / 2,
            node.y + node.height / 2 - (11 if len(label_lines) > 1 else 7),
            node.subtitle,
        )

    def draw(self) -> None:
        node_by_key = {node.key: node for node in self.nodes}
        for source_key, target_key in self.edges:
            self._draw_arrow(node_by_key[source_key], node_by_key[target_key])
        for node in self.nodes:
            self._draw_node(node)


class DataModelPdfBuilder:
    def __init__(self, output_path: Path = OUTPUT_PATH) -> None:
        self.output_path = output_path
        self.styles = self._create_styles()

    @staticmethod
    def _create_styles() -> dict[str, ParagraphStyle]:
        cell = ParagraphStyle(
            "Cell",
            fontName="Helvetica",
            fontSize=7.0,
            leading=8.25,
            textColor=colors.HexColor("#222220"),
        )
        return {
            "title": ParagraphStyle(
                "Title",
                fontName="Helvetica-Bold",
                fontSize=16.5,
                leading=16.8,
                textColor=colors.HexColor("#20201E"),
                spaceAfter=2,
            ),
            "subtitle": ParagraphStyle(
                "Subtitle",
                fontName="Helvetica",
                fontSize=10.2,
                leading=11.2,
                textColor=colors.HexColor("#62615D"),
                spaceAfter=7,
            ),
            "header": ParagraphStyle(
                "Header",
                fontName="Helvetica-Bold",
                fontSize=8.7,
                leading=10.2,
                textColor=colors.white,
                alignment=TA_LEFT,
            ),
            "cell": cell,
            "entity": ParagraphStyle("Entity", parent=cell, fontName="Helvetica-Bold"),
            "section_title": ParagraphStyle(
                "SectionTitle",
                fontName="Helvetica-Bold",
                fontSize=9.4,
                leading=11,
                textColor=colors.HexColor("#2A2A27"),
                spaceAfter=4,
            ),
            "legend": ParagraphStyle(
                "Legend",
                fontName="Helvetica",
                fontSize=6.8,
                leading=8.0,
                textColor=colors.HexColor("#55544F"),
            ),
            "view_note": ParagraphStyle(
                "ViewNote",
                fontName="Helvetica",
                fontSize=7.4,
                leading=9.2,
                textColor=colors.HexColor("#596579"),
                borderColor=colors.HexColor("#D7DFEA"),
                borderWidth=0.5,
                borderPadding=6,
                backColor=colors.HexColor("#F7F9FC"),
                spaceBefore=3,
            ),
        }

    def _p(self, text: str, style: str) -> Paragraph:
        return Paragraph(text, self.styles[style])

    @staticmethod
    def _view_ingesta() -> EntityViewDiagram:
        raw = colors.HexColor("#E6EEF9")
        parsing = colors.HexColor("#E2F1F4")
        nodes = [
            DiagramNode("empresa", "EMPRESA", "CIK estable", 15, 455, raw),
            DiagramNode("informe", "INFORME / FILING", "accession_number", 196, 455, raw),
            DiagramNode("documento", "DOCUMENTO_FUENTE", "artefacto inmutable", 377, 455, raw),
            DiagramNode("version", "VERSION_PARSING", "código + configuración", 15, 300, parsing),
            DiagramNode("ejecucion", "EJECUCION_PARSING", "documento x versión", 196, 300, parsing),
            DiagramNode("seccion", "SECCION", "Item 1A, Item 7...", 377, 300, parsing),
            DiagramNode("parrafo", "PARRAFO", "posición estructural", 196, 145, parsing),
            DiagramNode("frase", "FRASE", "unidad mínima", 377, 145, parsing),
        ]
        edges = [
            ("empresa", "informe"),
            ("informe", "documento"),
            ("documento", "ejecucion"),
            ("version", "ejecucion"),
            ("ejecucion", "seccion"),
            ("seccion", "parrafo"),
            ("parrafo", "frase"),
        ]
        return EntityViewDiagram(nodes, edges)

    @staticmethod
    def _view_comparacion() -> EntityViewDiagram:
        raw = colors.HexColor("#E6EEF9")
        parsing = colors.HexColor("#E2F1F4")
        derived = colors.HexColor("#E4F2E8")
        longitudinal = colors.HexColor("#E9E4F4")
        analysis = colors.HexColor("#F1E8D8")
        output = colors.HexColor("#FDE9AD")
        nodes = [
            DiagramNode("parsing", "EJECUCION_PARSING", "entrada versionada", 5, 475, parsing),
            DiagramNode("modelo", "VERSION_MODELO", "familia técnica", 132, 475, analysis),
            DiagramNode("informe", "INFORME / FILING", "objetivo o referencia", 259, 475, raw),
            DiagramNode("frase", "FRASE", "texto procesado", 386, 475, parsing),
            DiagramNode("caracterizacion", "EJECUCION_\nCARACTERIZACION", "extracción reproducible", 5, 355, derived),
            DiagramNode("caracteristica", "CARACTERISTICA_\nFRASE", "ejecución x frase", 132, 355, derived),
            DiagramNode("representacion", "REPRESENTACION_\nINFORME", "agregación versionada", 259, 355, derived),
            DiagramNode("referencia", "COMPARACION_INFORME_\nREFERENCIA", "orden + peso", 386, 355, longitudinal),
            DiagramNode("comparacion", "COMPARACION", "objetivo + baseline", 5, 235, longitudinal),
            DiagramNode("analisis", "EJECUCION_ANALISIS", "comparación x modelo", 132, 235, analysis),
            DiagramNode("score", "SCORE", "salida cuantitativa", 259, 235, output),
            DiagramNode("hallazgo", "HALLAZGO", "riesgo detectado", 386, 235, output),
            DiagramNode("parrafo", "PARRAFO", "anclaje opcional", 259, 115, parsing),
            DiagramNode("evidencia", "EVIDENCIA_\nHALLAZGO", "trazabilidad textual", 386, 115, output),
        ]
        edges = [
            ("parsing", "caracterizacion"),
            ("modelo", "caracterizacion"),
            ("frase", "caracteristica"),
            ("caracterizacion", "caracteristica"),
            ("informe", "representacion"),
            ("caracterizacion", "representacion"),
            ("representacion", "score"),
            ("informe", "comparacion"),
            ("comparacion", "referencia"),
            ("informe", "referencia"),
            ("comparacion", "analisis"),
            ("modelo", "analisis"),
            ("analisis", "score"),
            ("analisis", "hallazgo"),
            ("hallazgo", "evidencia"),
            ("informe", "evidencia"),
            ("parrafo", "evidencia"),
        ]
        return EntityViewDiagram(nodes, edges)

    @staticmethod
    def _view_clustering_validation() -> EntityViewDiagram:
        longitudinal = colors.HexColor("#E9E4F4")
        analysis = colors.HexColor("#F1E8D8")
        output = colors.HexColor("#FDE9AD")
        grouping = colors.HexColor("#F8E2E2")
        validation = colors.HexColor("#E6E8F5")
        nodes = [
            DiagramNode("modelo", "VERSION_MODELO", "algoritmo o juez", 5, 475, analysis),
            DiagramNode("hallazgo", "HALLAZGO", "entrada agrupable", 132, 475, output),
            DiagramNode("comparacion", "COMPARACION", "contexto del caso", 259, 475, longitudinal),
            DiagramNode("analisis", "EJECUCION_ANALISIS", "objeto evaluable", 386, 475, analysis),
            DiagramNode("clustering", "EJECUCION_\nCLUSTERING", "experimento inmutable", 5, 355, grouping),
            DiagramNode("entrada", "ENTRADA_\nCLUSTERING", "conjunto exacto", 132, 355, grouping),
            DiagramNode("grupo", "GRUPO_RIESGO", "cluster emergente", 259, 355, grouping),
            DiagramNode("asignacion", "ASIGNACION", "hallazgo x grupo", 386, 355, grouping),
            DiagramNode("dataset", "DATASET_EVALUACION", "dataset versionado", 5, 235, validation),
            DiagramNode("caso", "CASO_EVALUACION", "unidad evaluable", 132, 235, validation),
            DiagramNode("anotacion", "ANOTACION_\nREFERENCIA", "ground truth revisable", 259, 235, validation),
            DiagramNode("evaluacion", "EJECUCION_\nEVALUACION", "configuración reproducible", 386, 235, validation),
            DiagramNode("resultado", "RESULTADO_\nEVALUACION", "por caso y objeto", 132, 115, validation),
            DiagramNode("metrica", "METRICA_\nEVALUACION", "resumen comparable", 386, 115, validation),
        ]
        edges = [
            ("modelo", "clustering"),
            ("hallazgo", "entrada"),
            ("clustering", "entrada"),
            ("clustering", "grupo"),
            ("clustering", "asignacion"),
            ("hallazgo", "asignacion"),
            ("grupo", "asignacion"),
            ("dataset", "caso"),
            ("comparacion", "caso"),
            ("caso", "anotacion"),
            ("dataset", "evaluacion"),
            ("modelo", "evaluacion"),
            ("evaluacion", "resultado"),
            ("caso", "resultado"),
            ("analisis", "resultado"),
            ("clustering", "resultado"),
            ("evaluacion", "metrica"),
        ]
        return EntityViewDiagram(nodes, edges)

    def _entity_tables(self) -> tuple[Table, Table]:
        rows = [
            (
                "Empresa",
                "Crudo",
                "Emisor SEC",
                "Entidad jurídica que presenta los filings. Identidad estable mediante CIK; conserva el nombre legal del emisor.",
            ),
            (
                "Informe / Filing",
                "Crudo",
                "Filing SEC",
                "Presentación concreta 10-K o 10-K/A, identificada por accession_number. Conserva empresa, formulario, ejercicio, cierre fiscal, fecha, ticker y URL de índice SEC.",
            ),
            (
                "DocumentoFuente",
                "Crudo",
                "Filing x documento",
                "Artefacto descargado de la SEC (HTML o TXT). Conserva URL, hash SHA-256, fecha de descarga y URI de almacenamiento; nunca se sobrescribe.",
            ),
            (
                "VersiónParsing",
                "Parsing",
                "Versión de parser",
                "Identifica de forma estable la implementación y su configuración. Permite reproducir o comparar distintas segmentaciones.",
            ),
            (
                "EjecuciónParsing",
                "Parsing",
                "Documento x versión",
                "Aplicación concreta de una versión de parsing a un documento fuente. Registra fecha y estado, y genera la estructura textual.",
            ),
            (
                "Sección",
                "Parsing",
                "Ejecución x sección",
                "Bloque detectado del filing (Item 1A, Item 7, resto). Pertenece a la ejecución que lo generó.",
            ),
            (
                "Párrafo",
                "Parsing",
                "Sección x posición",
                "Unidad estructurada intermedia y nivel de anclaje de los hallazgos del LLM.",
            ),
            (
                "Frase",
                "Parsing",
                "Párrafo x posición",
                "Átomo del árbol textual generado. Unidad mínima referenciable y nivel de extracción de características.",
            ),
            (
                "EjecuciónCaracterización",
                "Derivado (1.er orden)",
                "Parsing x versión de modelo",
                "Ejecución reproducible de extracción y agregación. Conserva código, parámetros, semilla, tiempos y estado.",
            ),
            (
                "CaracterísticaFrase",
                "Derivado (1.er orden)",
                "Ejecución x frase",
                "Características producidas para una frase por una ejecución concreta. Una frase admite múltiples versiones sin sobrescritura.",
            ),
            (
                "RepresentaciónInforme",
                "Derivado (1.er orden)",
                "Ejecución x filing",
                "Agregación cuantitativa producida por una ejecución. Un filing admite múltiples representaciones y cada una puede alimentar scores.",
            ),
            (
                "Comparación",
                "Contexto longitudinal",
                "Filing objetivo x estrategia",
                "Unidad de análisis que enfrenta un filing objetivo a uno o varios filings históricos con una estrategia declarada. Contexto común de LLM y ML.",
            ),
            (
                "ComparaciónInforme<br/>Referencia",
                "Contexto longitudinal",
                "Comparación x filing histórico",
                "Materializa el baseline: identifica cada accession_number de referencia e incorpora su orden y peso opcional.",
            ),
            (
                "VersiónModelo",
                "Análisis versionado",
                "Versión inmutable",
                "Identifica una versión y su familia técnica (LLM, ML clásico, cuántico, híbrido o reglas). La ejecución determina la tarea.",
            ),
            (
                "EjecuciónAnálisis",
                "Análisis versionado",
                "Comparación x versión",
                "Ejecución concreta y no sobrescribible. Conserva código, prompt, parámetros, semilla, tiempos y estado; genera las salidas.",
            ),
            (
                "Hallazgo",
                "Salida (LLM)",
                "Ejecución LLM x hallazgo",
                "Riesgo oculto generado por una ejecución, con descripción, confianza y severidad. Debe sustentarse en una o más evidencias.",
            ),
            (
                "EvidenciaHallazgo",
                "Salida (LLM)",
                "Hallazgo x evidencia",
                "Filing obligatorio y párrafo o rango opcional. Registra rol documental y tipo para representar presencia, cambio, aparición, desaparición u omisión.",
            ),
            (
                "Score",
                "Salida (ML)",
                "Ejecución ML",
                "Anomalía del filing objetivo generada por una ejecución, con la contribución de las características que la explican.",
            ),
            (
                "EjecuciónClustering",
                "Agrupación (2.º orden)",
                "Versión x conjunto de entrada",
                "Ejecución global e inmutable. Conserva código, parámetros, semilla, tiempos y estado; genera grupos y asignaciones.",
            ),
            (
                "EntradaClustering",
                "Agrupación (2.º orden)",
                "Ejecución x hallazgo",
                "Materializa el conjunto exacto de hallazgos recibido, incluidos los que finalmente quedan como ruido sin asignación.",
            ),
            (
                "GrupoRiesgo",
                "Agrupación (2.º orden)",
                "Ejecución x grupo",
                "Tipo de riesgo emergente generado por una ejecución. Transversal a empresas y años; conserva etiqueta y descripción.",
            ),
            (
                "Asignación",
                "Agrupación (2.º orden)",
                "Ejecución x hallazgo x grupo",
                "Pertenencia resultante de un hallazgo a un grupo, con grado de pertenencia y marca de representatividad.",
            ),
            (
                "DatasetEvaluación",
                "Validación",
                "Dataset x versión",
                "Colección versionada de casos para una tarea. Conserva hash, fecha y estado de revisión del conjunto.",
            ),
            (
                "CasoEvaluación",
                "Validación",
                "Dataset x caso",
                "Unidad evaluable asignada a una partición. Puede enlazar una comparación y conservar metadatos de entrada.",
            ),
            (
                "AnotaciónReferencia",
                "Validación",
                "Caso x anotación",
                "Ground truth esperado con autor, fuente y estado de revisión. Admite varias anotaciones por caso.",
            ),
            (
                "EjecuciónEvaluación",
                "Validación",
                "Dataset x configuración",
                "Evaluación reproducible con código y configuración propios; puede utilizar una versión de modelo como juez.",
            ),
            (
                "ResultadoEvaluación",
                "Validación",
                "Ejecución x caso x objeto",
                "Resultado por caso sobre una ejecución de análisis o clustering (XOR), con valor, superación y detalle.",
            ),
            (
                "MétricaEvaluación",
                "Validación",
                "Ejecución x métrica",
                "Métrica agregada con nombre, alcance, valor y desglose para comparar experimentos reproduciblemente.",
            ),
        ]

        raw = colors.HexColor("#E6EEF9")
        parsing = colors.HexColor("#E2F1F4")
        derived = colors.HexColor("#E4F2E8")
        longitudinal = colors.HexColor("#E9E4F4")
        analysis = colors.HexColor("#F1E8D8")
        output = colors.HexColor("#FDE9AD")
        grouping = colors.HexColor("#F8E2E2")
        validation = colors.HexColor("#E6E8F5")
        row_backgrounds = (
            [raw] * 3
            + [parsing] * 5
            + [derived] * 3
            + [longitudinal] * 2
            + [analysis] * 2
            + [output] * 3
            + [grouping] * 4
            + [validation] * 6
        )

        def build_table(table_rows, backgrounds):
            headers = ("Entidad", "Capa", "Grano", "Qué representa")
            data = [[self._p(value, "header") for value in headers]]
            data.extend(
                [
                    self._p(name, "entity"),
                    self._p(layer, "cell"),
                    self._p(grain, "cell"),
                    self._p(description, "cell"),
                ]
                for name, layer, grain, description in table_rows
            )
            table = Table(data, colWidths=[102, 94, 108, 199], repeatRows=1, hAlign="LEFT")
            table_style = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2A2A29")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, 0), 5),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
                ("TOPPADDING", (0, 1), (-1, -1), 3.2),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 3.2),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C7C7C2")),
            ]
            for row_number, background in enumerate(backgrounds, start=1):
                table_style.append(("BACKGROUND", (0, row_number), (-1, row_number), background))
            table.setStyle(TableStyle(table_style))
            return table

        split_index = 18
        return (
            build_table(rows[:split_index], row_backgrounds[:split_index]),
            build_table(rows[split_index:], row_backgrounds[split_index:]),
        )

    def _legend_table(self) -> Table:
        legend_rows = [
            (colors.HexColor("#4E79A7"), "<b>Crudo:</b> Metadatos SEC y documentos fuente inmutables, conservados para reproducibilidad."),
            (colors.HexColor("#3E8997"), "<b>Parsing:</b> Estructura textual regenerable, producida por una versión y una ejecución identificables."),
            (colors.HexColor("#2F855A"), "<b>Derivado (1.er orden):</b> Sale del árbol parseado mediante una ejecución versionada y se recalcula sin sobrescritura."),
            (colors.HexColor("#7562A8"), "<b>Contexto longitudinal:</b> Define el filing objetivo y el conjunto explícito de filings históricos usados como referencia."),
            (colors.HexColor("#9A6B32"), "<b>Análisis versionado:</b> Fija el modelo y registra cada ejecución reproducible sobre una comparación."),
            (colors.HexColor("#C46A00"), "<b>Salida:</b> Resultado inmutable de una ejecución. Las ramas LLM y ML tienen distinto anclaje."),
            (colors.HexColor("#C51F1F"), "<b>Agrupación (2.º orden):</b> Ejecución global versionada sobre un conjunto explícito de hallazgos; conserva grupos, ruido y asignaciones."),
            (colors.HexColor("#5969A6"), "<b>Validación:</b> Ground truth versionado y resultados por caso, resumidos mediante métricas comparables."),
        ]
        data = [["", self._p(text, "legend")] for _, text in legend_rows]
        table = Table(data, colWidths=[12, 487], hAlign="LEFT")
        table_style = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (0, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 1.2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
        ]
        for row_number, (swatch, _) in enumerate(legend_rows):
            table_style.extend(
                [
                    ("BACKGROUND", (0, row_number), (0, row_number), swatch),
                    ("BOX", (0, row_number), (0, row_number), 1.5, colors.white),
                ]
            )
        table.setStyle(TableStyle(table_style))
        return table

    @staticmethod
    def _draw_page_number(canvas, document) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#777670"))
        canvas.drawRightString(A4[0] - 16 * mm, 4 * mm, str(document.page))
        canvas.restoreState()

    def build(self) -> None:
        document = SimpleDocTemplate(
            str(self.output_path),
            pagesize=A4,
            leftMargin=16 * mm,
            rightMargin=16 * mm,
            topMargin=8 * mm,
            bottomMargin=6 * mm,
            title="Modelo de datos - Análisis automático de riesgos ocultos en informes 10-K",
            author="TFM MIAX",
        )
        main_table, validation_table = self._entity_tables()
        story = [
            self._p(
                "Modelo de datos - Análisis automático de riesgos ocultos en informes 10-K",
                "title",
            ),
            self._p("Vista 1 de 3 · Ingesta, procedencia y estructura del 10-K", "subtitle"),
            self._view_ingesta(),
            self._p(
                "<b>Lectura:</b> la cadena conserva el filing y el documento original; "
                "la estructura textual siempre queda asociada a una ejecución y una versión de parsing.",
                "view_note",
            ),
            PageBreak(),
            self._p(
                "Modelo de datos - Análisis automático de riesgos ocultos en informes 10-K",
                "title",
            ),
            self._p("Vista 2 de 3 · Comparación longitudinal y generación de resultados", "subtitle"),
            self._view_comparacion(),
            self._p(
                "<b>Lectura:</b> las características se versionan por ejecución; la comparación "
                "materializa el baseline y cada hallazgo conserva evidencia trazable al filing.",
                "view_note",
            ),
            PageBreak(),
            self._p(
                "Modelo de datos - Análisis automático de riesgos ocultos en informes 10-K",
                "title",
            ),
            self._p("Vista 3 de 3 · Clustering, experimentación y validación", "subtitle"),
            self._view_clustering_validation(),
            self._p(
                "<b>Integridad:</b> RESULTADO_EVALUACION referencia exactamente una ejecución "
                "de análisis o una de clustering (XOR). El detalle completo de cardinalidades está en el HTML.",
                "view_note",
            ),
            PageBreak(),
            self._p(
                "Diccionario del modelo de datos",
                "title",
            ),
            self._p("Entidades, capas y granos del sistema · Parte 1 de 2", "subtitle"),
            main_table,
            PageBreak(),
            self._p("Diccionario del modelo de datos", "title"),
            self._p("Entidades de segundo orden y evaluación · Parte 2 de 2", "subtitle"),
            validation_table,
            Spacer(1, 3),
            self._p("Descripción de las capas", "section_title"),
            self._legend_table(),
        ]
        document.build(
            story,
            onFirstPage=self._draw_page_number,
            onLaterPages=self._draw_page_number,
        )


if __name__ == "__main__":
    DataModelPdfBuilder().build()
