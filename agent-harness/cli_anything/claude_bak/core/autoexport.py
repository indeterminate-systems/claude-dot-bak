"""Opt-in: click claude.ai's "Export data" button with a local browser.

Off by default. This automates the web app, which the Consumer Terms restrict,
so it is the user's call for their own account. Guard rails:

* Uses a dedicated browser profile on this machine (never the repo, never the
  backup destination). You sign in once, by hand, with `cloud login`.
* Clicks at most once every MIN_INTERVAL_DAYS (hard floor, no override below it).
* Only clicks the export button. It does not read chats or call private APIs.
* The emailed zip is still picked up by `cloud watch` as before.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from .cloud import EXPORT_URL

MIN_INTERVAL_DAYS = 7


def data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA", base)
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    d = Path(os.environ.get("CLAUDE_BAK_STATE", Path(base) / "claude-dot-bak"))
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d


def profile_dir() -> Path:
    return data_dir() / "browser-profile"


def _state_path() -> Path:
    return data_dir() / "autoexport.json"


def _export_url() -> str:
    # Override only for tests against a local stand-in page.
    return os.environ.get("CLAUDE_BAK_EXPORT_URL", EXPORT_URL)


def last_click() -> datetime | None:
    p = _state_path()
    if not p.exists():
        return None
    return datetime.fromisoformat(json.loads(p.read_text())["last_click"])


def due(interval_days: float, now: datetime | None = None) -> tuple[bool, str]:
    interval_days = max(interval_days, MIN_INTERVAL_DAYS)
    now = now or datetime.now(timezone.utc)
    last = last_click()
    if last is None:
        return True, "never run"
    age = (now - last).total_seconds() / 86400
    if age < interval_days:
        return False, f"last click {age:.1f} days ago, next after {interval_days:g} days"
    return True, f"last click {age:.1f} days ago"


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Auto-export needs Playwright: pip install 'cli-anything-claude-bak[browser]' "
            "&& playwright install chromium") from e
    return sync_playwright


def _launch(p, headless: bool):
    kwargs = dict(user_data_dir=str(profile_dir()), headless=headless,
                  viewport={"width": 1280, "height": 900})
    channel = os.environ.get("CLAUDE_BAK_BROWSER_CHANNEL")  # e.g. "chrome"
    if channel:
        kwargs["channel"] = channel
    exe = os.environ.get("CLAUDE_BAK_BROWSER_PATH")
    if exe:
        kwargs["executable_path"] = exe
    return p.chromium.launch_persistent_context(**kwargs)


def login(timeout_s: int = 600) -> dict:
    """Open a visible browser on the export page so you can sign in once."""
    with _playwright()() as p:
        ctx = _launch(p, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(_export_url())
        try:
            page.get_by_role("button", name=re.compile(r"export data", re.I)).wait_for(
                timeout=timeout_s * 1000)
            ok = True
        except Exception:
            ok = False
        ctx.close()
    return {"signed_in": ok, "profile": str(profile_dir()),
            "note": "Profile is stored on this machine only. Delete it to sign out."}


def click_export(headless: bool = True, interval_days: float = MIN_INTERVAL_DAYS,
                 force_check: bool = True) -> dict:
    """Click Export data once, if due. Returns what happened."""
    if force_check:
        ok, why = due(interval_days)
        if not ok:
            return {"clicked": False, "skipped": True, "reason": why}
    shot = data_dir() / "last-autoexport.png"
    with _playwright()() as p:
        ctx = _launch(p, headless=headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(_export_url(), wait_until="domcontentloaded")
            button = page.get_by_role("button", name=re.compile(r"^\s*export data\s*$", re.I))
            try:
                button.wait_for(timeout=30_000)
            except Exception:
                page.screenshot(path=str(shot))
                signed_out = "/login" in page.url or page.get_by_text(
                    re.compile(r"log in|sign in|continue with", re.I)).count() > 0
                return {"clicked": False, "skipped": False,
                        "reason": ("not signed in: run `cli-anything-claude-bak backup cloud login`"
                                   if signed_out else "Export data button not found"),
                        "url": page.url, "screenshot": str(shot)}
            button.click()
            # Some versions ask to confirm in a dialog.
            confirm = page.get_by_role("dialog").get_by_role(
                "button", name=re.compile(r"export|confirm|continue", re.I))
            try:
                confirm.first.wait_for(timeout=5_000)
                confirm.first.click()
            except Exception:
                pass
            page.wait_for_timeout(3_000)
            confirmed = page.get_by_text(
                re.compile(r"(export|email).*(started|sent|on its way|processing|shortly)", re.I)
            ).count() > 0
            page.screenshot(path=str(shot))
        finally:
            ctx.close()
    now = datetime.now(timezone.utc)
    _state_path().write_text(json.dumps({"last_click": now.isoformat(), "confirmed": confirmed}))
    return {"clicked": True, "confirmed_on_page": confirmed, "at": now.isoformat(),
            "screenshot": str(shot),
            "next": "Open the emailed link while signed in; `cloud watch` files the zip."}
