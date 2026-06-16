#!/usr/bin/env python3
"""
build_bank_ciks.py

Construye el universo de CIKs de bancos estadounidenses consultando EDGAR
por codigo SIC, y escribe un fichero de texto (un CIK por linea) listo para
pasarselo a edgar-crawler en el parametro `cik_tickers` de config.json.

Por que asi: edgar-crawler descarga por CIK/ticker, no por sector. Los indices
trimestrales de EDGAR no llevan el SIC, asi que el filtrado sectorial se hace
ANTES, construyendo aqui la lista de CIKs.

Requisitos: requests  ->  pip install requests
Politica de acceso de la SEC: max 10 req/s y User-Agent descriptivo obligatorio.
"""

import re
import time
import sys
import pathlib
import requests

# --- CONFIGURACION ---------------------------------------------------------

# OBLIGATORIO: la SEC rechaza (403) las peticiones sin un User-Agent real.
# Pon tu nombre y un email de contacto.
USER_AGENT = "Higinio Paterna Ortiz higiniopaternaortiz@gmail.com"

# Codigos SIC del universo bancario (instituciones de deposito + holdings).
BANK_SIC_CODES = [
    "6021",  # National commercial banks (1055 CIKs)
    "6022",  # State commercial banks (1322 CIKs)
    "6029",  # Commercial banks, NEC (129 CIKs)
    "6035",  # Savings institutions, federally chartered (807 CIKs)
    "6036",  # Savings institutions, not federally chartered ( 283 CIKs)
]


FILING_TYPE = "10-K"          # solo empresas que presentan 10-K
OUTPUT_FILE = pathlib.Path(__file__).parent / "edgar-crawler/bank_ciks.txt"
PAGE_SIZE = 100               # maximo que admite browse-edgar por pagina
SLEEP_SECONDS = 0.15          # ~6-7 req/s, holgado bajo el limite de 10 req/s

BROWSE_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})

# --- LOGICA ----------------------------------------------------------------

def fetch_ciks_for_sic(sic: str) -> set[str]:
    """Devuelve el conjunto de CIKs (10 digitos) que tienen filings 10-K
    bajo un codigo SIC, paginando hasta agotar resultados."""
    ciks: set[str] = set()
    start = 0
    while True:
        params = {
            "action": "getcompany",
            "SIC": sic,
            "type": FILING_TYPE,
            "dateb": "",
            "owner": "include",
            "count": PAGE_SIZE,
            "start": start,
            "output": "atom",
        }
        resp = SESSION.get(BROWSE_URL, params=params, timeout=30)
        time.sleep(SLEEP_SECONDS)

        if resp.status_code == 403:
            sys.exit("403 de la SEC: revisa el User-Agent o baja el ritmo.")
        resp.raise_for_status()

        # Robusto frente al esquema exacto del atom: extraemos CIKs tanto de
        # las etiquetas <cik> como de los enlaces que llevan CIK=NNNNNNNNNN.
        page = set(re.findall(r"<cik>(\d{1,10})</cik>", resp.text))
        page |= set(re.findall(r"CIK=(\d{10})", resp.text))
        page = {c.zfill(10) for c in page}

        new = page - ciks
        if not new:                # no hay CIKs nuevos -> fin de la paginacion
            break
        ciks |= new
        start += PAGE_SIZE

    return ciks


def main() -> None:
    if "<apellido>" in USER_AGENT or "example.com" in USER_AGENT:
        sys.exit("Edita USER_AGENT con tu nombre y email reales antes de ejecutar.")

    all_ciks: set[str] = set()
    for sic in BANK_SIC_CODES:
        found = fetch_ciks_for_sic(sic)
        print(f"SIC {sic}: {len(found)} CIKs")
        all_ciks |= found

    # edgar-crawler acepta un fichero con un CIK por linea en `cik_tickers`.
    with open(OUTPUT_FILE, "w") as f:
        for cik in sorted(all_ciks, key=int):
            f.write(str(int(cik)) + "\n")

    print(f"\nTotal de bancos unicos: {len(all_ciks)}")
    print(f"Escrito en: {OUTPUT_FILE}")
    print("Pasaselo a edgar-crawler -> config.json -> \"cik_tickers\": \"bank_ciks.txt\"")


if __name__ == "__main__":
    main()
