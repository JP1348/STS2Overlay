"""
advisor.py
Core scoring engine for the STS2 Advisor overlay.

Given a RunState (current deck, relics, HP, floor) and a list of card/relic
options presented to the player, scores each option and produces ranked advice
with percentage scores and human-readable reasoning.

Scoring formula (weights sum to 1.0):
  synergy_with_deck    0.35  — how well this card combos with existing deck
  archetype_fit        0.25  — does this push the detected build forward
  relic_amplification  0.20  — does a held relic amplify this card
  curve_fit            0.10  — energy cost vs. current deck average
  redundancy_penalty   0.05  — penalize 3rd+ copy of same card
  future_awareness     0.05  — placeholder for seed-based look-ahead
"""

from dataclasses import dataclass, field
from typing import List, Optional
from collections import Counter

from data.cards  import CARDS, SYNERGY_PAIRS, get_tags, get_archetypes
from data.relics import RELICS, get_relic


# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------
W_SYNERGY    = 0.35
W_ARCHETYPE  = 0.25
W_RELIC      = 0.20
W_CURVE      = 0.10
W_REDUNDANCY = 0.05  # applied as a penalty
W_FUTURE     = 0.05


# ---------------------------------------------------------------------------
# Ascension modifiers
#
# Each threshold entry applies when ascension >= the key value.
# Modifiers are *additive* score adjustments applied to specific tag groups.
# Negative values penalize; positive values boost.
# ---------------------------------------------------------------------------

ASCENSION_THRESHOLDS = [
    # (min_ascension, modifier_dict)
    # modifier_dict keys: card tag or archetype → score delta
    # STS2 ascension caps at A10.
    (0,  {}),   # baseline — no modifiers

    # A3: Elites buffed — defensive consistency starts to matter
    (3,  {
        "block_gen":    +0.05,
        "sustain":      +0.05,
    }),

    # A6: Harder bosses — consistency over burst
    (6,  {
        "block_gen":    +0.05,
        "draw":         +0.05,
        "energy_burst": -0.05,
    }),

    # A10: Max difficulty in STS2 — defence and scaling are paramount
    (10, {
        "block_gen":     +0.10,
        "block_scaling": +0.08,
        "sustain":       +0.08,
        "draw":          +0.05,
        "aoe":           +0.05,
        "energy_burst":  -0.08,
    }),
]


def get_ascension_modifier(card_id: str, ascension: int) -> tuple[float, list]:
    """
    Calculate a score delta for a card based on ascension level.
    Returns (delta, list of reason strings).
    """
    tags = set(get_tags(card_id)) | set(get_archetypes(card_id))
    total_delta = 0.0
    reasons = []

    for threshold, modifiers in ASCENSION_THRESHOLDS:
        if ascension >= threshold:
            for tag, delta in modifiers.items():
                if tag in tags:
                    total_delta += delta
                    if abs(delta) >= 0.06:  # only surface meaningful adjustments
                        direction = "boosted" if delta > 0 else "reduced"
                        reasons.append(f"A{threshold}+ ({tag} value {direction})")

    # Cap the total delta to avoid runaway boosts
    total_delta = max(min(total_delta, 0.25), -0.25)
    return total_delta, list(dict.fromkeys(reasons))[:2]  # deduplicate, cap at 2


