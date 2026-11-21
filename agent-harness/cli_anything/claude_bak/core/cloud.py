"""claude.ai data: the official export, assisted.

The Consumer Terms forbid scripted access to claude.ai outside the API, so the
tool never logs in or scrapes. It opens the export page, then files the zip you
download.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import webbrowser
import zipfile
from datetime import datetime, timezone
from pathlib import Path

EXPORT_URL = "https://claude.ai/settings/data-privacy-controls"


def request(open_browser: bool = True) -> dict:
    if open_browser:
        webbrowser.open(EXPORT_URL)
    return {"url": EXPORT_URL, "next": [
        "Click 'Export data'.",
        "Open the emailed link within 24 hours while signed in, and download the zip.",
        "Run: cli-anything-claude-bak backup cloud ingest <zip>  (or let 'watch' find it)",
    ]}


def inspect(zip_path: Path) -> dict:
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        info = {"members": names[:200], "is_claude_export": False, "counts": {}}
        for n in names:
            base = n.rsplit("/", 1)[-1]
            if base in ("conversations.json", "projects.json", "users.json", "memories.json"):
                info["is_claude_export"] = info["is_claude_export"] or base == "conversations.json"
                try:
                    data = json.loads(z.read(n))
                    info["counts"][base] = len(data) if isinstance(data, list) else 1
                except ValueError:
                    info["counts"][base] = None
    return info


def ingest(zip_path: Path, dest: Path, move: bool = False) -> dict:
    info = inspect(zip_path)
    if not info["is_claude_export"]:
        raise ValueError(f"{zip_path} does not look like a Claude export (no conversations.json)")
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    cloud = dest / "cloud"
    cloud.mkdir(parents=True, exist_ok=True)
    for existing in cloud.glob(f"*-{digest[:12]}.zip"):
        return {"stored": str(existing), "duplicate": True, "counts": info["counts"]}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = cloud / f"{stamp}-{digest[:12]}.zip"
    (shutil.move if move else shutil.copy2)(str(zip_path), target)
    (target.with_suffix(".json")).write_text(json.dumps(
        {"source": str(zip_path), "sha256": digest, "ingested": stamp, "counts": info["counts"]},
        indent=1))
    return {"stored": str(target), "duplicate": False, "counts": info["counts"]}


def watch(downloads: Path, dest: Path) -> list[dict]:
    """Ingest any Claude export zips sitting in a downloads folder."""
    out = []
    for z in sorted(downloads.glob("*.zip")):
        try:
            if inspect(z)["is_claude_export"]:
                out.append(ingest(z, dest, move=True))
        except (zipfile.BadZipFile, OSError, ValueError):
            continue
    return out


def last_export_age_days(dest: Path) -> float | None:
    zips = sorted((dest / "cloud").glob("*.zip")) if (dest / "cloud").exists() else []
    if not zips:
        return None
    stamp = datetime.strptime(zips[-1].name[:16], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - stamp).total_seconds() / 86400
