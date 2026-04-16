"""
enemies.py
Boss and elite enemy data for STS2.

HP scaling rules (from wiki):
  A0–A7  : base HP
  A8+    : hp_a8 (confirmed exact values from wiki where available)
  A9+    : enemies deal more damage (+~10% damage, no HP change beyond A8)
  A10    : two Act 3 bosses fought back-to-back

HP values confirmed from slaythespire.wiki.gg — marked TODO where unconfirmed.

Structure for each boss entry:
  hp          — base HP (A0–A7)
  hp_a8       — HP at Ascension 8+ (None if unknown, falls back to hp)
  act         — which act (1, 2, 3)
  area        — act region name (Overgrowth, Underdocks, ...)
  components  — list of sub-enemies for multi-enemy fights
  abilities   — key moves with damage and effect
  gimmicks    — special mechanics that require specific counterplay
  counters    — deck traits / strategies that help against this boss
  punishes    — deck traits / playstyles this boss specifically punishes
"""

from typing import Optional


# ---------------------------------------------------------------------------
# Helper: get scaled HP for a boss at a given ascension
# ---------------------------------------------------------------------------

def get_boss_hp(boss_id: str, ascension: int = 0) -> int:
    """Return HP for a boss component at the given ascension level."""
    entry = BOSSES.get(boss_id)
    if not entry:
        return 0
    if ascension >= 8 and entry.get("hp_a8") is not None:
        return entry["hp_a8"]
    return entry["hp"]


def get_component_hp(boss_id: str, component_name: str, ascension: int = 0) -> int:
    """Return HP for a named sub-component (e.g. 'Kin Follower') at ascension."""
    entry = BOSSES.get(boss_id, {})
    for comp in entry.get("components", []):
        if comp["name"] == component_name:
            if ascension >= 8 and comp.get("hp_a8") is not None:
                return comp["hp_a8"]
            return comp["hp"]
    return 0


def get_act_bosses(act: int) -> list:
    """Return list of boss IDs for a given act."""
    return [bid for bid, b in BOSSES.items() if b["act"] == act]


def boss_tips(boss_id: str, ascension: int = 0) -> list:
    """
    Return formatted tip dicts for the overlay describing the upcoming boss.
    Caller should resolve which bosses are possible for the current act/floor.
    """
    entry = BOSSES.get(boss_id)
    if not entry:
        return []

    hp = get_boss_hp(boss_id, ascension)
    tips = []

    # Header
    tips.append({
        "text": f"── {entry['name']}  HP {hp} ──",
        "tone": "neutral",
    })

    # Gimmicks first — highest priority info
    for g in entry.get("gimmicks", []):
        tips.append({"text": f"  ⚠ {g}", "tone": "warn"})

    # Counters
    for c in entry.get("counters", []):
        tips.append({"text": f"  ✓ {c}", "tone": "good"})

    # What it punishes
    for p in entry.get("punishes", []):
        tips.append({"text": f"  ✗ {p}", "tone": "warn"})

    # A9 damage note
    if ascension >= 9:
        tips.append({"text": "  A9+: Boss deals ~10% more damage", "tone": "warn"})

    return tips


# ---------------------------------------------------------------------------
# ACT 1 BOSSES — floor 17 (Overgrowth or Underdocks depending on seed)
# ---------------------------------------------------------------------------

