"""
gsheet_import_service.py
========================
Logica pura per importare team VGC dal Google Spreadsheet VGCPastes.

Flusso:
  1. Scarica la lista dei fogli (tab) dal documento pubblico
  2. Per ogni foglio selezionato, scarica il CSV (header a riga 3)
  3. Per ogni riga con URL Pokepaste valido, scarica e parsa il paste
  4. Assegna gli EVs: dal paste se presenti, oppure auto-generati in base
     al formato (Normale/Champions) e al ruolo del Pokémon

Dipendenze:
  - urllib.request (HTTP, nessuna libreria esterna)
  - src.domain.team_builder_service.parse_pokepaste (parsing Pokepaste)
  - src.domain.role_detector.detect_role (classificazione ruolo)
  - database.models_v2.PokemonSpeciesV2 (base stats dal DB)
"""

import csv
import io
import re
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from html.parser import HTMLParser


# ── Dataclass di dominio ─────────────────────────────────────────

@dataclass
class SheetInfo:
    """Metadati di un foglio (tab) del Google Spreadsheet."""
    name: str
    gid: str


@dataclass
class TeamRow:
    """Riga singola estratta dal CSV del foglio."""
    team_name: str
    pokepaste_url: str
    has_evs: bool


@dataclass
class TeamMemberBuild:
    """Build completa di un singolo Pokémon con EVs risolti."""
    species: str
    ability: str
    item: str
    moves: List[str]
    nature: str
    tera_type: str
    evs: Dict[str, int]
    ivs: Dict[str, int]
    role: str          # "Offensive" | "Defensive" | "Disruptive"
    evs_source: str    # "paste" | "auto"


@dataclass
class ImportedTeam:
    """Team completo importato dal foglio."""
    team_name: str
    pokepaste_url: str
    members: List[TeamMemberBuild]
    source_sheet: str
    has_evs: bool


# ── Costanti ─────────────────────────────────────────────────────

SPREADSHEET_ID = "1axlwmzPA49rYkqXh7zHvAtSP-TKbM0ijGYBPRflLSWw"

_HEADERS = {"User-Agent": "Mozilla/5.0 (JAnalytics/1.0)"}

# Colonne attese (case-insensitive match)
_COL_TEAM_DESC = "team description"
_COL_POKEPASTE = "pokepaste"
_COL_EVS = "evs"


# ── 1. Fetch lista fogli ────────────────────────────────────────

def fetch_sheet_names(spreadsheet_id: str = SPREADSHEET_ID) -> List[SheetInfo]:
    """
    Scarica la pagina HTML pubblica del Google Sheet e ne estrae
    i nomi dei tab (fogli) con i relativi gid.

    Strategia a 2 fasi:
      1. Estrai i gridId dal bootstrapData JavaScript embedded
      2. Per ogni gridId, scarica i primi byte del CSV per identificare
         il nome reale del foglio dalla prima riga ("VGCPastes Repository (...)")

    Fallback: se l'HTML non contiene il bootstrapData, usa i nomi
    dei tab dal markup HTML (docs-sheet-tab-caption) e tenta di
    scoprire i gid con l'export CSV.
    """
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
    req = urllib.request.Request(url, headers=_HEADERS)

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode("utf-8", errors="replace")
    except Exception as e:
        raise ConnectionError(f"Impossibile scaricare lo spreadsheet: {e}")

    # ── Fase 1: estrai i gridId dal bootstrapData ─────────────────
    # Il bootstrapData contiene entries con pattern: [\"GRIDID\",N,ROWS,COL_START,COL_END]
    bd_match = re.search(r'bootstrapData\s*=\s*\{', html)
    gids: List[str] = []

    if bd_match:
        bd_end = html.find('</script>', bd_match.start())
        bd_text = html[bd_match.start():bd_end] if bd_end > 0 else html[bd_match.start():]

        # Estrai gridId dal pattern delle definizioni dei fogli
        chunk_ids = re.findall(
            r'\[\\"(\d{6,12})\\",\d+,\d+,\d+,\d+\]',
            bd_text
        )
        # Deduplicazione preservando l'ordine
        seen = set()
        for gid in chunk_ids:
            if gid not in seen:
                gids.append(gid)
                seen.add(gid)

    # ── Fase 1b: fallback — estrai i nomi tab dal markup HTML ─────
    tab_names = re.findall(
        r'class="[^"]*docs-sheet-tab-caption[^"]*"[^>]*>([^<]+)</div>',
        html
    )

    if not gids:
        raise ValueError(
            "Impossibile estrarre i gridId dal Google Sheet. "
            "Verifica che il documento sia pubblico."
        )

    # ── Fase 2: per ogni gid, identifica il nome dal CSV ──────────
    sheets: List[SheetInfo] = []

    for i, gid in enumerate(gids):
        # Prova a identificare il nome del foglio dal contenuto CSV
        name = _identify_sheet_name(spreadsheet_id, gid)

        if not name and i < len(tab_names):
            # Fallback: usa il nome dal tab HTML (ordine potenzialmente diverso)
            name = tab_names[i]

        if not name:
            name = f"Foglio (gid={gid})"

        sheets.append(SheetInfo(name=name, gid=gid))

    return sheets


