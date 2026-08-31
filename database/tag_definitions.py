"""
tag_definitions.py
==================
Definizioni statiche dei Tag VGC per il seeding iniziale del database.

Struttura: dizionario category -> lista di nomi tag.
I tag vengono usati per classificare:
  - Mosse (move_tag)
  - Abilità (ability_tag)
  - Strumenti (item_tag)
  - Field conditions per turno (turn_field_condition)
  - Archetipi di team (match_archetype)
"""

from typing import Dict, List

# ---------------------------------------------------------------------------
# Tag per categoria
# ---------------------------------------------------------------------------

TAGS: Dict[str, List[str]] = {
    # ── Archetipi di team ──────────────────────────────────────────────────
    "archetype": [
        "Trick Room",
        "Tailwind Offense",
        "Rain Team",
        "Sun Team",
        "Sand Team",
        "Snow Team",
        "Weather Team",
        "Setup Sweep",
        "Psyspam",
        "Dondozo",
        "Balance",
        "Hyper Offense",
        "Stall",
        "Unclassified",
    ],

    # ── Condizioni meteorologiche ──────────────────────────────────────────
    "weather": [
        "raindance",
        "sunnyday",
        "sandstorm",
        "hail",
        "snowscape",
        "clearskies",
    ],

    # ── Terreni ────────────────────────────────────────────────────────────
    "terrain": [
        "electricterrain",
        "grassyterrain",
        "psychicterrain",
        "mistyterrain",
    ],

    # ── Field conditions lato campo ────────────────────────────────────────
    "field_condition": [
        "trickroom",
        "gravity",
        "magicroom",
        "wonderroom",
    ],

    # ── Field conditions per lato (p1/p2) ─────────────────────────────────
    "side_condition": [
        "tailwind",
        "reflect",
        "lightscreen",
        "auroraveil",
        "stealthrock",
        "spikes",
        "toxicspikes",
        "stickyweb",
    ],

    # ── Categoria mossa ────────────────────────────────────────────────────
    "move_category": [
        "Physical",
        "Special",
        "Status",
    ],

    # ── Tipo elemento (per mosse, abilità, strumenti tipizzati) ───────────
    "type": [
        "Normal", "Fire", "Water", "Grass", "Electric", "Ice",
        "Fighting", "Poison", "Ground", "Flying", "Psychic",
        "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy",
    ],

    # ── Effetti speciali mosse ─────────────────────────────────────────────
    "move_effect": [
        "priority",          # priority != 0
        "spread",            # colpisce tutti gli avversari (adj)
        "redirection",       # follow-me, rage-powder
        "protection",        # protect, wide-guard, etc.
        "heal",              # recupera HP
        "recoil",            # danno di rimbalzo
        "weather_setter",    # imposta meteo
        "terrain_setter",    # imposta terreno
        "stat_boost",        # alza stat del proprio lato
        "stat_drop",         # abbassa stat del lato avversario
        "flinch",            # provoca flinch
        "status_inflict",    # infligge status (brn, par, slp, frz, psn, tox)
        "multi_hit",         # più colpi in un turno
        "two_turn",          # carica + attacco
        "field_setter",      # imposta field condition (TR, Gravity)
        "side_setter",       # imposta side condition (TW, Reflect)
        "hazard",            # imposta rocks/spikes
        "hazard_removal",    # defog, rapid-spin
        "switch_forcing",    # roar, whirlwind, dragon-tail
        "binding",           # mean-look, block
        "trapping",          # fire spin, wrap
        "faint_user",        # self-ko moves (explosion, self-destruct)
        "z_move",
        "max_move",
    ],

    # ── Effetti speciali abilità ───────────────────────────────────────────
    "ability_effect": [
        "weather_setter",     # drizzle, drought, etc.
        "terrain_setter",     # electric-surge, etc.
        "intimidate",         # abbassa ATK
        "redirection",        # lightning-rod, storm-drain
        "stat_boost",         # beast-boost, moxie, etc.
        "stat_drop_immunity", # clear-body, white-smoke
        "status_immunity",    # immunity, insomnia, etc.
        "priority_boost",     # gale-wings, triage
        "contact_damage",     # rough-skin, iron-barbs
        "type_immunity",      # levitate, flash-fire, etc.
        "speed_control",      # swift-swim, chlorophyll, etc.
        "damage_boost",       # adaptability, technician, etc.
        "trace",              # copia abilità
        "item_interact",      # interagisce con strumenti
        "entry_hazard_immune",# magic-guard, magic-bounce
        "trick_room_related", # analytic, slow-start
    ],

    # ── Categorie strumenti ────────────────────────────────────────────────
    "item_category": [
        "choice",          # choice-band, scarf, specs
        "berry",           # qualsiasi bacca
        "berry_heal",      # sitrus, oran
        "berry_stat",      # liechi, salac
        "berry_pinch",     # carattere/attivazione <25% HP
        "held_boost",      # life-orb, muscle-band, etc.
        "defensive",       # leftovers, rocky-helmet, eviolite
        "terrain_seed",    # misty-seed, electric-seed, etc.
        "type_gem",        # normal-gem, ecc.
        "mega_stone",      # megapietra
        "z_crystal",       # cristallo-z
        "utility",         # red-card, eject-button, eject-pack
        "speed_control",   # choice-scarf, iron-ball
        "booster_energy",
        "ability_shield",
        "clear_amulet",
        "covert-cloak",
    ],
}