BOSSES = {

    # ── OVERGROWTH ACT 1 ───────────────────────────────────────────────────

    "ceremonial_beast": {
        "name": "Ceremonial Beast",
        "act": 1,
        "area": "Overgrowth",
        "hp": 252,
        "hp_a8": 262,
        "components": [],   # single enemy
        "abilities": [
            # Phase 1
            {"name": "Stamp",       "damage": 0,  "effect": "Sets Plow threshold (150 HP). When reached: stunned, loses all Strength."},
            {"name": "Plow",        "damage": 18, "effect": "Gains 2 Strength. (A9: 20 dmg)"},
            # Phase 2 (triggered when HP drops to Plow threshold)
            {"name": "Beast Cry",   "damage": 0,  "effect": "Applies 1 Ringing — you can only play 1 card next turn."},
            {"name": "Stomp",       "damage": 15, "effect": "(A9: 17 dmg)"},
            {"name": "Crush",       "damage": 17, "effect": "Gains 3 Strength. (A9: 19 dmg, 4 Str)"},
        ],
        "gimmicks": [
            "Phase 1: Gains 2 Str each turn — kill fast or take massive damage",
            "Phase trigger at 150 HP: you get a free turn (stun), then Phase 2",
            "Beast Cry (Phase 2): limits you to 1 card played — have 0-cost cards ready",
            "Plow threshold is 160 HP at A9",
        ],
        "counters": [
            "Burst damage to clear Phase 1 quickly (fewer Plow stacks)",
            "0-cost cards / Shivs buffer Beast Cry turns",
            "AOE not needed — single target",
        ],
        "punishes": [
            "Slow decks — Str compounds fast in Phase 1",
            "Decks with no 0-cost answers — Beast Cry turns become dead turns",
        ],
    },

    "the_kin": {
        "name": "The Kin",
        "act": 1,
        "area": "Overgrowth",
        "hp": 190,      # Kin Priest (main target / fight lasts until Priest dies)
        "hp_a8": 199,
        "components": [
            {"name": "Kin Priest",   "hp": 190,   "hp_a8": 199,   "count": 1},
            {"name": "Kin Follower", "hp": 58,    "hp_a8": 62,    "count": 2,
             "note": "HP range 58-59 (62-63 A8). Both have Minion tag."},
        ],
        "abilities": [
            # Priest (fixed cycle: Orb of Frailty → Orb of Weakness → Soul Beam → Dark Ritual)
            {"name": "Orb of Frailty",  "damage": 8,  "effect": "Apply 1 Frail (block -25%). (A9: 9 dmg)"},
            {"name": "Orb of Weakness", "damage": 8,  "effect": "Apply 1 Weak (attack -25%). (A9: 9 dmg)"},
            {"name": "Soul Beam",       "damage": 9,  "effect": "3 hits of 3 dmg."},
            {"name": "Dark Ritual",     "damage": 0,  "effect": "Gains 2 Strength. (A9: 3 Str)"},
            # Followers (fixed cycle: Quick Slash → Boomerang → Power Dance, offset from each other)
            {"name": "Quick Slash",     "damage": 5,  "effect": "Single hit."},
            {"name": "Boomerang",       "damage": 4,  "effect": "2 hits of 2."},
            {"name": "Power Dance",     "damage": 0,  "effect": "Follower gains 2 Strength. (A9: 3 Str)"},
        ],
        "gimmicks": [
            "3-enemy fight: 1 Priest + 2 Followers — benefits strongly from AOE",
            "All three gain Strength over time — damage escalates each cycle",
            "Followers have Minion tag — killing them doesn't end the fight",
            "Priest move order is fixed and predictable (Frail → Weak → Beam → Ritual)",
            "Followers start offset so you take hits from both on different turns",
        ],
        "counters": [
            "AOE attacks hit all 3 simultaneously",
            "Kill Followers early to stop their Strength stacks",
            "Predictable Priest cycle — block on Beam/Frail/Weak turns",
            "Poison scales well across 3 targets",
        ],
        "punishes": [
            "Single-target only decks — Followers will overwhelm",
            "Weak/Frail sensitive decks — Priest applies both consistently",
        ],
    },

    "vantom": {
        "name": "Vantom",
        "act": 1,
        "area": "Overgrowth",
        "hp": 173,
        "hp_a8": 183,
        "components": [],
        "abilities": [
            # Fixed cycle: Ink Blot → Inky Lance → Dismember → Prepare
            {"name": "Ink Blot",   "damage": 7,  "effect": "(A9: 8 dmg)"},
            {"name": "Inky Lance", "damage": 12, "effect": "2 hits of 6. (A9: 2×7)"},
            {"name": "Dismember",  "damage": 27, "effect": "Shuffles 3 Wounds into discard pile. (A9: 30 dmg)"},
            {"name": "Prepare",    "damage": 0,  "effect": "Gains 2 Strength."},
        ],
        "gimmicks": [
            "Starts with 9 Slippery stacks — takes only 1 HP per hit until stacks are gone",
            "Multi-hit attacks (Inky Lance type) strip Slippery stacks faster",
            "Dismember deals 27 damage AND adds 3 Wounds to discard — block it",
            "Gains 2 Str every 4th turn — damage ramps over long fights",
        ],
        "counters": [
            "Multi-hit attacks break Slippery stacks fast (each hit removes 1 stack)",
            "Shivs / Blade Dance / Inky Lance type cards are ideal",
            "Poison ignores Slippery — each tick removes 1 stack",
            "Have 27+ block ready on turn 3 for Dismember",
        ],
        "punishes": [
            "Single big-hit decks — Slippery wastes your whole attack",
            "Decks without block on turn 3 — Dismember + Wounds is brutal",
        ],
    },

    # ── UNDERDOCKS ACT 1 ───────────────────────────────────────────────────
    # HP values TODO — wiki rate-limited, fill in when available

    "waterfall_giant": {
        "name": "Waterfall Giant",
        "act": 1,
        "area": "Underdocks",
        "hp": None,     # TODO: confirm from wiki
        "hp_a8": None,
        "components": [],
        "abilities": [],
        "gimmicks": [],
        "counters": [],
        "punishes": [],
    },

    "soul_fysh": {
        "name": "Soul Fysh",
        "act": 1,
        "area": "Underdocks",
        "hp": None,
        "hp_a8": None,
        "components": [],
        "abilities": [],
        "gimmicks": [],
        "counters": [],
        "punishes": [],
    },

    "lagavulin_matriarch": {
        "name": "Lagavulin Matriarch",
        "act": 1,
        "area": "Underdocks",
        "hp": None,
        "hp_a8": None,
        "components": [],
        "abilities": [],
        "gimmicks": [],
        "counters": [],
        "punishes": [],
    },

    # ── ACT 2 BOSSES — floor 33 ─────────────────────────────────────────────
    # TODO: confirm all HP values from wiki

    "the_insatiable": {
        "name": "The Insatiable",
        "act": 2,
        "area": "Act 2",
        "hp": None,
        "hp_a8": None,
        "components": [],
        "abilities": [],
        "gimmicks": [],
        "counters": [],
        "punishes": [],
    },

    "knowledge_demon": {
        "name": "Knowledge Demon",
        "act": 2,
        "area": "Act 2",
        "hp": None,
        "hp_a8": None,
        "components": [],
        "abilities": [],
        "gimmicks": [],
        "counters": [],
        "punishes": [],
    },

    "kaiser_crab": {
        "name": "Kaiser Crab",
        "act": 2,
        "area": "Act 2",
        "hp": None,
        "hp_a8": None,
        "components": [],
        "abilities": [],
        "gimmicks": [],
        "counters": [],
        "punishes": [],
    },

    # ── ACT 3 BOSSES — floor 48 (A10: two bosses back-to-back) ─────────────
    # TODO: confirm all HP values from wiki

    "queen": {
        "name": "Queen",
        "act": 3,
        "area": "Act 3",
        "hp": None,
        "hp_a8": None,
        "components": [],
        "abilities": [],
        "gimmicks": [],
        "counters": [],
        "punishes": [],
    },

    "test_subject": {
        "name": "Test Subject",
        "act": 3,
        "area": "Act 3",
        "hp": None,
        "hp_a8": None,
        "components": [],
        "abilities": [],
        "gimmicks": [],
        "counters": [],
        "punishes": [],
    },

    "doormaker": {
        "name": "Doormaker",
        "act": 3,
        "area": "Act 3",
        "hp": None,
        "hp_a8": None,
        "components": [],
        "abilities": [],
        "gimmicks": [],
        "counters": [],
        "punishes": [],
    },
}


# ---------------------------------------------------------------------------
# Floor → boss pool lookup (singleplayer floor numbers)
# Multiplayer: Act 1 boss on 16, Act 2 on 31, Act 3 on 45
# ---------------------------------------------------------------------------

BOSS_FLOOR = {
    1: 17,
    2: 33,
    3: 48,
}

# Which act areas can appear (randomised per seed per area)
ACT_AREAS = {
    1: ["Overgrowth", "Underdocks"],
    2: ["Act 2"],
    3: ["Act 3"],
}

BOSSES_BY_AREA = {
    "Overgrowth":  ["ceremonial_beast", "the_kin", "vantom"],
    "Underdocks":  ["waterfall_giant", "soul_fysh", "lagavulin_matriarch"],
    "Act 2":       ["the_insatiable", "knowledge_demon", "kaiser_crab"],
    "Act 3":       ["queen", "test_subject", "doormaker"],
}
