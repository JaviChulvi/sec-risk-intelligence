"""Local shared samples and independent reviewer CSV annotations."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import tempfile
from functools import lru_cache
from html import escape
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ASSETS = Path(__file__).resolve().parent
DATA = ASSETS
REVIEWERS = ("Javi", "Hugo", "Higinio")
FIELDS = ("review_status", "relevant_risk_news", "company_relevance", "event_status",
          "confirmed_risk_families", "noise_type", "reviewer", "notes")
REQUIRED = {"review_order", "article_id", "company", "title", "link", *FIELDS}
READER_HOSTS = {"finance.yahoo.com", "uk.finance.yahoo.com"}


class ArticleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.block = None
        self.parts = []
        self.blocks = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div":
            if self.depth:
                self.depth += 1
            elif attrs.get("data-testid") == "article-body":
                self.depth = 1
        if self.depth and tag in {"p", "h2", "h3"}:
            self.block, self.parts = tag, []
        if self.block and tag == "br":
            self.parts.append(" ")

    def handle_data(self, data):
        if self.depth and self.block:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == self.block:
            text = " ".join("".join(self.parts).split())
            if text:
                self.blocks.append(f"<{tag}>{escape(text)}</{tag}>")
            self.block = None
        if tag == "div" and self.depth:
            self.depth -= 1


class ArticleRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != "https" or urlsplit(newurl).netloc not in READER_HOSTS:
            raise ValueError("El medio redirige a otra página; abre el enlace original.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@lru_cache(maxsize=80)
def article_text(url: str) -> str:
    if urlsplit(url).scheme != "https" or urlsplit(url).netloc not in READER_HOSTS:
        raise ValueError("Este medio no tiene vista de lectura integrada.")
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with build_opener(ArticleRedirect()).open(request, timeout=12) as response:
        raw = response.read(4_000_001)
    if len(raw) > 4_000_000:
        raise ValueError("La página es demasiado grande para la vista de lectura.")
    parser = ArticleText()
    parser.feed(raw.decode("utf-8", errors="replace"))
    if not parser.blocks:
        raise ValueError("El medio no ha facilitado texto legible. Abre el original o deja la noticia pendiente.")
    return "".join(parser.blocks)


def reader_page(row: dict) -> bytes:
    try:
        body = article_text(row["link"])
    except (OSError, ValueError) as error:
        body = f"<p role='alert'>No se pudo cargar la lectura: {escape(str(error))}</p>"
    return ("<!doctype html><html lang='en'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width'>"
            "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'\">"
            "<title>Lectura de la noticia</title><style>body{font:17px/1.65 system-ui;color:#263c39;"
            "max-width:760px;margin:24px auto;padding:0 24px;background:white}"
            "h2{font-size:20px}a{color:#205c48}small{color:#5d6b66}</style>"
            f"{body}<small>Texto público disponible en origen · Puede ser parcial</small>"
            f"<p><a href='{escape(row['link'], quote=True)}' target='_blank' rel='noopener noreferrer'>Abrir original ↗</a></p></html>").encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def parse_sample(raw: bytes) -> tuple[list[str], list[dict]]:
    table = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True))
    if len(table) < 2:
        raise ValueError("El CSV no contiene noticias.")
    headers = table[0]
    if len(set(headers)) != len(headers) or not REQUIRED.issubset(headers):
        raise ValueError("Faltan columnas de revisión o hay columnas repetidas.")
    rows, identities = [], set()
    for values in table[1:]:
        if not values:
            continue
        if len(values) != len(headers):
            raise ValueError("Todas las filas deben tener el mismo número de columnas.")
        row = dict(zip(headers, values))
        identity = row["company"], row["article_id"]
        if not all(identity) or identity in identities:
            raise ValueError("Hay noticias duplicadas o sin identificador.")
        if row["review_status"] != "pending" or any(row[field] for field in FIELDS[1:] if field != "reviewer"):
            raise ValueError("La muestra compartida debe estar pendiente y sin respuestas. Conserva las anotaciones en el CSV de cada revisor.")
        identities.add(identity)
        rows.append(row)
    if not rows:
        raise ValueError("El CSV no contiene noticias.")
    return headers, rows


def sample_path(root: Path, name: str) -> Path:
    if not name or Path(name).name != name or "\\" in name or not name.lower().endswith(".csv"):
        raise ValueError("El nombre debe ser un archivo CSV, sin directorios.")
    path = root / "samples" / name
    if path.is_symlink():
        raise ValueError("La muestra debe ser un archivo dentro de la carpeta samples.")
    return path


def read_sample(root: Path, name: str) -> tuple[str, list[str], list[dict]]:
    raw = sample_path(root, name).read_bytes()
    headers, rows = parse_sample(raw)
    return digest(raw), headers, rows


def annotation_path(root: Path, filename: str, reviewer: str) -> Path:
    if reviewer not in REVIEWERS:
        raise ValueError("Selecciona Javi, Hugo o Higinio.")
    return root / "annotations" / f"{Path(filename).stem}_{reviewer.lower()}.csv"


def revision(path: Path) -> str:
    return digest(path.read_bytes()) if path.exists() else ""


def validate_annotations(headers: list[str], base: list[dict], rows: list[dict], reviewer: str) -> None:
    if not isinstance(rows, list) or len(rows) != len(base):
        raise ValueError("La anotación debe conservar todas las noticias de la muestra.")
    for original, row in zip(base, rows):
        if not isinstance(row, dict) or set(row) != set(headers) or not all(isinstance(value, str) for value in row.values()):
            raise ValueError("El formato de las filas no coincide con la muestra.")
        if any(row[field] != original[field] for field in headers if field not in FIELDS):
            raise ValueError("No se pueden cambiar los datos originales de las noticias.")
        if row["reviewer"] != reviewer or row["review_status"] not in ("pending", "reviewed"):
            raise ValueError("El revisor o el estado de la fila no son válidos.")
        if row["review_status"] == "pending":
            continue
        if not row["notes"].strip():
            raise ValueError("Cada noticia revisada necesita una nota.")
        if row["relevant_risk_news"] == "true":
            families = row["confirmed_risk_families"].split("|")
            if row["company_relevance"] != "true" or not set(families) <= {"cybersecurity", "critical_suppliers"}:
                raise ValueError("Confirma la empresa y la familia de los riesgos relevantes.")
            if row["event_status"] not in ("materialized", "exposure", "emerging") or row["noise_type"]:
                raise ValueError("Indica el estado del riesgo y deja vacío el motivo de ruido.")
        elif row["relevant_risk_news"] == "false":
            if row["company_relevance"] not in ("true", "false", "unclear") or not row["noise_type"].strip():
                raise ValueError("Indica la relación empresarial y el motivo de la noticia negativa.")
            if row["event_status"] or row["confirmed_risk_families"]:
                raise ValueError("Una noticia negativa no debe tener familia o estado de riesgo.")
        else:
            raise ValueError("Las noticias dudosas deben quedar pendientes.")


def write_annotations(path: Path, headers: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8-sig", newline="", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class Handler(BaseHTTPRequestHandler):
    def valid_host(self) -> bool:
        port = self.server.server_port
        return self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}

    def reply(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def json(self, status: int, value: dict) -> None:
        self.reply(status, json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/api/sample":
            with self.server.annotation_lock:
                self.get()
        else:
            self.get()

    def get(self) -> None:
        if not self.valid_host():
            self.json(403, {"error": "Usa la dirección local de la aplicación."})
            return
        route = urlsplit(self.path)
        root = self.server.data
        try:
            if route.path == "/api/samples":
                self.json(200, {"samples": sorted(p.name for p in (root / "samples").iterdir() if p.suffix.lower() == ".csv" and p.is_file() and not p.is_symlink()), "reviewers": REVIEWERS})
            elif route.path == "/api/sample":
                query = parse_qs(route.query)
                name = query.get("name", [""])[0]
                reviewer = query.get("reviewer", [""])[0]
                sample_id, headers, base = read_sample(root, name)
                path = annotation_path(root, name, reviewer)
                rows = [{**row, "reviewer": reviewer} for row in base]
                if path.exists():
                    with path.open(encoding="utf-8-sig", newline="") as stream:
                        rows = list(csv.DictReader(stream))
                    validate_annotations(headers, base, rows, reviewer)
                self.json(200, {"id": sample_id, "filename": name, "headers": headers, "rows": rows, "reviewer": reviewer, "revision": revision(path)})
            elif route.path == "/article":
                query = parse_qs(route.query)
                _, _, rows = read_sample(root, query.get("name", [""])[0])
                index = int(query.get("index", ["-1"])[0])
                if not 0 <= index < len(rows):
                    raise ValueError("Noticia no disponible.")
                self.reply(200, reader_page(rows[index]), "text/html; charset=utf-8")
            elif route.path in {"/", "/index.html", "/app.js", "/style.css"}:
                asset = ASSETS / ("index.html" if route.path == "/" else route.path[1:])
                mime = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}[asset.suffix]
                self.reply(200, asset.read_bytes(), mime + "; charset=utf-8")
            else:
                self.json(404, {"error": "Ruta no disponible."})
        except FileNotFoundError:
            self.json(404, {"error": "No se encuentra el CSV en la carpeta samples."})
        except (ValueError, csv.Error, KeyError, TypeError, OSError) as error:
            self.json(400, {"error": str(error)})

    def do_POST(self) -> None:
        with self.server.annotation_lock:
            self.post()

    def post(self) -> None:
        if not self.valid_host() or self.headers.get("Origin") != f"http://{self.headers.get('Host')}":
            self.json(403, {"error": "Guarda desde esta aplicación local."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 8_000_000:
                raise ValueError("El archivo debe ocupar menos de 8 MB.")
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError("La petición no es válida.")
            root = self.server.data
            if self.path == "/api/samples":
                name, text = payload["filename"], payload["csv"]
                if not isinstance(name, str) or not isinstance(text, str):
                    raise ValueError("Selecciona un archivo CSV.")
                raw = text.encode("utf-8")
                parse_sample(raw)
                path = sample_path(root, name)
                if path.exists():
                    if path.read_bytes().decode("utf-8-sig") != text.removeprefix("\ufeff"):
                        self.json(409, {"error": "Ya existe otra muestra con ese nombre. Renombra el CSV antes de cargarlo."})
                        return
                else:
                    path.write_bytes(raw)
                self.json(200, {"filename": name})
            elif self.path == "/api/annotations":
                sample_id, headers, base = read_sample(root, payload["filename"])
                if sample_id != payload["id"]:
                    self.json(409, {"error": "La muestra ha cambiado. Descarga tu borrador y recarga el archivo."})
                    return
                reviewer, rows = payload["reviewer"], payload["rows"]
                path = annotation_path(root, payload["filename"], reviewer)
                if payload.get("revision") != revision(path):
                    self.json(409, {"error": "Otra pestaña ha guardado cambios. Descarga tu borrador antes de recargar lo guardado."})
                    return
                validate_annotations(headers, base, rows, reviewer)
                write_annotations(path, headers, rows)
                self.json(200, {"revision": revision(path)})
            else:
                self.json(404, {"error": "Ruta no disponible."})
        except (ValueError, csv.Error, KeyError, TypeError, OSError) as error:
            self.json(400, {"error": f"No se pudo guardar: {error}"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=DATA)
    args = parser.parse_args()
    root = args.data_dir.resolve()
    (root / "samples").mkdir(parents=True, exist_ok=True)
    (root / "annotations").mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.data = root
    server.annotation_lock = Lock()
    print(f"Anotación de noticias: http://127.0.0.1:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
