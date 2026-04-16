"""
path_advisor.py
Scores available map path choices based on current run state.

Map node types confirmed from STS2 .run data:
  monster, elite, event (unknown), rest, shop, boss, ancient (Neow/boss event)

Scoring philosophy:
  - HP is the most critical constraint — a dead player wins nothing
  - Relics from elites are high value but not worth dying for
  - Rest sites become mandatory below ~40% HP
  - Shops are only worth routing to if you have gold to spend
  - Events (unknown) are medium risk/reward — better than monsters when HP is low
"""

from dataclasses import dataclass, field
from typing import List, Optional

from data.enemies import BOSSES_BY_AREA, BOSS_FLOOR, boss_tips, get_act_bosses, BOSSES


# ---------------------------------------------------------------------------
# Node type display names and base desirability
# ---------------------------------------------------------------------------
NODE_LABELS = {
    "monster":  "Monster",
    "elite":    "Elite",
    "event":    "? Unknown",
    "rest":     "Rest Site",
    "shop":     "Shop",
    "boss":     "Boss",
    "ancient":  "Ancient / Event",
    "treasure": "Treasure",
}

# Base score before modifiers — how inherently useful each node type is
NODE_BASE_SCORE = {
    "rest":     0.70,
    "shop":     0.55,
    "event":    0.50,
    "treasure": 0.60,
    "monster":  0.45,
    "elite":    0.65,   # high base — good relic drops — modifiers pull this down when unsafe
    "ancient":  0.60,
    "boss":     0.50,   # unavoidable, scored for awareness only
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class NodeScore:
    node_type:  str
    score:      float
    reasons:    List[str] = field(default_factory=list)
    warnings:   List[str] = field(default_factory=list)

    @property
    def pct(self) -> int:
        return round(self.score * 100)

    @property
    def stars(self) -> str:
        if self.score >= 0.70: return "★★★"
        if self.score >= 0.50: return "★★"
        if self.score >= 0.30: return "★"
        return "✗"

    @property
    def tone(self) -> str:
        if self.score >= 0.60: return "good"
        if self.score >= 0.35: return "neutral"
        return "warn"

    @property
    def label(self) -> str:
        return NODE_LABELS.get(self.node_type, self.node_type)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _hp_ratio(hp: int, max_hp: int) -> float:
    if max_hp <= 0:
        return 1.0
    return min(hp / max_hp, 1.0)


def _score_rest(hp: int, max_hp: int, floor: int, floors_to_boss: int) -> NodeScore:
    ratio = _hp_ratio(hp, max_hp)
    score = NODE_BASE_SCORE["rest"]
    reasons = []
    warnings = []

    if ratio <= 0.30:
        score += 0.30
        warnings.append(f"HP critical ({hp}/{max_hp}) — rest is mandatory")
    elif ratio <= 0.50:
        score += 0.20
        reasons.append(f"Low HP ({hp}/{max_hp}) — rest recommended")
    elif ratio <= 0.70:
        score += 0.05
        reasons.append(f"Moderate HP — rest is safe choice")
    else:
        score -= 0.10
        reasons.append("HP healthy — rest less urgent")

    if floors_to_boss <= 2:
        score += 0.15
        reasons.append(f"Only {floors_to_boss} floors to boss — heal now")

    return NodeScore("rest", min(score, 1.0), reasons, warnings)


def _score_elite(
    hp: int, max_hp: int, relic_count: int,
    deck_size: int, ascension: int, floor: int
) -> NodeScore:
    ratio = _hp_ratio(hp, max_hp)
    score = NODE_BASE_SCORE["elite"]
    reasons = []
    warnings = []

    # HP penalty
    if ratio <= 0.30:
        score -= 0.50
        warnings.append(f"HP critical ({hp}/{max_hp}) — elite will likely kill you")
    elif ratio <= 0.50:
        score -= 0.25
        warnings.append(f"Low HP ({hp}/{max_hp}) — elite is very risky")
    elif ratio <= 0.65:
        score -= 0.10
        reasons.append("Moderate HP — elite is risky but survivable")
    else:
        reasons.append(f"HP healthy ({hp}/{max_hp}) — good time for elite")

    # Relic incentive — fewer relics = more reason to fight elite
    if relic_count <= 2:
        score += 0.15
        reasons.append(f"Only {relic_count} relics — elite relic drop is high value")
    elif relic_count <= 4:
        score += 0.05

    # Deck not established yet — elite is harder to beat
    if deck_size < 8:
        score -= 0.15
        warnings.append("Deck too small — elite combat will be inconsistent")

    # Ascension penalties
    if ascension >= 10:
        score -= 0.10
        warnings.append("A10: Elites are significantly harder")
    elif ascension >= 3:
        score -= 0.05

    return NodeScore("elite", min(max(score, 0.0), 1.0), reasons, warnings)


def _score_shop(hp: int, max_hp: int, gold: int, deck_size: int) -> NodeScore:
    ratio = _hp_ratio(hp, max_hp)
    score = NODE_BASE_SCORE["shop"]
    reasons = []
    warnings = []

    # Gold gating — shop is only useful if you can buy something
    if gold >= 150:
        score += 0.20
        reasons.append(f"High gold ({gold}g) — can afford relic or removal")
    elif gold >= 75:
        score += 0.05
        reasons.append(f"Decent gold ({gold}g) — card purchase likely")
    else:
        score -= 0.25
        warnings.append(f"Low gold ({gold}g) — not much to buy")

    # Card removal is always valuable — bigger deck = more urgent
    if deck_size >= 15:
        score += 0.10
        reasons.append(f"Large deck ({deck_size} cards) — removal worth the detour")

    # If HP is low, shop potions/removal are extra valuable
    if ratio <= 0.40:
        score += 0.10
        reasons.append("Low HP — shop potion could be lifesaving")

    return NodeScore("shop", min(max(score, 0.0), 1.0), reasons, warnings)


def _score_event(hp: int, max_hp: int, floor: int) -> NodeScore:
    ratio = _hp_ratio(hp, max_hp)
    score = NODE_BASE_SCORE["event"]
    reasons = []
    warnings = []

    # Events generally safer than monsters when low HP
    if ratio <= 0.40:
        score += 0.15
        reasons.append("Low HP — event safer than combat")
    elif ratio >= 0.80:
        score -= 0.05

    reasons.append("Events have variable outcomes — high variance")
    return NodeScore("event", min(max(score, 0.0), 1.0), reasons, warnings)


def _score_monster(hp: int, max_hp: int, floor: int) -> NodeScore:
    ratio = _hp_ratio(hp, max_hp)
    score = NODE_BASE_SCORE["monster"]
    reasons = []
    warnings = []

    if ratio <= 0.30:
        score -= 0.20
        warnings.append(f"HP critical — even regular combat is dangerous")
    elif ratio >= 0.70:
        score += 0.10
        reasons.append("HP healthy — safe to fight")

    reasons.append("Guaranteed card reward")
    return NodeScore("monster", min(max(score, 0.0), 1.0), reasons, warnings)


def _score_boss(act: int, ascension: int, floors_to_boss: int) -> NodeScore:
    """Build a boss node score with HP and gimmick info for all possible act bosses."""
    boss_ids = get_act_bosses(act)
    reasons = [f"Floor {BOSS_FLOOR.get(act, '?')} — unavoidable, prepare now"]
    warnings = []

    if floors_to_boss <= 3:
        warnings.append(f"{floors_to_boss} floor(s) to boss — finalise deck and HP now")

    for bid in boss_ids:
        entry = BOSSES.get(bid, {})
        if not entry or entry.get("hp") is None:
            continue
        hp_val = entry["hp_a8"] if ascension >= 8 and entry.get("hp_a8") else entry["hp"]
        name = entry["name"]
        reasons.append(f"[{name}] HP {hp_val}")
        for g in entry.get("gimmicks", [])[:2]:
            warnings.append(f"[{name}] {g}")
        for c in entry.get("counters", [])[:1]:
            reasons.append(f"[{name}] ✓ {c}")

    if ascension >= 9:
        warnings.append("A9+: Boss deals ~10% more damage")
    if ascension >= 10:
        warnings.append("A10: Two Act 3 bosses back-to-back — no rest between them")

    return NodeScore("boss", 0.50, reasons, warnings)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def score_path_choices(
    available_nodes: List[str],
    hp:              int,
    max_hp:          int,
    gold:            int,
    floor:           int,
    act:             int,
    relic_count:     int,
    deck_size:       int,
    ascension:       int = 0,
    floors_to_boss:  int = 5,
) -> List[NodeScore]:
    """
    Score each available map node type and return ranked list.

    available_nodes: list of node type strings e.g. ["monster", "elite", "rest"]
    """
    scores = []

    for node_type in available_nodes:
        if node_type == "rest":
            scores.append(_score_rest(hp, max_hp, floor, floors_to_boss))
        elif node_type == "elite":
            scores.append(_score_elite(hp, max_hp, relic_count, deck_size, ascension, floor))
        elif node_type == "shop":
            scores.append(_score_shop(hp, max_hp, gold, deck_size))
        elif node_type in ("event", "unknown"):
            scores.append(_score_event(hp, max_hp, floor))
        elif node_type == "monster":
            scores.append(_score_monster(hp, max_hp, floor))
        elif node_type == "treasure":
            scores.append(NodeScore("treasure", 0.60,
                ["Free relic — always take if available"]))
        elif node_type == "boss":
            scores.append(_score_boss(act, ascension, floors_to_boss))
        else:
            scores.append(NodeScore(node_type, 0.40, ["Unknown node type"]))

    return sorted(scores, key=lambda n: n.score, reverse=True)


def path_tips(node_scores: List[NodeScore]) -> List[dict]:
    """Format path scores for the overlay UI."""
    tips = [{"text": "── Path Recommendation ──", "tone": "neutral"}]
    for ns in node_scores:
        tips.append({
            "text": f"{ns.label:<12} {ns.pct}%  {ns.stars}",
            "tone": ns.tone,
        })
        for r in ns.reasons[:1]:
            tips.append({"text": f"    {r}", "tone": "neutral"})
        for w in ns.warnings[:1]:
            tips.append({"text": f"    ! {w}", "tone": "warn"})
    return tips