def ascension_context_tips(ascension: int) -> List[dict]:
    """
    Return overlay tips describing what this ascension level means strategically.
    Shown when no card reward is active. STS2 caps at A10.
    """
    tips = []
    if ascension == 0:
        return tips
    if ascension >= 10:
        tips.append({"text": "A10 (max): Defence is priority. Block generation and scaling over burst.", "tone": "warn"})
    elif ascension >= 6:
        tips.append({"text": f"A{ascension}: Harder bosses — consistency beats burst strategies.", "tone": "warn"})
    elif ascension >= 3:
        tips.append({"text": f"A{ascension}: Elites are tougher — defensive cards gain value.", "tone": "neutral"})
    else:
        tips.append({"text": f"A{ascension}: Low ascension — flexible deckbuilding, take risks.", "tone": "neutral"})
    return tips


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CardScore:
    card_id:     str
    score:       float          # 0.0 – 1.0
    reasons:     List[str]      = field(default_factory=list)
    warnings:    List[str]      = field(default_factory=list)
    archetype:   Optional[str]  = None

    @property
    def pct(self) -> int:
        return round(self.score * 100)

    @property
    def stars(self) -> str:
        if self.score >= 0.80: return "★★★"
        if self.score >= 0.55: return "★★"
        if self.score >= 0.35: return "★"
        return "✗"

    @property
    def tone(self) -> str:
        if self.score >= 0.55: return "good"
        if self.score >= 0.35: return "neutral"
        return "warn"


@dataclass
class SkipScore:
    score:    float
    reasons:  List[str] = field(default_factory=list)

    @property
    def pct(self) -> int:
        return round(self.score * 100)


@dataclass
class Advice:
    card_scores: List[CardScore]
    skip_score:  SkipScore
    detected_archetype: Optional[str]

    def best(self) -> CardScore:
        return max(self.card_scores, key=lambda c: c.score)

    def ranked(self) -> List[CardScore]:
        return sorted(self.card_scores, key=lambda c: c.score, reverse=True)

    def as_tips(self) -> List[dict]:
        """Format for the overlay UI tip list."""
        tips = []
        for cs in self.ranked():
            name = CARDS.get(cs.card_id, {}).get("name", cs.card_id)
            tips.append({
                "text": f"{name}  {cs.pct}%  {cs.stars}",
                "tone": cs.tone,
            })
            for r in cs.reasons[:2]:   # show top 2 reasons
                tips.append({"text": f"    + {r}", "tone": "neutral"})
            for w in cs.warnings[:1]:
                tips.append({"text": f"    ! {w}", "tone": "warn"})

        skip = self.skip_score
        tips.append({
            "text": f"SKIP  {skip.pct}%",
            "tone": "good" if skip.score >= 0.45 else "neutral",
        })
        for r in skip.reasons[:1]:
            tips.append({"text": f"    {r}", "tone": "neutral"})

        if self.detected_archetype:
            tips.append({
                "text": f"Detected build: {self.detected_archetype}",
                "tone": "neutral",
            })
        return tips


# ---------------------------------------------------------------------------
# Archetype detection
# ---------------------------------------------------------------------------

def detect_archetype(deck: List[str], relics: List[str]) -> Optional[str]:
    """
    Infer the primary archetype of the current deck by counting
    archetype tags across all cards and relics.
    Returns the leading archetype, or None if no clear direction.
    """
    counts: Counter = Counter()

    for card_id in deck:
        for arch in get_archetypes(card_id):
            counts[arch] += 1

    for relic_id in relics:
        relic = get_relic(relic_id)
        for tag in relic.get("amplifies", []):
            counts[tag] += 0.5  # relics count less than cards

    if not counts:
        return None

    top, top_count = counts.most_common(1)[0]
    # Only declare an archetype if it has meaningful representation
    return top if top_count >= 2 else None


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _score_synergy(candidate_id: str, deck: List[str]) -> tuple[float, List[str]]:
    """
    Score how well the candidate card synergizes with the existing deck.
    Returns (score 0-1, list of reason strings).
    """
    candidate_tags = set(get_tags(candidate_id))
    if not candidate_tags:
        return 0.1, []

    hits = 0
    reasons = []

    for deck_card_id in deck:
        deck_tags = set(get_tags(deck_card_id))
        for ctag in candidate_tags:
            payoffs = set(SYNERGY_PAIRS.get(ctag, []))
            overlap = payoffs & deck_tags
            if overlap:
                hits += 1
                deck_name = CARDS.get(deck_card_id, {}).get("name", deck_card_id)
                reasons.append(f"Synergy with {deck_name} ({ctag})")
                break  # one hit per deck card is enough

    # Also check if the deck has tags this card benefits from
    for deck_card_id in deck:
        deck_tags = set(get_tags(deck_card_id))
        for dtag in deck_tags:
            payoffs = set(SYNERGY_PAIRS.get(dtag, []))
            if payoffs & candidate_tags:
                hits += 1
                break

    # Normalize: 3+ synergy hits = full score
    score = min(hits / 3.0, 1.0)
    return score, list(dict.fromkeys(reasons))[:3]  # deduplicate, cap at 3