# ---------------------------------------------------------------------------
# Mapping: nomi di mosse → tag_name da assegnare (seed iniziale)
# Il seeder leggerà moves.json e per ogni mossa controllata da questo map
# inserirà le righe in move_tag.
# ---------------------------------------------------------------------------

MOVE_TAG_MAP: Dict[str, List[str]] = {
    # Protection
    "protect":       ["protection"],
    "detect":        ["protection"],
    "wideguard":     ["protection", "spread"],
    "quickguard":    ["protection", "priority"],
    "matblock":      ["protection"],
    "craftyshield":  ["protection"],
    "spikyshield":   ["protection"],
    "kingsshield":   ["protection"],
    "banefulbunker": ["protection"],
    "silktrap":      ["protection"],
    "obstruct":      ["protection"],

    # Redirection
    "followme":    ["redirection"],
    "ragepowder":  ["redirection"],

    # Weather setters
    "raindance":   ["weather_setter"],
    "sunnyday":    ["weather_setter"],
    "sandstorm":   ["weather_setter"],
    "hail":        ["weather_setter"],
    "snowscape":   ["weather_setter"],
    "chilly reception": ["weather_setter"],

    # Terrain setters
    "electricterrain": ["terrain_setter"],
    "grassyterrain":   ["terrain_setter"],
    "psychicterrain":  ["terrain_setter"],
    "mistyterrain":    ["terrain_setter"],

    # Field conditions
    "trickroom":   ["field_setter"],
    "gravity":     ["field_setter"],
    "magicroom":   ["field_setter"],
    "wonderroom":  ["field_setter"],

    # Side conditions
    "tailwind":    ["side_setter"],
    "reflect":     ["side_setter"],
    "lightscreen": ["side_setter"],
    "auroraveil":  ["side_setter"],

    # Hazards
    "stealthrock": ["hazard", "side_setter"],
    "spikes":      ["hazard", "side_setter"],
    "toxicspikes": ["hazard", "side_setter", "status_inflict"],
    "stickyweb":   ["hazard", "side_setter"],

    # Hazard removal
    "defog":       ["hazard_removal"],
    "rapidspin":   ["hazard_removal"],
    "courtchange": ["hazard_removal"],

    # Priority moves
    "extremespeed":   ["priority"],
    "fakeout":        ["priority"],
    "firstimpression": ["priority"],
    "iceshard":        ["priority"],
    "aquajet":         ["priority"],
    "bulletpunch":     ["priority"],
    "shadowsneak":     ["priority"],
    "suckerpunch":     ["priority"],
    "vacuumwave":      ["priority"],
    "machpunch":       ["priority"],

    # Spread moves
    "earthquake":      ["spread"],
    "eruption":        ["spread"],
    "glaciallance":    ["spread"],
    "heatwave":        ["spread"],
    "blizzard":        ["spread"],
    "discharge":       ["spread"],
    "surf":            ["spread"],
    "sludgewave":      ["spread"],
    "rockslide":       ["spread"],
    "darkestlariat":   ["spread"],
    "bulldoze":        ["spread", "stat_drop"],
    "hypervoice":      ["spread"],
    "moonblast":       ["spread"],
    "astralbarrage":   ["spread"],
    "dazzlinggleam":   ["spread"],
    "muddywater":      ["spread", "stat_drop"],
    "razorleaf":       ["spread"],
    "powderedsnow":    ["spread"],
    "iciclespear":     ["spread", "multi_hit"],

    # Status
    "willowisp":    ["status_inflict"],
    "thunderwave":  ["status_inflict"],
    "toxic":        ["status_inflict"],
    "poisonpowder": ["status_inflict"],
    "spore":        ["status_inflict"],
    "sleeppowder":  ["status_inflict"],
    "glare":        ["status_inflict"],
    "yawn":         ["status_inflict"],
    "sing":         ["status_inflict"],
    "hypnosis":     ["status_inflict"],
    "lovelykiss":   ["status_inflict"],

    # Stat drops (opponent)
    "intimidate":    ["stat_drop"],  # ability, not move — but keep for completeness
    "featherdance":  ["stat_drop"],
    "partingshot":   ["stat_drop"],
    "icychill":      ["stat_drop"],
    "memento":       ["stat_drop", "faint_user"],
    "syrupbomb":     ["stat_drop"],
    "leer":          ["stat_drop"],
    "growl":         ["stat_drop"],
    "charm":         ["stat_drop"],
    "screech":       ["stat_drop"],

    # Stat boosts
    "swordsdance":  ["stat_boost"],
    "nastyplot":    ["stat_boost"],
    "calmmind":     ["stat_boost"],
    "quiverdance":  ["stat_boost"],
    "dragondance":  ["stat_boost"],
    "shellsmash":   ["stat_boost"],
    "coil":         ["stat_boost"],
    "bulkup":       ["stat_boost"],
    "workup":       ["stat_boost"],
    "geomancy":     ["stat_boost"],
    "victorydance": ["stat_boost"],

    # Heal
    "recover":      ["heal"],
    "roost":        ["heal"],
    "moonlight":    ["heal"],
    "synthesis":    ["heal"],
    "morningsun":   ["heal"],
    "softboiled":   ["heal"],
    "milkdrink":    ["heal"],
    "slackoff":     ["heal"],
    "shoreup":      ["heal"],
    "junglehealing": ["heal"],
    "lifedew":      ["heal"],
    "pollenpuff":   ["heal"],

    # Faint user
    "explosion":      ["faint_user", "spread"],
    "selfdestructmove": ["faint_user", "spread"],
    "healingwish":    ["faint_user"],
    "lunarblessing":  ["heal"],
    "lunardance":     ["faint_user"],
    "finalgambit":    ["faint_user"],
    "mistyexplosion": ["faint_user", "spread"],
}