def _identify_sheet_name(spreadsheet_id: str, gid: str) -> Optional[str]:
    """
    Scarica i primi byte del CSV di un foglio per estrarre il nome
    dalla prima riga, tipicamente:
        ,VGCPastes Repository (NOME_FOGLIO),...
    
    Returns None se non riesce a identificare il nome.
    """
    csv_url = (
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        f"/export?format=csv&gid={gid}"
    )
    req = urllib.request.Request(csv_url, headers=_HEADERS)

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            first_bytes = response.read(500).decode("utf-8-sig", errors="replace")
    except Exception:
        return None

    first_line = first_bytes.split("\n")[0] if first_bytes else ""

    # Pattern: "VGCPastes Repository (SHEET NAME)"
    match = re.search(r'VGCPastes Repository\s*\(([^)]+)\)', first_line)
    if match:
        return match.group(1).strip().rstrip("!")

    # Pattern alternativo: "Welcome to" → è la home/intro sheet
    if "Welcome" in first_line:
        return "Home"

    return None


# ── 2. Fetch dati CSV di un foglio ──────────────────────────────

def fetch_sheet_data(
    spreadsheet_id: str,
    gid: str,
) -> List[TeamRow]:
    """
    Scarica il CSV di un foglio specifico e parsa le righe.

    Header atteso alla riga 3 (le prime 2 righe vengono ignorate).
    Colonne usate:
      - "Team Description" → nome del team
      - "Pokepaste" → URL del paste
      - "EVs" → "Yes"/"No" per la presenza degli EVs nel paste
    """
    url = (
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        f"/export?format=csv&gid={gid}"
    )
    req = urllib.request.Request(url, headers=_HEADERS)

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8-sig", errors="replace")
    except Exception as e:
        raise ConnectionError(f"Impossibile scaricare il foglio (gid={gid}): {e}")

    lines = raw.splitlines()
    if len(lines) < 3:
        return []

    # Ignora le prime 2 righe, la riga 3 è l'header
    header_line = lines[2]
    data_lines = lines[3:]

    # Parsing CSV con header
    csv_text = header_line + "\n" + "\n".join(data_lines)
    reader = csv.DictReader(io.StringIO(csv_text))

    # Identifica le colonne con matching case-insensitive
    field_names = reader.fieldnames or []
    col_map = {f.strip().lower(): f for f in field_names}

    team_desc_col = col_map.get(_COL_TEAM_DESC)
    pokepaste_col = col_map.get(_COL_POKEPASTE)
    evs_col = col_map.get(_COL_EVS)

    if not pokepaste_col:
        # Fallback: cerca colonne che contengano "pokepaste" nel nome
        for key, original in col_map.items():
            if "pokepaste" in key:
                pokepaste_col = original
                break

    if not team_desc_col:
        for key, original in col_map.items():
            if "team" in key and "description" in key:
                team_desc_col = original
                break

    if not pokepaste_col:
        return []  # Senza colonna Pokepaste non possiamo procedere

    rows: List[TeamRow] = []
    for row in reader:
        paste_url = (row.get(pokepaste_col) or "").strip()
        if not paste_url or not paste_url.startswith("http"):
            continue

        team_name = (row.get(team_desc_col) or "").strip() if team_desc_col else ""
        evs_raw = (row.get(evs_col) or "").strip().lower() if evs_col else "no"
        has_evs = evs_raw in ("yes", "sì", "si", "true", "1", "y")

        rows.append(TeamRow(
            team_name=team_name or f"Team (paste: ...{paste_url[-12:]})",
            pokepaste_url=paste_url,
            has_evs=has_evs,
        ))

    return rows


