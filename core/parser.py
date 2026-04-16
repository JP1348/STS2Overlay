"""
parser.py
Parses an STS2 autosave JSON file and extracts relevant run state:
  - seed
  - current floor
  - character class
  - deck (list of cards)
  - relics
  - current HP / max HP
  - gold
  - map path choices made so far

NOTE: STS2 save format is not fully documented yet. Field names below
are based on STS1 conventions and will need validation against real
STS2 save files. Keys marked with # VERIFY should be confirmed
against actual STS2 save data.
"""

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RunState:
    seed: Optional[str] = None
    floor: int = 0
    character: Optional[str] = None
    deck: List[str] = field(default_factory=list)
    relics: List[str] = field(default_factory=list)
    hp: int = 0
    max_hp: int = 0
    gold: int = 0
    act: int = 1
    ascension: int = 0
    game_mode: str = "standard"
    raw: dict = field(default_factory=dict)

    def __str__(self):
        return (
            f"[Run State]\n"
            f"  Seed:      {self.seed}\n"
            f"  Character: {self.character}\n"
            f"  Ascension: {self.ascension}\n"
            f"  Act/Floor: {self.act} / {self.floor}\n"
            f"  HP:        {self.hp} / {self.max_hp}\n"
            f"  Gold:      {self.gold}\n"
            f"  Relics:    {', '.join(self.relics)}\n"
            f"  Deck ({len(self.deck)} cards): {', '.join(self.deck)}\n"
        )


def parse_run_history(path: str) -> RunState:
    """
    Parse a completed STS2 .run history file.
    Reconstructs the final run state by replaying floor-by-floor events.
    Field names confirmed from real STS2 run data.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[Parser] Failed to read run file: {e}")
        return RunState()

    state = RunState(raw=data)

    # --- Confirmed top-level fields ---
    state.ascension = data.get("ascension", 0)
    state.game_mode = data.get("game_mode", "standard")

    # Acts visited e.g. ["ACT.OVERGROWTH", "ACT.HIVE", "ACT.GLORY"]
    acts = data.get("acts", [])
    state.act = len(acts) if acts else 1

    # --- Reconstruct deck, relics, HP, gold by replaying map_point_history ---
    # map_point_history is a list of acts, each a list of floor events.
    # Each floor event has player_stats[0] with:
    #   cards_gained, cards_removed, relic_choices, current_hp, max_hp, current_gold
    deck  = []
    relics = []
    hp = max_hp = gold = 0
    floor = 0
    character = None

    for act_floors in data.get("map_point_history", []):
        for map_point in act_floors:
            floor += 1
            for ps in map_point.get("player_stats", []):

                # Character — stored as player_id in history; class comes from
                # cards_gained starter cards (e.g. CARD.STRIKE_NECROBINDER)
                if character is None:
                    for cg in ps.get("cards_gained", []):
                        cid = cg.get("id", "")
                        if "IRONCLAD" in cid:   character = "CHARACTER.IRONCLAD";   break
                        if "SILENT" in cid:     character = "CHARACTER.SILENT";     break
                        if "DEFECT" in cid:     character = "CHARACTER.DEFECT";     break
                        if "NECROBINDER" in cid: character = "CHARACTER.NECROBINDER"; break
                        if "REGENT" in cid:     character = "CHARACTER.REGENT";     break

                # Cards gained
                for cg in ps.get("cards_gained", []):
                    cid = cg.get("id")
                    if cid:
                        deck.append(cid)

                # Cards removed
                for cr in ps.get("cards_removed", []):
                    cid = cr.get("id")
                    if cid and cid in deck:
                        deck.remove(cid)

                # Relics picked
                for rc in ps.get("relic_choices", []):
                    if rc.get("was_picked"):
                        rid = rc.get("choice")
                        if rid and rid not in relics:
                            relics.append(rid)

                # Latest HP / gold snapshot
                if ps.get("current_hp") is not None:
                    hp      = ps["current_hp"]
                    max_hp  = ps.get("max_hp", max_hp)
                    gold    = ps.get("current_gold", gold)

    state.character = character
    state.deck      = deck
    state.relics    = relics
    state.hp        = hp
    state.max_hp    = max_hp
    state.gold      = gold
    state.floor     = floor

    # Seed not present in .run history files — will be in active run save
    state.seed = data.get("seed", "N/A (history file)")

    return state


def parse_save_file(path: str) -> RunState:
    """
    Load and parse an STS2 active run save file into a RunState object.
    Field names confirmed from .run history analysis; active save uses same schema.
    Falls back gracefully if any field is missing.
    """
    # .run history files — parse differently
    if path.endswith(".run") or path.endswith(".run.backup"):
        return parse_run_history(path)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[Parser] Failed to read save file: {e}")
        return RunState()

    state = RunState(raw=data)

    # --- Confirmed from STS2 .run data / likely same in active save ---
    state.ascension = data.get("ascension", 0)

    # --- These will be confirmed once we see an active mid-run save ---
    state.seed      = str(data.get("seed", "UNKNOWN"))
    state.floor     = data.get("floor", data.get("floor_num", 0))
    state.act       = data.get("act",   data.get("act_num",   1))
    state.character = data.get("character", data.get("character_chosen", None))
    state.hp        = data.get("current_hp",  data.get("hp", 0))
    state.max_hp    = data.get("max_hp", 0)
    state.gold      = data.get("current_gold", data.get("gold", 0))

    # --- Relics: STS2 uses "RELIC.ID" string format ---
    relics_raw = data.get("relics", [])
    if relics_raw and isinstance(relics_raw[0], dict):
        state.relics = [r.get("id", r.get("choice", str(r))) for r in relics_raw]
    else:
        state.relics = [str(r) for r in relics_raw]

    # --- Deck: STS2 uses "CARD.ID" string format ---
    deck_raw = data.get("cards", data.get("deck", []))
    if deck_raw and isinstance(deck_raw[0], dict):
        state.deck = [c.get("id", str(c)) for c in deck_raw]
    else:
        state.deck = [str(c) for c in deck_raw]

    return state


def load_from_directory(save_dir: str) -> Optional[RunState]:
    """Find and parse the most recently modified active run .save file in a directory."""
    excluded = {"progress.save", "settings.save",
                "progress.save.backup", "settings.save.backup"}
    saves = [
        f for f in Path(save_dir).glob("**/*.save")
        if f.name not in excluded
    ]
    if not saves:
        print(f"[Parser] No active run .save files found in {save_dir}")
        return None
    latest = max(saves, key=lambda f: f.stat().st_mtime)
    print(f"[Parser] Parsing: {latest}")
    return parse_save_file(str(latest))
