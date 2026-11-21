import json
import os
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli_anything.claude_bak.claude_bak_cli import cli
from cli_anything.claude_bak.core import cloud, schedule, snapshot, sources


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    code = home / ".claude"
    (code / "skills" / "x").mkdir(parents=True)
    (code / "skills" / "x" / "SKILL.md").write_text("skill")
    (code / "projects" / "p" ).mkdir(parents=True)
    (code / "projects" / "p" / "s.jsonl").write_text('{"m":1}\n')
    (code / ".credentials.json").write_text("SECRET")
    (code / "shell-snapshots").mkdir()
    (code / "shell-snapshots" / "a.sh").write_text("x")
    (home / ".claude.json").write_text(json.dumps(
        {"mcpServers": {"gh": {"command": "x", "env": {"TOKEN": "abc"}}}}))
    desk = home / ".config" / "Claude"
    (desk / "Cache").mkdir(parents=True)
    (desk / "Cache" / "blob").write_text("junk")
    (desk / "plugin-mcp-auth").mkdir()
    (desk / "plugin-mcp-auth" / ".credentials.json").write_text("SECRET")
    (desk / "local-agent-mode-sessions" / "s1").mkdir(parents=True)
    (desk / "local-agent-mode-sessions" / "s1" / "audit.jsonl").write_text("{}")
    (desk / "claude_desktop_config.json").write_text(json.dumps(
        {"mcpServers": {"fs": {"command": "npx", "env": {"KEY": "k"}}}}))
    monkeypatch.setenv("CLAUDE_BAK_HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    return home


def _all_files(snap):
    return {str(p.relative_to(snap / "files")) for p in (snap / "files").rglob("*") if p.is_file()}


def test_discover_and_excludes(fake_home, tmp_path):
    srcs = sources.discover(platform="linux")
    assert {s.name for s in srcs} == {"claude-code", "claude-code-json", "claude-desktop"}
    r = snapshot.create(srcs, tmp_path / "dest")
    files = _all_files(Path(r["snapshot"]))
    assert "claude-code/skills/x/SKILL.md" in files
    assert "claude-code/projects/p/s.jsonl" in files
    assert "claude-desktop/local-agent-mode-sessions/s1/audit.jsonl" in files
    assert not any("credentials" in f for f in files)
    assert not any("Cache" in f or "shell-snapshots" in f for f in files)


def test_second_run_hardlinks_and_verifies(fake_home, tmp_path):
    srcs = sources.discover(platform="linux")
    dest = tmp_path / "dest"
    snapshot.create(srcs, dest)
    import time; time.sleep(1.1)
    r2 = snapshot.create(srcs, dest)
    assert r2["copied"] == 0 and r2["hardlinked"] == r2["files"]
    assert snapshot.verify(Path(r2["snapshot"]))["ok"]


def test_redact_mcp_env(fake_home, tmp_path):
    r = snapshot.create(sources.discover(platform="linux"), tmp_path / "d", redact_mcp_env=True)
    snap = Path(r["snapshot"])
    data = json.loads((snap / "files/claude-desktop/claude_desktop_config.json").read_text())
    assert data["mcpServers"]["fs"]["env"]["KEY"] == "<redacted>"
    data = json.loads((snap / "files/claude-code-json/.claude.json").read_text())
    assert data["mcpServers"]["gh"]["env"]["TOKEN"] == "<redacted>"


def _export_zip(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("conversations.json", json.dumps([{"uuid": "1"}, {"uuid": "2"}]))
        z.writestr("projects.json", json.dumps([{"uuid": "p"}]))
        z.writestr("users.json", json.dumps([{"uuid": "u"}]))
    return path


def test_cloud_ingest_dedupes_and_watch(tmp_path):
    z = _export_zip(tmp_path / "data-2026.zip")
    dest = tmp_path / "dest"
    r = cloud.ingest(z, dest)
    assert r["counts"]["conversations.json"] == 2 and not r["duplicate"]
    assert cloud.ingest(z, dest)["duplicate"]
    dl = tmp_path / "dl"; dl.mkdir()
    zipfile.ZipFile(dl / "other.zip", "w").writestr("a.txt", "x")
    _export_zip(dl / "data-new.zip")
    assert len(cloud.watch(dl, dest)) == 1
    assert cloud.last_export_age_days(dest) < 1


def test_cloud_rejects_non_export(tmp_path):
    p = tmp_path / "x.zip"
    zipfile.ZipFile(p, "w").writestr("a.txt", "x")
    with pytest.raises(ValueError):
        cloud.ingest(p, tmp_path / "d")


@pytest.mark.parametrize("plat,expect", [("linux", "systemctl"), ("darwin", "launchctl"),
                                         ("win32", "schtasks")])
def test_schedule_render(tmp_path, plat, expect):
    spec = schedule.render(tmp_path, "04:15", platform=plat)
    assert spec["enable"][-1][0] == expect
    blob = json.dumps(spec)
    assert "backup" in blob and "run" in blob


def test_cli_json(fake_home, tmp_path):
    runner = CliRunner()
    r = runner.invoke(cli, ["--json", "scan"], obj={})
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["files"] > 0
    r = runner.invoke(cli, ["--json", "backup", "run", "--dest", str(tmp_path / "d")], obj={})
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["cloud_export_due"] is True
