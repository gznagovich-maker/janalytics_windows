"""
sheet_client.py
===============
Accesso HTTP (solo lettura, nessuna libreria esterna) a un Google Sheet pubblico.

L'URL del foglio è fornito dinamicamente dall'utente: lo spreadsheet ID viene
estratto a runtime e i gid dei tab vengono scoperti dalla pagina /htmlview.
"""

import re
import urllib.error
import urllib.request
from typing import List, Optional

from src.domain.sheet_dashboard.models import SheetTab

_HEADERS = {"User-Agent": "Mozilla/5.0 (JAnalytics/1.0)"}
_BASE = "https://docs.google.com/spreadsheets/d/{sid}"

_ID_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]{20,})")


class SheetAccessError(ConnectionError):
    """Errore di accesso al Google Sheet (rete, permessi, URL non valido)."""


def parse_spreadsheet_url(url: str) -> str:
    """Estrae lo spreadsheet ID da un URL Google Sheets (o accetta l'ID nudo)."""
    text = (url or "").strip()
    m = _ID_RE.search(text)
    if m:
        return m.group(1)
    if re.fullmatch(r"[a-zA-Z0-9_-]{20,}", text):
        return text
    raise ValueError(
        "URL Google Sheets non valido. Formato atteso: "
        "https://docs.google.com/spreadsheets/d/<ID>/edit"
    )


def _get(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final_url = resp.geturl() or ""
            body = resp.read().decode("utf-8-sig", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            raise SheetAccessError(
                "Il foglio non è accessibile: verifica che sia condiviso come "
                "'Chiunque abbia il link può visualizzare'."
            ) from e
        raise SheetAccessError(f"Errore HTTP {e.code} durante il download del foglio.") from e
    except Exception as e:
        raise SheetAccessError(f"Impossibile contattare Google Sheets: {e}") from e

    if "accounts.google.com" in final_url or "ServiceLogin" in final_url:
        raise SheetAccessError(
            "Il foglio richiede l'accesso: rendilo pubblico in sola lettura."
        )
    return body


def _unescape_js(text: str) -> str:
    text = text.replace("\\/", "/")
    return re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), text)


def fetch_title_and_tabs(sid: str) -> tuple[str, List[SheetTab]]:
    """Restituisce (titolo documento, lista tab con gid) leggendo /htmlview."""
    html = _get(f"{_BASE.format(sid=sid)}/htmlview")
    tabs: List[SheetTab] = []
    seen = set()
    for m in re.finditer(r'items\.push\(\{name:\s*"((?:[^"\\]|\\.)*)".*?gid:\s*"(\d+)"', html):
        name, gid = _unescape_js(m.group(1)).strip(), m.group(2)
        if gid not in seen:
            seen.add(gid)
            tabs.append(SheetTab(name=name, gid=gid))

    title = ""
    t = re.search(r"<title>(.*?)</title>", html, re.S)
    if t:
        title = re.sub(r"\s*-\s*Google (Drive|Sheets|Fogli)\s*$", "", t.group(1)).strip()

    if not tabs:
        raise SheetAccessError(
            "Nessun tab trovato nel documento. Verifica che il foglio sia pubblico."
        )
    return title, tabs


def fetch_csv(sid: str, gid: str) -> str:
    return _get(f"{_BASE.format(sid=sid)}/export?format=csv&gid={gid}")


def fetch_htmlview(sid: str, gid: str) -> str:
    """Render HTML del singolo tab: preserva hyperlink e dati dei grafici."""
    return _get(f"{_BASE.format(sid=sid)}/htmlview/sheet?headers=false&gid={gid}")


def find_tab(tabs: List[SheetTab], *names: str) -> Optional[SheetTab]:
    """Trova un tab per nome (case/spazi-insensitive), con fallback 'contains'."""
    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", s.lower())

    wanted = [norm(n) for n in names]
    for tab in tabs:
        if norm(tab.name) in wanted:
            return tab
    for tab in tabs:
        if any(w and w in norm(tab.name) for w in wanted):
            return tab
    return None
