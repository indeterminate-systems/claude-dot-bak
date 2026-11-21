"""Auto-export tests against a local stand-in page (never the real claude.ai)."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from cli_anything.claude_bak.core import autoexport

PAGE = """<!doctype html><title>Privacy</title>
<button id=b>Export data</button>
<div id=d role=dialog hidden><button id=c>Export</button></div>
<p id=s></p>
<script>
b.onclick = () => { d.hidden = false; };
c.onclick = () => { d.hidden = true; s.textContent = 'Your export has started. We will email you shortly.'; document.title = 'clicked'; };
</script>"""

LOGIN = "<!doctype html><title>Login</title><p>Continue with email</p>"


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_BAK_STATE", str(tmp_path / "state"))
    return tmp_path


def _page(tmp_path, html, monkeypatch):
    f = tmp_path / "page.html"
    f.write_text(html)
    monkeypatch.setenv("CLAUDE_BAK_EXPORT_URL", f.as_uri())


def test_interval_floor_is_weekly(state):
    now = datetime.now(timezone.utc)
    assert autoexport.due(1, now)[0]
    (autoexport.data_dir() / "autoexport.json").write_text(
        json.dumps({"last_click": (now - timedelta(days=3)).isoformat()}))
    assert not autoexport.due(1, now)[0]          # asking for daily still waits a week
    assert autoexport.due(1, now + timedelta(days=5))[0]


def test_skips_when_not_due(state):
    (autoexport.data_dir() / "autoexport.json").write_text(
        json.dumps({"last_click": datetime.now(timezone.utc).isoformat()}))
    r = autoexport.click_export()
    assert r["skipped"] and not r["clicked"]


playwright = pytest.importorskip("playwright.sync_api")


def test_clicks_export_and_confirm(state, monkeypatch):
    _page(state, PAGE, monkeypatch)
    r = autoexport.click_export()
    assert r["clicked"] and r["confirmed_on_page"], r
    assert autoexport.last_click() is not None
    assert autoexport.click_export()["skipped"]   # second run same week does nothing


def test_reports_signed_out(state, monkeypatch):
    _page(state, LOGIN, monkeypatch)
    monkeypatch.setattr(autoexport, "MIN_INTERVAL_DAYS", 7)
    r = autoexport.click_export()
    assert not r["clicked"] and "not signed in" in r["reason"]
    assert autoexport.last_click() is None
