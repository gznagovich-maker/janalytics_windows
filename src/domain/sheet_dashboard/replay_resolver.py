"""
replay_resolver.py
==================
Download, cache e parsing "leggero" dei log Showdown referenziati dal foglio.

Produce, per ogni replay, i dati necessari alla dashboard con identità
Pokémon basata su "Specie + Forma":
  - team preview risolto (le wildcard tipo "Urshifu-*" vengono sostituite con la
    forma reale osservata negli switch-in)
  - lead (primi due switch-in prima di |turn|1) e back rivelati
  - mega evoluzione (flag separato: la Mega NON è una forma distinta)
  - vincitore, rating, presenza di team sheet aperti (OTS)
  - conteggio mosse usate per Pokémon (fallback nativo per Move Usage)

Espone inoltre `ensure_in_db` per importare on-demand un replay nel DB interno,
così che il visualizzatore nativo (ReplayAnalyzerUI) possa aprirlo.
"""

import os
import re
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from src.domain.sheet_dashboard.models import GameSummary, ParsedLog, SideData

_HEADERS = {"User-Agent": "Mozilla/5.0 (JAnalytics/1.0)"}
_REPLAY_HOST = "https://replay.pokemonshowdown.com"
CACHE_DIR = Path.home() / "JAnalytics" / "replay_cache"

# Suffissi di forma "in battaglia" che non fanno parte dell'identità
_BATTLE_SUFFIX_RE = re.compile(r"-(Mega(?:-[XYZ])?|Primal|Tera|Gmax|Eternamax)$", re.I)


