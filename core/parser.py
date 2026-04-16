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
    # Fields confirmed from real STS2 save data
    is_on_reward_screen: bool = False   # pre_finished_room.is_pre_finished
    last_card_choices: List[dict] = field(default_factory=list)  # most recent card_choices
    next_nodes: List[dict] = field(default_factory=list)  # available next map nodes
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
    Confirmed field layout from real current_run.save (schema_version 14):
      - Top-level: ascension, current_act_index, rng.seed, map_point_history
      - Player data under players[0]: character_id, current_hp, max_hp, gold,
        deck (list of {id, ...}), relics (list of {id, ...})
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

    # --- Top-level fields ---
    state.ascension = data.get("ascension", 0)
    state.act       = data.get("current_act_index", 0) + 1
    state.seed      = str(data.get("rng", {}).get("seed", "UNKNOWN"))

    # Floor = total map points visited across all acts
    state.floor = sum(len(act) for act in data.get("map_point_history", []))

    # --- Player data (take first player) ---
    player = (data.get("players") or [{}])[0]

    state.character = player.get("character_id")
    state.hp        = player.get("current_hp", 0)
    state.max_hp    = player.get("max_hp", 0)
    state.gold      = player.get("gold", 0)

    # Relics: list of {"id": "RELIC.X", ...}
    state.relics = [r["id"] for r in player.get("relics", []) if "id" in r]

    # Deck: list of {"id": "CARD.X", ...}
    state.deck = [c["id"] for c in player.get("deck", []) if "id" in c]

    # --- Reward screen state ---
    pre = data.get("pre_finished_room", {})
    state.is_on_reward_screen = bool(pre.get("is_pre_finished", False))

    # --- Most recent card choices from history ---
    # Walk map_point_history in reverse to find the last floor that has card_choices
    state.last_card_choices = []
    for act_floors in reversed(data.get("map_point_history", [])):
        for map_point in reversed(act_floors):
            for ps in map_point.get("player_stats", []):
                choices = ps.get("card_choices", [])
                if choices:
                    state.last_card_choices = choices
                    break
            if state.last_card_choices:
                break
        if state.last_card_choices:
            break

    # --- Next available map nodes ---
    # Find current position (last visited coord) and look up its children
    visited = data.get("visited_map_coords", [])
    if visited:
        current = visited[-1]
        act_data = (data.get("acts") or [{}])[state.act - 1]
        saved_map = act_data.get("saved_map", {})
        # Build coord → node lookup
        coord_key = lambda c: (c.get("col"), c.get("row"))
        nodes_by_coord = {coord_key(p["coord"]): p for p in saved_map.get("points", [])}
        # Add boss node
        boss = saved_map.get("boss")
        if boss:
            nodes_by_coord[coord_key(boss["coord"])] = boss
        current_node = nodes_by_coord.get(coord_key(current))
        if current_node:
            state.next_nodes = [
                nodes_by_coord[coord_key(child)]
                for child in current_node.get("children", [])
                if coord_key(child) in nodes_by_coord
            ]

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
