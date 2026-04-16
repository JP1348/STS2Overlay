"""
relics.py
Relic data for STS1 and STS2.
Relic IDs confirmed from real STS2 .run files: format is "RELIC.RELIC_NAME"

Confirmed STS2 relics from run data:
  RELIC.LARGE_CAPSULE, RELIC.ORICHALCUM, RELIC.FUNERARY_MASK,
  RELIC.GOLDEN_PEARL, RELIC.BOOMING_CONCH
"""

RELICS = {

    # =========================================================
    # CONFIRMED STS2 RELICS (from run data)
    # =========================================================

    "RELIC.LARGE_CAPSULE": {
        "name": "Large Capsule",
        "class": "any",
        "amplifies": [],
        "tags": ["starter"],
        "note": "Starting relic — confirmed STS2",
        "game": "sts2",
    },
    "RELIC.ORICHALCUM": {
        "name": "Orichalcum",
        "class": "any",
        "amplifies": ["block_gen", "block"],
        "tags": ["block_gen", "sustain"],
        "note": "Gain 6 Block if you end turn with no Block — strong with block builds",
        "game": "sts2",
    },
    "RELIC.FUNERARY_MASK": {
        "name": "Funerary Mask",
        "class": "any",
        "amplifies": ["exhaust", "blight", "soul"],
        "tags": ["exhaust_payoff"],
        "note": "Confirmed STS2 relic — exhaust/necrobinder synergy likely",
        "game": "sts2",
    },
    "RELIC.GOLDEN_PEARL": {
        "name": "Golden Pearl",
        "class": "any",
        "amplifies": [],
        "tags": ["gold_gen"],
        "note": "Confirmed STS2 relic — gold generation",
        "game": "sts2",
    },
    "RELIC.BOOMING_CONCH": {
        "name": "Booming Conch",
        "class": "any",
        "amplifies": [],
        "tags": ["utility"],
        "note": "Confirmed STS2 relic",
        "game": "sts2",
    },

    # =========================================================
    # STS1 RELICS retained (RELIC. prefix format)
    # =========================================================

    "RELIC.BURNING_BLOOD": {
        "name": "Burning Blood",
        "class": "CHARACTER.IRONCLAD",
        "amplifies": [],
        "tags": ["sustain"],
        "note": "Heals 6 HP after each combat",
        "game": "sts1",
    },
    "RELIC.DEAD_BRANCH": {
        "name": "Dead Branch",
        "class": "CHARACTER.IRONCLAD",
        "amplifies": ["exhaust", "exhaust_enabler", "exhaust_payoff"],
        "tags": ["exhaust_payoff"],
        "note": "Generates a random card each time you exhaust",
        "game": "sts1",
    },
    "RELIC.BRIMSTONE": {
        "name": "Brimstone",
        "class": "CHARACTER.IRONCLAD",
        "amplifies": ["strength", "strength_gen", "strength_payoff"],
        "tags": ["strength_gen"],
        "note": "Grants 2 Strength each combat",
        "game": "sts1",
    },
    "RELIC.KUNAI": {
        "name": "Kunai",
        "class": "CHARACTER.SILENT",
        "amplifies": ["shiv", "shiv_gen"],
        "tags": ["shiv_payoff"],
        "note": "Gain 1 Dexterity every 3 attacks played",
        "game": "sts1",
    },
    "RELIC.NUNCHAKU": {
        "name": "Nunchaku",
        "class": "any",
        "amplifies": ["attack"],
        "tags": ["energy_payoff"],
        "note": "Gain 1 Energy after playing 10 attacks",
        "game": "sts1",
    },
    "RELIC.BLACK_STAR": {
        "name": "Black Star",
        "class": "any",
        "amplifies": [],
        "tags": ["relic_gen"],
        "note": "Elites drop an extra relic",
        "game": "sts1",
    },
    "RELIC.RUNIC_DOME": {
        "name": "Runic Dome",
        "class": "any",
        "amplifies": ["energy"],
        "tags": ["energy_gen"],
        "note": "+1 Energy/turn but can't see enemy intents",
        "game": "sts1",
    },
    "RELIC.SOZU": {
        "name": "Sozu",
        "class": "any",
        "amplifies": [],
        "tags": [],
        "note": "+1 Energy but no potions",
        "game": "sts1",
    },
    "RELIC.PHILOSOPHERS_STONE": {
        "name": "Philosopher's Stone",
        "class": "any",
        "amplifies": ["energy", "strength"],
        "tags": ["energy_gen"],
        "note": "+1 Energy but enemies gain 1 Strength",
        "game": "sts1",
    },
    "RELIC.ASTROLABE": {
        "name": "Astrolabe",
        "class": "any",
        "amplifies": [],
        "tags": ["deck_transform"],
        "note": "Transform 3 cards",
        "game": "sts1",
    },
    "RELIC.CURSED_KEY": {
        "name": "Cursed Key",
        "class": "any",
        "amplifies": [],
        "tags": ["gold_gen"],
        "note": "+1 Energy + extra gold from chests but adds Curses",
        "game": "sts1",
    },
}


def get_relic(relic_id: str) -> dict:
    return RELICS.get(relic_id, {})


def relics_amplifying(tags: list) -> list:
    """Return relic IDs that amplify any of the given archetype/tags."""
    return [
        rid for rid, relic in RELICS.items()
        if any(t in relic.get("amplifies", []) for t in tags)
    ]
