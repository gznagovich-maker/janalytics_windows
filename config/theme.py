# theme.py
# ═══════════════════════════════════════════════════════════════
# Design System — "Hisui Goodra" Dark Edition
# ───────────────────────────────────────────────────────────────
# Palette Strategy:
#   Goodra di Hisui è un Drago/Acciaio con tre famiglie cromatiche:
#   1. BRONZO/ORO     (#C49A3C) → shell metallica, corna — accento primario
#   2. LAVANDA ACCIAIO (#8577A8) → corpo morbido desaturato — accento secondario
#   3. GRIGIO ACCIAIO  (#607080) → squame metalliche — accento terziario
#   Background: nero assoluto (#000000) per massimo contrasto e modernità.
#   Testo base: bianco caldo (#DEDAD4), non puro — riduce affaticamento visivo.
# ═══════════════════════════════════════════════════════════════

class Palette:
    # --- Backgrounds (pure black layered system) ---
    BG_APP              = "#000000"   # Nero assoluto — canvas principale
    BG_SURFACE          = "#0A0B0D"   # Quasi nero con sfumatura acciaio — sidebar/pannelli
    BG_SURFACE_ELEVATED = "#131519"   # Acciaio scuro — card, header sezioni
    BG_CARD             = "#1C1F26"   # Superfici in primo piano — menu, dialoghi

    # --- Primary Accent: Bronze/Gold (Goodra's shell & horns) ---
    PRIMARY        = "#C49A3C"   # Bronzo saturo — CTA principale, bordi attivi
    PRIMARY_BRIGHT = "#D4AA52"   # Oro acceso — hover sugli accenti
    PRIMARY_DIM    = "#7A6025"   # Bronzo profondo — pressed/active

    # --- Secondary Accent: Steel Lavender (Goodra's soft body) ---
    SECONDARY      = "#8577A8"   # Lavanda acciaio — info secondaria, badge
    SECONDARY_DIM  = "#5A5075"   # Lavanda scura — hover secondario

    # --- Tertiary Accent: Metallic Steel Blue (Goodra's scales) ---
    TERTIARY       = "#607080"   # Grigio acciaio blu — dettagli, bordi enfatici
    TERTIARY_LIGHT = "#8A9DB0"   # Acciaio chiaro — testo enfatico terziario

    # --- Text ---
    TEXT_PRIMARY = "#DEDAD4"   # Bianco caldo (patina metallica) — testo base
    TEXT_MUTED   = "#5E6575"   # Grigio freddo — etichette, descrizioni

    # --- Borders ---
    BORDER_COLOR = "#1C1F26"   # Bordo standard (BG_CARD)
    BORDER_LIGHT = "#252932"   # Bordo separatore visibile

    # --- Semantic States ---
    DANGER      = "#8A3838"   # Rosso desaturato — azioni distruttive
    DANGER_BRIGHT = "#B04545"  # Rosso hover
    SUCCESS     = "#3D6B50"   # Verde scuro — feedback positivo
    WARNING     = "#8A6830"   # Bronzo scuro — avvertimento

    # --- Chart Bar Colors (Goodra palette, desaturated for data viz) ---
    CHART_HP  = "#3D7A5A"   # Verde muted
    CHART_ATK = "#8A3838"   # Rosso muted
    CHART_DEF = "#607080"   # Grigio acciaio
    CHART_SPA = "#5A5075"   # Lavanda scura
    CHART_SPD = "#8577A8"   # Lavanda primario
    CHART_SPE = "#C49A3C"   # Bronzo — velocità, accento primario


class Fonts:
    # UI Text: Segoe UI Variable (Win11) → Inter → Segoe UI
    # Data/Numbers: Cascadia Code (Win11) → Consolas (Win7+) → monospace
    FAMILY_UI      = "'Segoe UI Variable', 'Inter', 'Segoe UI', sans-serif"
    FAMILY_DATA    = "'Cascadia Code', 'Consolas', 'Courier New', monospace"
    FAMILY_DEFAULT = FAMILY_UI

    SIZE_XS     = "11px"
    SIZE_SMALL  = "12px"
    SIZE_BASE   = "13px"
    SIZE_MEDIUM = "14px"
    SIZE_LARGE  = "16px"
    SIZE_TITLE  = "20px"
    SIZE_DISPLAY = "24px"

    WEIGHT_LIGHT  = "300"
    WEIGHT_NORMAL = "400"
    WEIGHT_MEDIUM = "500"
    WEIGHT_SEMI   = "600"
    WEIGHT_BOLD   = "700"


class Spacing:
    """Grid 8pt system"""
    XS  = 4
    SM  = 8
    MD  = 16
    LG  = 24
    XL  = 32
    XXL = 48


# ─── Icon Map (Unicode line-art, sidebar navigation) ──────────
class Icons:
    LIBRARY     = "◎"   # Viewfinder — libreria replay
    IMPORT      = "⊕"   # Circled plus — importa log
    BULK_IMPORT = "⊞"   # Squared plus — import multiplo
    META_STATS  = "⬡"   # Hexagon — meta statistics
    CORE        = "◉"   # Target — analisi core
    TEAM        = "⬟"   # Diamond — team analysis
    TOURNAMENT  = "✦"   # 4-pointed star — tornei
    BACK        = "‹"   # Single chevron — back navigation
    MENU        = "⋮⋮"  # Grid dots — hamburger alt