def _score_archetype_fit(candidate_id: str, archetype: Optional[str]) -> tuple[float, List[str]]:
    """Score how well the candidate fits the detected archetype."""
    if not archetype:
        return 0.5, ["No clear archetype yet — any direction viable"]
    archetypes = get_archetypes(candidate_id)
    if archetype in archetypes:
        return 1.0, [f"Directly supports {archetype} build"]
    # Partial credit if the card is generally useful (draw, energy, etc.)
    if any(a in archetypes for a in ["draw", "energy"]):
        return 0.4, ["Utility card — not archetype-specific but generally useful"]
    return 0.1, [f"Off-archetype — current build is {archetype}"]


def _score_relic_amplification(candidate_id: str, relics: List[str]) -> tuple[float, List[str]]:
    """Score based on whether held relics amplify this card."""
    candidate_tags = set(get_tags(candidate_id))
    candidate_archetypes = set(get_archetypes(candidate_id))
    combined = candidate_tags | candidate_archetypes

    hits = 0
    reasons = []
    for relic_id in relics:
        relic = get_relic(relic_id)
        amplifies = set(relic.get("amplifies", []))
        if amplifies & combined:
            hits += 1
            reasons.append(f"{relic.get('name', relic_id)} amplifies this card")

    score = min(hits / 2.0, 1.0)
    return score, reasons


def _score_curve_fit(candidate_id: str, deck: List[str]) -> tuple[float, List[str]]:
    """
    Penalize cards that are too expensive relative to current deck average.
    Cards costing <= deck average cost score higher.
    """
    card_data = CARDS.get(candidate_id, {})
    cost = card_data.get("cost", 1)

    if cost < 0:  # X-cost cards — neutral
        return 0.5, ["X-cost card — value scales with energy"]

    deck_costs = [
        CARDS.get(c, {}).get("cost", 1)
        for c in deck
        if CARDS.get(c, {}).get("cost", 1) >= 0
    ]
    avg_cost = sum(deck_costs) / len(deck_costs) if deck_costs else 1.5

    if cost <= avg_cost:
        return 0.8, [f"Good cost efficiency ({cost} energy, deck avg {avg_cost:.1f})"]
    if cost <= avg_cost + 1:
        return 0.5, []
    return 0.2, [f"Expensive at {cost} energy (deck avg {avg_cost:.1f})"]


def _score_redundancy(candidate_id: str, deck: List[str]) -> tuple[float, List[str]]:
    """Penalize if the deck already has 2+ copies of this card."""
    count = deck.count(candidate_id)
    if count == 0:
        return 0.0, []   # no penalty
    if count == 1:
        return 0.3, [f"Already have 1 copy — 2nd copy is often fine"]
    return 1.0, [f"Already have {count} copies — diminishing returns"]


# ---------------------------------------------------------------------------
# Skip score
# ---------------------------------------------------------------------------