# ---------------------------------------------------------------------------
# Mapping: nomi di abilità → tag_name
# ---------------------------------------------------------------------------

ABILITY_TAG_MAP: Dict[str, List[str]] = {
    # Weather setters
    "drizzle":        ["weather_setter"],
    "drought":        ["weather_setter"],
    "snowwarning":    ["weather_setter"],
    "sandstream":     ["weather_setter"],
    "cloudnine":      ["weather_setter"],
    "airlock":        ["weather_setter"],

    # Terrain setters
    "electricsurge":  ["terrain_setter"],
    "grassysurge":    ["terrain_setter"],
    "psychicsurge":   ["terrain_setter"],
    "mistysurge":     ["terrain_setter"],

    # Intimidate
    "intimidate":     ["intimidate", "stat_drop"],
    "costar":         ["stat_boost"],

    # Redirection
    "lightningrod":   ["redirection", "type_immunity"],
    "stormdrain":     ["redirection", "type_immunity"],

    # Speed control
    "swiftsim":       ["speed_control"],
    "swiftswim":      ["speed_control"],
    "chlorophyll":    ["speed_control"],
    "slushrush":      ["speed_control"],
    "sandrush":       ["speed_control"],
    "surgesurfer":    ["speed_control"],
    "slowstart":      ["trick_room_related"],
    "analytic":       ["trick_room_related"],

    # Stat boost on entry
    "beastboost":     ["stat_boost"],
    "moxie":          ["stat_boost"],
    "soulheart":      ["stat_boost"],
    "chilling-neigh": ["stat_boost"],
    "chillingneigh":  ["stat_boost"],
    "asone":          ["stat_boost"],

    # Type immunity
    "levitate":       ["type_immunity"],
    "flashfire":      ["type_immunity"],
    "waterabsorb":    ["type_immunity"],
    "voltabsorb":     ["type_immunity"],
    "sapsipper":      ["type_immunity"],
    "eartheater":     ["type_immunity"],
    "wellbakedbody":  ["type_immunity"],
    "windrider":      ["type_immunity"],
    "motordriveability": ["type_immunity", "speed_control"],
    "motordrive":     ["type_immunity", "speed_control"],

    # Damage reduction
    "friendguard":    ["defensive"],
    "fluffy":         ["defensive"],
    "filter":         ["defensive"],
    "solidrock":      ["defensive"],
    "multiscale":     ["defensive"],
    "shadowshield":   ["defensive"],

    # Contact damage
    "roughskin":      ["contact_damage"],
    "ironbarbs":      ["contact_damage"],
    "cottondown":     ["contact_damage", "stat_drop"],

    # Damage boost
    "adaptability":   ["damage_boost"],
    "technician":     ["damage_boost"],
    "strongjaw":      ["damage_boost"],
    "sheerforce":     ["damage_boost"],
    "toughclaws":     ["damage_boost"],
    "pixilate":       ["damage_boost"],
    "aerilate":       ["damage_boost"],
    "refrigerate":    ["damage_boost"],
    "galvanize":      ["damage_boost"],

    # Priority
    "galewings":      ["priority_boost"],
    "triage":         ["priority_boost"],
    "prankster":      ["priority_boost"],
    "quickdraw":      ["priority_boost"],

    # Booster energy interaction
    "protosynthesis": ["speed_control", "stat_boost", "item_interact"],
    "quarkdrive":     ["speed_control", "stat_boost", "item_interact"],
    "orichalcumpulse": ["damage_boost"],
    "hadronengine":   ["damage_boost", "terrain_setter"],

    # Utility
    "trace":          ["trace"],
    "imposter":       ["trace"],
    "neutralizinggas": ["stat_drop"],
    "unnerve":        ["item_interact"],
    "magicguard":     ["entry_hazard_immune"],
    "magicbounce":    ["entry_hazard_immune"],
}

