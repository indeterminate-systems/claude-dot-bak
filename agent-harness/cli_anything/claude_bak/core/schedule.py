"""Native schedulers: systemd user timer, launchd agent, Windows Task Scheduler."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

LABEL = "claude-dot-bak"


def _command(dest: Path) -> list[str]:
    exe = shutil.which("cli-anything-claude-bak")
    base = [exe] if exe else [sys.executable, "-m", "cli_anything.claude_bak"]
    return base + ["--json", "backup", "run", "--dest", str(dest)]


def render(dest: Path, at: str = "03:30", platform: str | None = None) -> dict:
    """Return {path: content} for the files to install, plus the commands to enable them."""
    platform = platform or sys.platform
    dest = Path(dest).expanduser().resolve()
    hh, mm = (int(x) for x in at.split(":"))
    cmd = _command(dest)
    home = Path.home()
    if platform == "darwin":
        args = "\n".join(f"    <string>{a}</string>" for a in cmd)
        plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>ai.{LABEL}</string>
  <key>ProgramArguments</key><array>
{args}
  </array>
  <key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>{hh}</integer><key>Minute</key><integer>{mm}</integer>
  </dict>
  <key>StandardOutPath</key><string>{dest}/last-run.log</string>
  <key>StandardErrorPath</key><string>{dest}/last-run.log</string>
</dict></plist>
"""
        path = home / "Library" / "LaunchAgents" / f"ai.{LABEL}.plist"
        return {"files": {str(path): plist},
                "enable": [["launchctl", "bootstrap", f"gui/{_uid()}", str(path)]],
                "disable": [["launchctl", "bootout", f"gui/{_uid()}", str(path)]]}
    if platform.startswith("win"):
        tr = subprocess.list2cmdline(cmd)
        return {"files": {},
                "enable": [["schtasks", "/Create", "/F", "/SC", "DAILY", "/ST", at,
                            "/TN", LABEL, "/TR", tr]],
                "disable": [["schtasks", "/Delete", "/F", "/TN", LABEL]],
                "note": "Turn on 'Run task as soon as possible after a scheduled start is "
                        "missed' in Task Scheduler for catch-up runs."}
    unit_dir = home / ".config" / "systemd" / "user"
    service = f"""[Unit]
Description=Back up Claude data (claude-dot-bak)

[Service]
Type=oneshot
ExecStart={subprocess.list2cmdline(cmd)}
Nice=10
IOSchedulingClass=idle
"""
    timer = f"""[Unit]
Description=Daily Claude backup

[Timer]
OnCalendar=*-*-* {hh:02d}:{mm:02d}:00
Persistent=true
RandomizedDelaySec=10m

[Install]
WantedBy=timers.target
"""
    return {"files": {str(unit_dir / f"{LABEL}.service"): service,
                      str(unit_dir / f"{LABEL}.timer"): timer},
            "enable": [["systemctl", "--user", "daemon-reload"],
                       ["systemctl", "--user", "enable", "--now", f"{LABEL}.timer"]],
            "disable": [["systemctl", "--user", "disable", "--now", f"{LABEL}.timer"]]}


def _uid() -> int:
    import os
    return os.getuid() if hasattr(os, "getuid") else 0


def install(dest: Path, at: str, dry_run: bool) -> dict:
    spec = render(dest, at)
    if dry_run:
        return {"dry_run": True, **spec}
    for path, content in spec["files"].items():
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content)
    results = [subprocess.run(c, capture_output=True, text=True).returncode for c in spec["enable"]]
    return {"dry_run": False, "installed": list(spec["files"]), "returncodes": results}


def remove(dry_run: bool) -> dict:
    spec = render(Path("."))
    if dry_run:
        return {"dry_run": True, "disable": spec["disable"], "delete": list(spec["files"])}
    rcs = [subprocess.run(c, capture_output=True, text=True).returncode for c in spec["disable"]]
    for path in spec["files"]:
        Path(path).unlink(missing_ok=True)
    return {"dry_run": False, "returncodes": rcs}
