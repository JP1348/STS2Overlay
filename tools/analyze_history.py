"""
tools/analyze_history.py

Mine all STS2 .run history files and do two things:
  1. Print a summary of your run patterns (characters, win rate, top cards)
  2. Optionally submit all runs to the community API to seed the database

Usage:
    # Just analyze locally (no login needed):
    python tools/analyze_history.py --history-dir "C:\\...\\saves\\history"

    # Analyze + submit to community API:
    python tools/analyze_history.py --history-dir "..." --submit

    # Auto-detect save dir:
    python tools/analyze_history.py --submit
"""

import sys
import os
import json
import argparse
import threading
from pathlib import Path
from collections import Counter, defaultdict

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.parser import parse_run_history
from core.find_save import find_save_dir
from core.api_client import ApiClient


def find_history_dir(saves_dir: str = None) -> Path | None:
    if saves_dir:
        p = Path(saves_dir)
        # If they passed the saves dir, history is a subdir
        hist = p / "history"
        if hist.exists():
            return hist
        if p.exists():
            return p  # maybe they passed the history dir directly
    # Auto-detect
    detected = find_save_dir()
    if detected:
        hist = Path(detected) / "history"
        return hist if hist.exists() else Path(detected)
    return None


def load_all_runs(history_dir: Path) -> list[dict]:
    """Load all .run files in the history directory. Returns list of raw dicts."""
    run_files = list(history_dir.glob("**/*.run"))
    if not run_files:
        print(f"[Analyzer] No .run files found in {history_dir}")
        return []
    print(f"[Analyzer] Found {len(run_files)} run files")
    runs = []
    for f in run_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["_filepath"] = str(f)
            runs.append(data)
        except Exception as e:
            print(f"[Analyzer] Skip {f.name}: {e}")
    return runs


def summarize(runs: list[dict]):
    """Print a human-readable summary of all runs."""
    if not runs:
        print("No runs to summarize.")
        return

    total = len(runs)
    wins  = sum(1 for r in runs if r.get("victory", False))
    by_char: Counter = Counter()
    win_by_char: Counter = Counter()
    floors_reached: list[int] = []
    card_pick_counts: Counter = Counter()   # how often each card was picked across all runs
    card_win_counts: Counter  = Counter()   # how often a picked card correlated with a win
    skip_count = 0
    relic_picks: Counter = Counter()

    for run in runs:
        # Character
        char = run.get("character", "UNKNOWN")
        by_char[char] += 1
        won = run.get("victory", False)
        if won:
            win_by_char[char] += 1

        # Floor reached
        history = run.get("map_point_history", [])
        total_floors = sum(len(act) for act in history)
        floors_reached.append(total_floors)

        # Card picks — from card_choices field if present, else reconstruct from history
        card_choices = run.get("card_choices", [])
        for choice in card_choices:
            offered = choice.get("offered", [])
            picked  = choice.get("picked")
            if picked:
                card_pick_counts[picked] += 1
                if won:
                    card_win_counts[picked] += 1
            else:
                skip_count += 1

        # Also scan map_point_history for cards_gained
        for act_floors in history:
            for mp in act_floors:
                for ps in mp.get("player_stats", []):
                    for rc in ps.get("relic_choices", []):
                        if rc.get("was_picked"):
                            rid = rc.get("choice", "")
                            if rid:
                                relic_picks[rid] += 1

    avg_floor = sum(floors_reached) / len(floors_reached) if floors_reached else 0
    win_rate  = wins / total * 100 if total else 0

    print("\n" + "="*60)
    print(f"  STS2 Run History Analysis — {total} runs")
    print("="*60)
    print(f"  Overall win rate:  {win_rate:.1f}%  ({wins}/{total})")
    print(f"  Average floor:     {avg_floor:.1f}")
    print()
    print("  By character:")
    for char, count in by_char.most_common():
        char_wins = win_by_char.get(char, 0)
        char_wr = char_wins / count * 100 if count else 0
        print(f"    {char:<30} {count:>4} runs  {char_wr:.0f}% win")
    print()

    # Most picked cards
    print("  Top 15 most-picked cards:")
    for card_id, count in card_pick_counts.most_common(15):
        picked_wins = card_win_counts.get(card_id, 0)
        pick_wr = picked_wins / count * 100 if count else 0
        print(f"    {card_id:<40} picked {count:>3}x  win {pick_wr:.0f}%")
    print()

    # Best win-correlated cards (min 3 picks)
    print("  Best win-correlated cards (min 3 picks):")
    by_winrate = [
        (cid, cnt, card_win_counts.get(cid, 0) / cnt * 100)
        for cid, cnt in card_pick_counts.items()
        if cnt >= 3
    ]
    by_winrate.sort(key=lambda x: x[2], reverse=True)
    for card_id, count, wr in by_winrate[:10]:
        print(f"    {card_id:<40} {wr:.0f}% win  (n={count})")
    print()

    print(f"  Times skipped card reward: {skip_count}")
    print()
    print("  Top relics picked:")
    for relic_id, count in relic_picks.most_common(10):
        print(f"    {relic_id:<40} {count:>3}x")
    print("="*60 + "\n")