def to_id(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


# ── Identità Specie + Forma ───────────────────────────────────────

def canonical_species(details_species: str) -> str:
    """
    "Garchomp-Mega-Z" → "Garchomp", "Ogerpon-Hearthflame-Tera" → "Ogerpon-Hearthflame".
    La forma (regionale, Urshifu-Rapid-Strike, Indeedee-F, ...) viene preservata.
    """
    s = (details_species or "").split(",")[0].strip()
    prev = None
    while prev != s:
        prev = s
        s = _BATTLE_SUFFIX_RE.sub("", s)
    return s


def _base_key(species: str) -> str:
    """Chiave di specie base (per la Species Clause una sola per team)."""
    return to_id(species.split("-")[0])


def is_mega_forme(details_species: str) -> bool:
    return bool(re.search(r"-Mega(?:-[XYZ])?$", (details_species or "").split(",")[0].strip(), re.I))


# ── URL / ID replay ───────────────────────────────────────────────

def replay_slug_from_url(url: str) -> str:
    """URL replay → slug (es. 'gen9...-2695223934-axwr...pw')."""
    parsed = urllib.parse.urlparse((url or "").strip())
    path = parsed.path if parsed.netloc else (url or "")
    slug = path.rstrip("/").split("/")[-1]
    slug = re.sub(r"\.(log|json|html)$", "", slug)
    if not slug:
        raise ValueError(f"URL replay non valido: {url}")
    return slug


def match_id_from_slug(slug: str) -> str:
    """Rimuove il suffisso password dei replay privati: '...-123-abcpw' → '...-123'."""
    m = re.match(r"^(.*-\d+)-[a-z0-9]+pw$", slug)
    return m.group(1) if m else slug


def fetch_log(slug: str, use_cache: bool = True) -> str:
    """Scarica il .log di un replay (con cache su disco)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', slug)}.log"
    if use_cache and cache_file.exists() and cache_file.stat().st_size > 0:
        return cache_file.read_text(encoding="utf-8")

    req = urllib.request.Request(f"{_REPLAY_HOST}/{slug}.log", headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    if not text.strip().startswith("|"):
        raise ValueError(f"Contenuto non valido per il replay {slug}")
    cache_file.write_text(text, encoding="utf-8")
    return text


# ── Parsing log ───────────────────────────────────────────────────

class _SideState:
    def __init__(self, slot: str):
        self.data = SideData(slot=slot)
        self.nick_to_key: dict = {}

    def resolve(self, details_species: str) -> str:
        """Mappa una specie vista in battaglia sull'entry del team preview."""
        s = canonical_species(details_species)
        team = self.data.team
        sid = to_id(s)
        for i, p in enumerate(team):
            if to_id(p) == sid:
                return p
        for i, p in enumerate(team):
            if p.endswith("-*") and sid.startswith(to_id(p[:-2])):
                team[i] = s                      # wildcard risolta con la forma reale
                return s
        for p in team:
            if s.startswith(p + "-"):            # forma di battaglia (es. Palafin-Hero)
                return p
        bk = _base_key(s)
        for p in team:
            if _base_key(p) == bk:               # Species Clause → match per specie base
                return p
        team.append(s)
        return s


def _split_ident(ident: str) -> Tuple[str, str]:
    """'p1a: Garchomp' → ('p1', 'Garchomp')."""
    pos, _, nick = (ident or "").partition(":")
    return pos.strip()[:2], nick.strip()


def parse_log(log: str, replay_id: str = "") -> ParsedLog:
    sides = {"p1": _SideState("p1"), "p2": _SideState("p2")}
    parsed = ParsedLog(replay_id=replay_id)
    started_turns = False

    for line in log.splitlines():
        if not line.startswith("|"):
            continue
        parts = line.split("|")
        if len(parts) < 2:
            continue
        tag = parts[1]

        if tag == "player" and len(parts) >= 4 and parts[2] in sides:
            sd = sides[parts[2]].data
            if parts[3]:
                sd.name = parts[3]
            if len(parts) >= 6 and parts[5].strip().isdigit():
                sd.rating = int(parts[5].strip())

        elif tag == "tier" and len(parts) > 2:
            parsed.format = parts[2]

        elif tag == "poke" and len(parts) > 3 and parts[2] in sides:
            species = canonical_species(parts[3])
            team = sides[parts[2]].data.team
            if species and species not in team:
                team.append(species)

        elif tag == "showteam" and len(parts) > 2 and parts[2] in sides:
            sides[parts[2]].data.showteam = True

        elif tag == "turn":
            started_turns = True

        elif tag in ("switch", "drag", "replace") and len(parts) > 3:
            slot, nick = _split_ident(parts[2])
            if slot not in sides:
                continue
            st = sides[slot]
            key = st.resolve(parts[3])
            st.nick_to_key[nick] = key
            if is_mega_forme(parts[3]) and not st.data.mega:
                st.data.mega, st.data.mega_forme = key, parts[3].split(",")[0].strip()
            if tag == "replace":
                continue
            if not started_turns:
                if key not in st.data.lead:
                    st.data.lead.append(key)
            elif key not in st.data.lead and key not in st.data.back:
                st.data.back.append(key)

        elif tag in ("detailschange", "-formechange") and len(parts) > 3:
            slot, nick = _split_ident(parts[2])
            if slot in sides and is_mega_forme(parts[3]):
                st = sides[slot]
                key = st.nick_to_key.get(nick) or st.resolve(parts[3])
                if not st.data.mega:
                    st.data.mega, st.data.mega_forme = key, parts[3].split(",")[0].strip()

        elif tag == "-mega" and len(parts) > 2:
            slot, nick = _split_ident(parts[2])
            if slot in sides:
                st = sides[slot]
                key = st.nick_to_key.get(nick)
                if key and not st.data.mega:
                    st.data.mega = key

        elif tag == "move" and len(parts) > 3:
            if any(p.startswith("[from]") for p in parts[4:]):
                continue
            slot, nick = _split_ident(parts[2])
            if slot in sides and parts[3] and parts[3] != "Struggle":
                st = sides[slot]
                key = st.nick_to_key.get(nick)
                if key:
                    st.data.moves.setdefault(key, Counter())[parts[3]] += 1

        elif tag == "win" and len(parts) > 2:
            parsed.winner = parts[2]
        elif tag == "tie":
            parsed.winner = "tie"

    parsed.sides = {k: v.data for k, v in sides.items()}
    return parsed


def orient(parsed: ParsedLog, my_names: Iterable[str]) -> Optional[GameSummary]:
    """Individua il lato del giocatore del foglio e restituisce il GameSummary."""
    ids = {to_id(n) for n in my_names if n}
    me_slot = next((s for s, d in parsed.sides.items() if to_id(d.name) in ids), None)
    if not me_slot:
        return None
    opp_slot = "p2" if me_slot == "p1" else "p1"
    me, opp = parsed.sides[me_slot], parsed.sides[opp_slot]
    won = None
    if parsed.winner and parsed.winner != "tie":
        won = to_id(parsed.winner) == to_id(me.name)
    return GameSummary(me=me, opp=opp, won=won, format=parsed.format)


def guess_player_names(parsed_logs: List[ParsedLog]) -> List[str]:
    """Fallback: il nickname presente nel maggior numero di replay."""
    c = Counter()
    for p in parsed_logs:
        for d in p.sides.values():
            if d.name:
                c[d.name] += 1
    return [c.most_common(1)[0][0]] if c else []


# ── Import on-demand nel DB interno ───────────────────────────────

def is_in_db(match_id: str) -> bool:
    from database.connection import SessionLocal
    from database.models_v2 import MatchV2
    with SessionLocal() as session:
        return session.query(MatchV2.id).filter_by(id=match_id).first() is not None


def ensure_in_db(slug: str) -> str:
    """
    Garantisce che il replay sia presente nel DB interno e restituisce il
    match_id da passare a ReplayAnalyzerUI.display_match().
    """
    match_id = match_id_from_slug(slug)
    if is_in_db(match_id):
        return match_id
    from src.parser.showdown import parse_showdown_log
    from database.repository_v2 import save_parsed_match_to_db_v2
    log = fetch_log(slug)
    save_parsed_match_to_db_v2(parse_showdown_log(log), match_id)
    return match_id