# ── 3. Fetch testo raw da Pokepaste ─────────────────────────────

def fetch_pokepaste_text(url: str) -> str:
    """
    Scarica l'HTML da pokepast.es e ne estrae il testo raw del paste
    dal tag <pre>.

    Supporta anche URL con /raw suffix.
    """
    clean_url = url.strip().rstrip("/")

    # Se l'URL finisce con /raw, scarica direttamente il testo
    if clean_url.endswith("/raw"):
        raw_url = clean_url
    else:
        raw_url = clean_url + "/raw"

    # Tentativo 1: endpoint /raw (testo puro)
    try:
        req = urllib.request.Request(raw_url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as response:
            text = response.read().decode("utf-8", errors="replace").strip()
            if text and not text.startswith("<!"):
                return text
    except Exception:
        pass

    # Tentativo 2: scraping HTML con parsing <pre>
    try:
        req = urllib.request.Request(clean_url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode("utf-8", errors="replace")
    except Exception as e:
        raise ConnectionError(f"Impossibile scaricare il Pokepaste da {url}: {e}")

    # Estrai il contenuto di tutti i tag <pre> (ogni Pokémon è in un <pre> separato)
    pre_contents = re.findall(r"<pre>(.*?)</pre>", html, re.DOTALL)
    if not pre_contents:
        raise ValueError(f"Nessun contenuto trovato nel Pokepaste: {url}")

    # Rimuovi tag HTML residui e unisci con riga vuota (separatore Pokémon)
    clean_parts = []
    for part in pre_contents:
        # Rimuovi tag HTML
        clean = re.sub(r"<[^>]+>", "", part)
        # Decodifica entità HTML
        clean = clean.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        clean = clean.replace("&#39;", "'").replace("&quot;", '"')
        clean = clean.strip()
        if clean:
            clean_parts.append(clean)

    return "\n\n".join(clean_parts)


# ── 4. Build team con logica EVs ────────────────────────────────

def _generate_normal_evs(
    role: str,
    base_stats: Dict[str, int],
    moves: Optional[List[str]] = None,
) -> Tuple[Dict[str, int], str]:
    """
    Genera EVs per il formato "Normale" (scala 0-252, budget 508 max).

    Returns:
        (evs_dict, nature)
    """
    from src.domain.auto_build import _classify_moves

    if role == "Offensive":
        move_class = _classify_moves(moves or [])

        if move_class == "mixed":
            return {"Atk": 252, "SpA": 252, "Spe": 4}, "Naive"
        elif move_class == "physical":
            return {"Atk": 252, "Spe": 252, "HP": 4}, "Jolly"
        elif move_class == "special":
            return {"SpA": 252, "Spe": 252, "HP": 4}, "Timid"
        else:
            # Fallback su base stats
            atk = base_stats.get("atk", 0) or 0
            spa = base_stats.get("spa", 0) or 0
            if atk >= spa:
                return {"Atk": 252, "Spe": 252, "HP": 4}, "Jolly"
            else:
                return {"SpA": 252, "Spe": 252, "HP": 4}, "Timid"
    else:
        # Defensive / Disruptive
        def_ = base_stats.get("def", 0) or 0
        spd = base_stats.get("spd", 0) or 0
        if def_ >= spd:
            return {"HP": 252, "Def": 252, "SpD": 4}, "Impish"
        else:
            return {"HP": 252, "SpD": 252, "Def": 4}, "Careful"


def _generate_champions_evs(
    role: str,
    base_stats: Dict[str, int],
    moves: Optional[List[str]] = None,
) -> Tuple[Dict[str, int], str]:
    """
    Genera EVs per il formato "Champions" (scala 0-32, budget 66 max).
    Riusa la logica già presente in auto_build.py.
    """
    from src.domain.auto_build import generate_auto_build
    result = generate_auto_build(role, base_stats, moves)
    return result["evs"], result["nature"]


def build_team_with_evs(
    paste_text: str,
    has_evs: bool,
    format_mode: str,
    corrections: Optional[Dict[str, str]] = None,
) -> List[TeamMemberBuild]:
    """
    Parsa il testo di un Pokepaste e risolve gli EVs.

    Args:
        paste_text: Testo raw del Pokepaste
        has_evs: Se True, usa gli EVs dal paste; se False, auto-genera
        format_mode: "Normale" o "Champions"
        corrections: Dizionario opzionale di correzioni nomi (per parse_pokepaste)

    Returns:
        Lista di TeamMemberBuild con EVs risolti
    """
    from src.domain.team_builder_service import parse_pokepaste
    from src.domain.role_detector import detect_role
    from database.connection import SessionLocal
    from database.models_v2 import PokemonSpeciesV2
    from database.hash_utils import to_id

    # Parsing del paste (con validazione DB)
    try:
        members = parse_pokepaste(paste_text, corrections)
    except Exception as e:
        raise ValueError(f"Errore nel parsing del Pokepaste: {e}")

    builds: List[TeamMemberBuild] = []

    with SessionLocal() as session:
        for member in members:
            # Recupera base stats dal DB
            species_id = to_id(member.species)
            species_db = session.query(PokemonSpeciesV2).filter(
                PokemonSpeciesV2.id == species_id
            ).first()

            base_stats = {}
            if species_db:
                base_stats = {
                    "hp": species_db.bst_hp,
                    "atk": species_db.bst_atk,
                    "def": species_db.bst_def,
                    "spa": species_db.bst_spa,
                    "spd": species_db.bst_spd,
                    "spe": species_db.bst_spe,
                }

            # Determina il ruolo
            role = detect_role(member.species, member.moves, base_stats)

            # Risolvi EVs
            if has_evs and member.evs and any(v > 0 for v in member.evs.values()):
                # Caso A: EVs presenti nel paste — usa quelli
                evs = dict(member.evs)
                nature = member.nature or "Hardy"
                evs_source = "paste"
            else:
                # Caso B: EVs non presenti — auto-genera
                if format_mode == "Champions":
                    evs, nature = _generate_champions_evs(
                        role, base_stats, member.moves
                    )
                else:
                    evs, nature = _generate_normal_evs(
                        role, base_stats, member.moves
                    )
                evs_source = "auto"

                # Mantieni la natura del paste se presente e non in auto-mode
                if member.nature:
                    nature = member.nature

            builds.append(TeamMemberBuild(
                species=member.species,
                ability=member.ability,
                item=member.item,
                moves=member.moves,
                nature=nature,
                tera_type=member.tera_type,
                evs=evs,
                ivs=dict(member.ivs) if member.ivs else {},
                role=role,
                evs_source=evs_source,
            ))

    return builds