def build_submission_payload(run: dict) -> dict | None:
    """
    Convert a raw .run dict into the API submission format.
    Strips anything personally identifiable (no username, no timestamp).
    """
    try:
        history = run.get("map_point_history", [])
        total_floors = sum(len(act) for act in history)
        acts_count = len(history)

        card_picks = []
        for choice in run.get("card_choices", []):
            offered = choice.get("offered", [])
            picked  = choice.get("picked")
            floor   = choice.get("floor", 0)
            if offered:
                card_picks.append({
                    "floor":   floor,
                    "offered": offered if isinstance(offered, list) else [offered],
                    "chosen":  picked,
                })

        return {
            "seed":          run.get("seed"),
            "character":     run.get("character"),
            "ascension":     run.get("ascension", 0),
            "act_reached":   acts_count,
            "floor_reached": total_floors,
            "won":           bool(run.get("victory", False)),
            "card_picks":    card_picks,
            "run_json":      None,  # don't send raw JSON for history submissions
        }
    except Exception as e:
        print(f"[Analyzer] Failed to build payload: {e}")
        return None


def submit_all(runs: list[dict], api: ApiClient):
    """Submit all runs to the community API. Shows progress."""
    if not api.is_logged_in:
        print("[Analyzer] Not logged in — cannot submit. Run with login first.")
        return

    submitted = 0
    failed = 0
    for i, run in enumerate(runs, 1):
        payload = build_submission_payload(run)
        if not payload:
            failed += 1
            continue

        # Submit synchronously here (analysis is a one-time batch job, not overlay)
        ok, result = api._post("/runs/submit", payload, auth=True)
        if ok:
            submitted += 1
        else:
            failed += 1

        if i % 20 == 0:
            print(f"  Progress: {i}/{len(runs)} ({submitted} OK, {failed} failed)")

    print(f"\n[Analyzer] Submitted {submitted}/{len(runs)} runs. "
          f"{failed} failed.\n")


def main():
    ap = argparse.ArgumentParser(description="STS2 Run History Analyzer")
    ap.add_argument("--history-dir", default="",
                    help="Path to saves/history folder (auto-detected if omitted)")
    ap.add_argument("--submit", action="store_true",
                    help="Submit all runs to the community API")
    args = ap.parse_args()

    # Find history
    hist_dir = find_history_dir(args.history_dir or None)
    if not hist_dir or not hist_dir.exists():
        print(f"[Analyzer] Could not find history directory. "
              f"Pass --history-dir path/to/saves/history")
        sys.exit(1)

    print(f"[Analyzer] Reading from: {hist_dir}")
    runs = load_all_runs(hist_dir)
    if not runs:
        sys.exit(0)

    # Always print local summary
    summarize(runs)

    # Submit if requested
    if args.submit:
        api = ApiClient()
        if not api.is_logged_in:
            print("[Analyzer] No saved login token found.")
            username = input("Username: ").strip()
            password = input("Password: ").strip()
            ok, msg = api.login(username, password)
            if not ok:
                print(f"[Analyzer] Login failed: {msg}")
                sys.exit(1)
            print(f"[Analyzer] {msg}")

        print(f"[Analyzer] Submitting {len(runs)} runs to community API...")
        submit_all(runs, api)


if __name__ == "__main__":
    main()
