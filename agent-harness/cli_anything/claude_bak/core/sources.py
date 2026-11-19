"""Where Claude keeps data on each OS, and what to skip.

Paths come from the official docs:
  https://code.claude.com/docs/en/claude-directory
  https://claude.com/docs/third-party/claude-desktop/data-storage
"""
from __future__ import annotations

import fnmatch
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Source:
    name: str            # stable id, used as the folder name inside a snapshot
    path: Path
    description: str
    exclude: list[str] = field(default_factory=list)   # glob patterns, relative to path
    sensitive: list[str] = field(default_factory=list)  # backed up, but flagged

    def is_excluded(self, rel: str) -> bool:
        rel = rel.replace(os.sep, "/")
        for pat in self.exclude:
            if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(rel.split("/")[0], pat):
                return True
        return False

    def is_sensitive(self, rel: str) -> bool:
        rel = rel.replace(os.sep, "/")
        return any(fnmatch.fnmatch(rel, pat) for pat in self.sensitive)


# Credentials are never copied.
CLAUDE_CODE_EXCLUDE = [
    ".credentials.json",
    "shell-snapshots", "statsig", "telemetry", "debug", "ide",
    "plugins/cache", "plugins/*/node_modules", "*/node_modules/*",
    "*.lock",
]

DESKTOP_EXCLUDE = [
    # credentials
    "plugin-mcp-auth", "connectors/*/plugin-mcp/.credentials.json", "*.credentials.json",
    # binaries, VM disks, Chromium caches
    "vm_bundles", "claude-code", "claude-code-vm", "Cache", "Code Cache", "GPUCache",
    "DawnCache", "DawnGraphiteCache", "DawnWebGPUCache", "ShaderCache", "blob_storage",
    "Crashpad", "Service Worker", "logs", "SingletonLock", "SingletonSocket",
    "SingletonCookie", "Cookies", "Cookies-journal", "Network",
    # UI state, opt-in only
    "IndexedDB", "Local Storage", "Session Storage", "Shared Dictionary",
]

UI_STATE = {"IndexedDB", "Local Storage", "Session Storage"}


def _home() -> Path:
    return Path(os.environ.get("CLAUDE_BAK_HOME", str(Path.home())))


def _desktop_dirs(home: Path, platform: str) -> list[Path]:
    if platform == "darwin":
        base = home / "Library" / "Application Support"
        return [base / "Claude", base / "Claude-3p"]
    if platform.startswith("win"):
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        msix = local / "Packages" / "Claude_pzs8sxrjxfjjc" / "LocalCache"
        out = []
        for name in ("Claude", "Claude-3p"):
            out += [appdata / name, local / name, msix / "Roaming" / name, msix / "Local" / name]
        return out
    cfg = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    return [cfg / "Claude", cfg / "Claude-3p"]


def discover(include_ui_state: bool = False, platform: str | None = None) -> list[Source]:
    """Return every Claude data location that exists on this machine."""
    platform = platform or sys.platform
    home = _home()
    code_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR", home / ".claude"))
    code_json = (Path(os.environ["CLAUDE_CONFIG_DIR"]) / ".claude.json"
                 if "CLAUDE_CONFIG_DIR" in os.environ else home / ".claude.json")

    candidates = [
        Source("claude-code", code_dir,
               "Claude Code: settings, CLAUDE.md, skills, plugins, memory, session transcripts",
               exclude=list(CLAUDE_CODE_EXCLUDE),
               sensitive=["settings.json", "settings.local.json"]),
        Source("claude-code-json", code_json,
               "Claude Code: account details, trusted folders, personal MCP servers",
               sensitive=["*"]),
    ]
    desktop_exclude = [p for p in DESKTOP_EXCLUDE if not (include_ui_state and p in UI_STATE)]
    seen = set()
    for d in _desktop_dirs(home, platform):
        key = str(d.resolve()) if d.exists() else str(d)
        if key in seen:
            continue
        seen.add(key)
        tag = "claude-desktop-3p" if d.name == "Claude-3p" else "claude-desktop"
        if any(c.name == tag for c in candidates):
            tag += "-" + str(len([c for c in candidates if c.name.startswith(tag)]))
        candidates.append(Source(
            tag, d, "Claude Desktop: MCP config, local chats/Cowork history, memory, plugins",
            exclude=list(desktop_exclude),
            sensitive=["claude_desktop_config.json", "configLibrary/*"]))
    for d in (home / "Claude", home / "Documents" / "Claude"):
        candidates.append(Source(
            "claude-files" if d.parent == home else "claude-files-legacy", d,
            "Claude Desktop outputs: artifacts, scheduled-task results, project files"))
    return [s for s in candidates if s.path.exists()]