# ---------------------------------------------------------------------------
# Mapping: nomi di strumenti → tag_name
# ---------------------------------------------------------------------------

ITEM_TAG_MAP: Dict[str, List[str]] = {
    # Choice items
    "choiceband":    ["choice", "held_boost"],
    "choicescarf":   ["choice", "speed_control"],
    "choicespecs":   ["choice", "held_boost"],

    # Berries
    "sitrusberry":   ["berry", "berry_heal"],
    "oranberry":     ["berry", "berry_heal"],
    "aguavberry":    ["berry", "berry_heal"],
    "figyberry":     ["berry", "berry_heal"],
    "magoberry":     ["berry", "berry_heal"],
    "wikiberry":     ["berry", "berry_heal"],
    "iapapaberry":   ["berry", "berry_heal"],
    "lum berry":     ["berry"],
    "lumberry":      ["berry"],
    "cheriberry":    ["berry"],
    "chestoberry":   ["berry"],
    "pechaberry":    ["berry"],
    "rawstberry":    ["berry"],
    "aspearberry":   ["berry"],
    "leppaberry":    ["berry"],
    "liechiberry":   ["berry", "berry_stat"],
    "salacberry":    ["berry", "berry_stat"],
    "petayaberry":   ["berry", "berry_stat"],
    "ganglonberry":  ["berry", "berry_stat"],
    "starfberry":    ["berry", "berry_stat"],
    "enigmaberry":   ["berry"],
    "micleberry":    ["berry"],
    "custapberry":   ["berry", "priority_boost"],
    "jabocaberry":   ["berry", "contact_damage"],
    "rowapberry":    ["berry", "contact_damage"],
    "keeberry":      ["berry", "stat_boost"],
    "marangaberry":  ["berry", "stat_boost"],
    "weaknesspolicy": ["item_interact", "stat_boost"],
    "powerherb":     ["utility"],

    # Terrain seeds
    "electricseed":  ["terrain_seed", "stat_boost"],
    "grassyseed":    ["terrain_seed", "stat_boost"],
    "psychicseed":   ["terrain_seed", "stat_boost"],
    "mistyseed":     ["terrain_seed", "stat_boost"],

    # Damage boosts
    "lifeorb":       ["held_boost"],
    "muscleband":    ["held_boost"],
    "wiseglasses":   ["held_boost"],
    "expertbelt":    ["held_boost"],
    "silkscarf":     ["held_boost"],
    "blackbelt":     ["held_boost"],
    "nevermeltice":  ["held_boost"],
    "blackglasses":  ["held_boost"],
    "charcoal":      ["held_boost"],
    "mysticwater":   ["held_boost"],
    "magnet":        ["held_boost"],
    "miracleseed":   ["held_boost"],
    "metalcoat":     ["held_boost"],
    "twistedspoon":  ["held_boost"],
    "hardstone":     ["held_boost"],
    "sharpbeak":     ["held_boost"],
    "poisonbarb":    ["held_boost"],
    "softsand":      ["held_boost"],
    "spelltag":      ["held_boost"],
    "dragonfang":    ["held_boost"],
    "fairyfeather":  ["held_boost"],
    "punchingglove": ["held_boost"],
    "throatspray":   ["held_boost", "stat_boost"],

    # Defensive
    "leftovers":     ["defensive"],
    "rockyhelmet":   ["defensive", "contact_damage"],
    "eviolite":      ["defensive"],
    "assaultvest":   ["defensive"],
    "heavydutyboots": ["defensive", "entry_hazard_immune"],

    # Utility / Reactive
    "redcard":        ["utility"],
    "ejectbutton":    ["utility"],
    "ejectpack":      ["utility"],
    "shedshell":      ["utility"],
    "smokescreen":    ["utility"],
    "airballoon":     ["utility", "type_immunity"],
    "ringtarget":     ["utility"],
    "safetygoggles":  ["utility"],
    "clearamulet":    ["utility", "stat_drop_immunity"],
    "covertcloak":    ["utility"],
    "abilitysheild":  ["utility"],
    "abilityshield":  ["utility"],

    # Booster energy
    "boosterenergy": ["item_interact", "stat_boost", "speed_control"],

    # Iron ball (speed control negative)
    "ironball":      ["speed_control"],

    # Others
    "loadeddice":    ["held_boost", "multi_hit"],
    "metronome":     ["held_boost"],
    "shellbell":     ["heal"],
}