def _score_skip(deck: List[str], floor: int, best_card_score: float) -> tuple[float, List[str]]:
    """
    Heuristic skip score.
    Skip is attractive when: deck is bloated, best offer is weak, or early floors.
    """
    reasons = []
    score = 0.0

    # Large deck — skipping keeps deck lean
    if len(deck) >= 20:
        score += 0.4
        reasons.append(f"Deck is {len(deck)} cards — trimming is often better than adding")
    elif len(deck) >= 15:
        score += 0.2

    # Best card offer is weak
    if best_card_score < 0.35:
        score += 0.4
        reasons.append("No strong options in this reward — skip is reasonable")
    elif best_card_score < 0.55:
        score += 0.15

    # Early floors — deck discipline matters less
    if floor <= 5:
        score -= 0.1  # early floors: take cards more liberally

    return min(max(score, 0.0), 1.0), reasons


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def score_card_reward(
    offered_cards: List[str],
    deck:          List[str],
    relics:        List[str],
    hp:            int,
    max_hp:        int,
    floor:         int,
    ascension:     int = 0,
    future_cards:  Optional[List[str]] = None,   # from seed sim (not yet implemented)
) -> Advice:
    """
    Score each offered card against the current run state.
    Returns an Advice object with ranked CardScores and a SkipScore.
    """
    archetype = detect_archetype(deck, relics)
    card_scores = []

    for card_id in offered_cards:
        reasons  = []
        warnings = []

        syn_score,   syn_reasons   = _score_synergy(card_id, deck)
        arch_score,  arch_reasons  = _score_archetype_fit(card_id, archetype)
        relic_score, relic_reasons = _score_relic_amplification(card_id, relics)
        curve_score, curve_reasons = _score_curve_fit(card_id, deck)
        redund_pen,  redund_warn   = _score_redundancy(card_id, deck)
        asc_delta,   asc_reasons   = get_ascension_modifier(card_id, ascension)

        # Future awareness placeholder — boost if known upcoming floors have synergy
        future_score = 0.5  # neutral until seed sim is implemented

        composite = (
            syn_score   * W_SYNERGY   +
            arch_score  * W_ARCHETYPE +
            relic_score * W_RELIC     +
            curve_score * W_CURVE     +
            future_score * W_FUTURE   -
            redund_pen  * W_REDUNDANCY +
            asc_delta                  # ascension modifier applied directly
        )
        composite = min(max(composite, 0.0), 1.0)

        reasons  += syn_reasons + arch_reasons + relic_reasons + curve_reasons + asc_reasons
        warnings += redund_warn

        card_scores.append(CardScore(
            card_id   = card_id,
            score     = composite,
            reasons   = reasons,
            warnings  = warnings,
            archetype = archetype,
        ))

    best_score = max(cs.score for cs in card_scores) if card_scores else 0.0
    skip_val, skip_reasons = _score_skip(deck, floor, best_score)

    return Advice(
        card_scores         = card_scores,
        skip_score          = SkipScore(score=skip_val, reasons=skip_reasons),
        detected_archetype  = archetype,
    )


def score_relic_choice(
    offered_relics: List[str],
    deck:           List[str],
    relics:         List[str],
    floor:          int,
) -> List[dict]:
    """
    Score relic options against current deck archetype and tags.
    Returns a sorted list of dicts with relic_id, score, reason.
    """
    archetype = detect_archetype(deck, relics)
    deck_tags = set()
    for card_id in deck:
        deck_tags.update(get_tags(card_id))

    results = []
    for relic_id in offered_relics:
        relic = get_relic(relic_id)
        amplifies = set(relic.get("amplifies", []))
        overlap = amplifies & deck_tags
        score = min(len(overlap) / 2.0, 1.0) if overlap else 0.2
        reason = relic.get("note", "")
        if overlap:
            reason = f"Amplifies your {', '.join(overlap)} cards. {reason}"
        results.append({
            "relic_id": relic_id,
            "name":     relic.get("name", relic_id),
            "score":    score,
            "pct":      round(score * 100),
            "reason":   reason,
            "tone":     "good" if score >= 0.55 else "neutral" if score >= 0.35 else "warn",
        })

    return sorted(results, key=lambda r: r["score"], reverse=True)
