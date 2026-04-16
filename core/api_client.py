"""
core/api_client.py

Handles all communication between the overlay and the community API.
- Stores auth token locally (no re-login on each launch)
- Submits completed runs in the background (non-blocking)
- Fetches seed intelligence for the current run
"""

import json
import threading
import urllib.request
import urllib.error
import urllib.parse
import os
from pathlib import Path
from typing import Optional

API_BASE = os.environ.get("STS2_API_URL", "https://sts2advisor.com/api")
TOKEN_FILE = Path.home() / ".sts2advisor" / "token.json"


class ApiClient:
    def __init__(self):
        self._token: Optional[str] = None
        self._username: Optional[str] = None
        self._load_token()

    # ------------------------------------------------------------------
    # Auth state
    # ------------------------------------------------------------------

    @property
    def is_logged_in(self) -> bool:
        return self._token is not None

    @property
    def username(self) -> Optional[str]:
        return self._username

    def _load_token(self):
        """Load saved token from disk (survives restarts — no re-login needed)."""
        try:
            data = json.loads(TOKEN_FILE.read_text())
            self._token = data.get("token")
            self._username = data.get("username")
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass

    def _save_token(self, token: str, username: str):
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(json.dumps({"token": token, "username": username}))
        TOKEN_FILE.chmod(0o600)  # owner read/write only

    def logout(self):
        self._token = None
        self._username = None
        try:
            TOKEN_FILE.unlink(missing_ok=True)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Login / Register (called once from the login dialog)
    # ------------------------------------------------------------------

    def login(self, username: str, password: str) -> tuple[bool, str]:
        """Returns (success, message)."""
        ok, result = self._post("/auth/login", {"username": username, "password": password})
        if ok:
            self._token = result["access_token"]
            self._username = username
            self._save_token(self._token, username)
            return True, f"Logged in as {username}"
        return False, result.get("detail", "Login failed")

    def register(self, username: str, email: str, password: str) -> tuple[bool, str]:
        """Returns (success, message)."""
        ok, result = self._post(
            "/auth/register",
            {"username": username, "email": email, "password": password},
        )
        if ok:
            self._token = result["access_token"]
            self._username = username
            self._save_token(self._token, username)
            return True, f"Account created. Welcome, {username}!"
        return False, result.get("detail", "Registration failed")

    # ------------------------------------------------------------------
    # Run submission (called silently when a run ends — background thread)
    # ------------------------------------------------------------------

    def submit_run_async(self, run_payload: dict):
        """Fire-and-forget — overlay never blocks waiting for this."""
        if not self._token:
            return
        thread = threading.Thread(
            target=self._submit_run_worker,
            args=(run_payload,),
            daemon=True,
        )
        thread.start()

    def _submit_run_worker(self, payload: dict):
        try:
            self._post("/runs/submit", payload, auth=True)
        except Exception:
            pass  # Submission failure is silent — never crash the overlay

    # ------------------------------------------------------------------
    # Seed intelligence (called on run start with the seed)
    # ------------------------------------------------------------------

    def get_seed_intel(self, seed: str, character: Optional[str] = None) -> Optional[dict]:
        """Returns parsed response dict, or None on any failure."""
        if not self._token or not seed:
            return None
        params = urllib.parse.urlencode({"seed": seed, **({"character": character} if character else {})})
        return self._get(f"/seeds/intel?{params}", auth=True)

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _post(self, path: str, body: dict, auth: bool = False) -> tuple[bool, dict]:
        url = API_BASE.rstrip("/") + path
        data = json.dumps(body).encode()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "sts2-overlay/0.1",
        }
        if auth and self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return True, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read())
            except Exception:
                detail = {"detail": str(e)}
            return False, detail
        except Exception:
            return False, {"detail": "Network error"}

    def _get(self, path: str, auth: bool = False) -> Optional[dict]:
        url = API_BASE.rstrip("/") + path
        headers = {
            "Accept": "application/json",
            "User-Agent": "sts2-overlay/0.1",
        }
        if auth and self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception:
            return None
