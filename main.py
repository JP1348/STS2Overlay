"""
main.py
STS2 Advisor Overlay — entry point.

Usage:
    python main.py --save-dir "/path/to/sts2/saves"

On Windows (STS2 via Steam), saves are typically at:
    C:\\Users\\<you>\\AppData\\Roaming\\SlayTheSpire2\\steam\\<steamid>\\profile1\\saves

On Linux (Steam/Proton), find your save dir by running:
    find ~/.steam -name "*.save" 2>/dev/null
"""

import sys
import os
import argparse
import subprocess
import threading

from core.watcher      import SaveFileWatcher
from core.parser       import parse_save_file
from core.advisor      import score_card_reward, ascension_context_tips, detect_archetype
from core.find_save    import find_save_dir
from core.path_advisor import score_path_choices, path_tips
from core.api_client   import ApiClient
from ui.overlay        import OverlayWindow
from ui.login_dialog   import LoginDialog

# Shared API client — one instance for the whole process
_api = ApiClient()

# Steam App ID for Slay the Spire 2
STS2_APP_ID = "1141290"


def launch_game() -> None:
    """Launch STS2 via Steam if it is not already running."""
    try:
        if sys.platform == "win32":
            os.startfile(f"steam://rungameid/{STS2_APP_ID}")
        else:
            # Linux / macOS — try the steam CLI first, fall back to xdg-open
            steam_cmd = ["steam", f"steam://rungameid/{STS2_APP_ID}"]
            try:
                subprocess.Popen(steam_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except FileNotFoundError:
                subprocess.Popen(["xdg-open", f"steam://rungameid/{STS2_APP_ID}"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[Main] Could not launch STS2: {e}")

# Track the last seen run floor so we can detect a run ending (floor resets to 0/1)
_last_floor: int = 0
_run_card_picks: list[dict] = []   # accumulated card picks for the current run
_last_run_state = None             # the most recent RunState, used for submission


def _maybe_submit_completed_run(prev_floor: int, current_floor: int):
    """If the floor just reset (new run started), submit the previous run."""
    global _run_card_picks, _last_run_state
    if prev_floor >= 3 and current_floor <= 1 and _last_run_state:
        rs = _last_run_state
        payload = {
            "seed":          rs.seed,
            "character":     rs.character,
            "ascension":     rs.ascension,
            "act_reached":   rs.act,
            "floor_reached": prev_floor,
            "won":           False,   # run ended — assume loss unless victory screen detected
            "card_picks":    _run_card_picks,
            "run_json":      None,
        }
        _api.submit_run_async(payload)
        _run_card_picks = []


def on_save_changed(path: str, overlay: OverlayWindow):
    """Called whenever the STS2 autosave file changes."""
    global _last_floor, _run_card_picks, _last_run_state

    run_state = parse_save_file(path)

    if not run_state.deck:
        overlay.show_error("Save file loaded but deck is empty.\nField names may need updating for STS2.")
        return

    # Detect run boundary and auto-submit previous run
    _maybe_submit_completed_run(_last_floor, run_state.floor)
    _last_floor = run_state.floor
    _last_run_state = run_state

    overlay.update_run_info(run_state)

    # -------------------------------------------------------------------
    # Advisor scoring
    # In a real implementation, the save file would include the card
    # reward options currently on screen. Until we confirm STS2 save
    # format, we score the full deck for archetype detection and show
    # a readiness summary.
    # -------------------------------------------------------------------
    offered = run_state.raw.get("card_choice", {}).get("cards", [])  # VERIFY field name

    if offered:
        advice = score_card_reward(
            offered_cards=offered,
            deck=run_state.deck,
            relics=run_state.relics,
            hp=run_state.hp,
            max_hp=run_state.max_hp,
            floor=run_state.floor,
            ascension=run_state.ascension,
        )
        # Record this pick event so it can be submitted with the run
        _run_card_picks.append({
            "floor":   run_state.floor,
            "offered": offered,
            "chosen":  None,  # updated if we detect a pick — VERIFY
        })
        local_tips = advice.as_tips()
        overlay.update_advice(local_tips)
        # Fetch community seed intel in background — injects above local tips when ready
        _fetch_seed_intel_async(
            run_state.seed, run_state.character, run_state.floor,
            overlay, local_tips,
        )
    else:
        # No active card choice — show deck summary + path advice + ascension context
        archetype = detect_archetype(run_state.deck, run_state.relics)
        tips = [
            {"text": f"Detected build: {archetype or 'unclear'}", "tone": "neutral"},
            {"text": f"Deck: {len(run_state.deck)} cards  |  Relics: {len(run_state.relics)}", "tone": "neutral"},
        ]
        if len(run_state.deck) > 20:
            tips.append({"text": "Deck is getting large — consider skipping next reward", "tone": "warn"})

        # Path advice — shown between floors
        available_nodes = run_state.raw.get("available_nodes",  # VERIFY field name
                          run_state.raw.get("next_nodes", []))
        if available_nodes:
            node_scores = score_path_choices(
                available_nodes = available_nodes,
                hp              = run_state.hp,
                max_hp          = run_state.max_hp,
                gold            = run_state.gold,
                floor           = run_state.floor,
                act             = run_state.act,
                relic_count     = len(run_state.relics),
                deck_size       = len(run_state.deck),
                ascension       = run_state.ascension,
            )
            tips += path_tips(node_scores)
        else:
            # No map data yet — show generic path heuristic based on current state
            hp_pct = round(run_state.hp / run_state.max_hp * 100) if run_state.max_hp else 0
            if hp_pct <= 30:
                tips.append({"text": f"HP critical ({hp_pct}%) — prioritise rest site over elite", "tone": "warn"})
            elif hp_pct <= 50:
                tips.append({"text": f"HP low ({hp_pct}%) — avoid elites if rest site available", "tone": "warn"})
            elif run_state.gold >= 150:
                tips.append({"text": f"High gold ({run_state.gold}g) — shop path worth considering", "tone": "good"})

        tips += ascension_context_tips(run_state.ascension)
        overlay.update_advice(tips)


def _fetch_seed_intel_async(
    seed: str,
    character: str,
    floor: int,
    overlay: OverlayWindow,
    local_tips: list[dict],
):
    """
    Fetch seed intel in a background thread and prepend the result to the
    overlay advice without blocking the file-watcher callback.
    local_tips are displayed immediately; seed intel is injected when it arrives.
    """
    if not _api.is_logged_in or not seed:
        return

    def _worker():
        intel = _api.get_seed_intel(seed, character)
        if not intel or intel.get("total_runs", 0) == 0:
            return
        seed_tips = [{
            "text": f"[Community] {intel['message']}",
            "tone": "good" if intel.get("win_rate", 0) >= 0.5 else "neutral",
        }]
        for s in intel.get("suggestions", []):
            if (
                s.get("floor") == floor
                and s.get("best_pick")
                and s.get("sample_size", 0) >= 2
            ):
                seed_tips.append({
                    "text": (
                        f"[Seed Intel] Floor {floor} best pick: {s['best_pick']} "
                        f"({round(s['pick_win_rate']*100)}% win, n={s['sample_size']})"
                    ),
                    "tone": "good",
                })
        # Merge seed tips at top, preserve local tips below
        merged = seed_tips + local_tips
        overlay.root.after(0, lambda: overlay.update_advice(merged))

    threading.Thread(target=_worker, daemon=True).start()


def main():
    parser = argparse.ArgumentParser(description="STS2 Advisor Overlay")
    parser.add_argument(
        "--save-dir",
        default="",
        help="Path to STS2 save directory or autosave file"
    )
    parser.add_argument(
        "--no-launch",
        action="store_true",
        help="Don't launch STS2 via Steam (use if the game is already running)"
    )
    args = parser.parse_args()

    if not args.no_launch:
        launch_game()

    overlay = OverlayWindow()

    # Show login dialog once if no stored token
    if not _api.is_logged_in:
        def on_login(msg: str):
            overlay.update_advice([{"text": msg, "tone": "good"}])
        LoginDialog(overlay.root, _api, on_success=on_login)
    else:
        overlay.update_advice([{
            "text": f"Logged in as {_api.username} — runs submitted automatically",
            "tone": "good",
        }])

    if not args.save_dir:
        detected = find_save_dir()
        if detected:
            print(f"[Main] Auto-detected save dir: {detected}")
            args.save_dir = detected
        else:
            overlay.show_error(
                "Could not auto-detect STS2 save directory.\n\n"
                "Run with:\n"
                "  python main.py --save-dir \"C:\\Users\\You\\AppData\\\n"
                "  Roaming\\SlayTheSpire2\\steam\\<id>\\profile1\\saves\"\n\n"
                "Or on Linux:\n"
                "  find ~/.steam -name '*.save' 2>/dev/null"
            )
    
    if args.save_dir:
        watcher = SaveFileWatcher(
            save_path=args.save_dir,
            on_change_callback=lambda path: on_save_changed(path, overlay),
        )
        watcher_thread = threading.Thread(target=watcher.start, daemon=True)
        watcher_thread.start()

    overlay.run()


if __name__ == "__main__":
    main()
