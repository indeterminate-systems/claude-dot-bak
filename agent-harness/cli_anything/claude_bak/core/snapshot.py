"""Make a local snapshot: copy files, hash them, write a manifest.

Unchanged files are hard-linked to the previous snapshot so daily runs are cheap.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
from datetime import datetime, timezone
from pathlib import Path

from .sources import Source

MANIFEST = "manifest.json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk(src: Source):
    """Yield (relative path, absolute path) for files to back up."""
    if src.path.is_file():
        yield src.path.name, src.path
        return
    for root, dirs, files in os.walk(src.path, followlinks=False):
        rel_root = os.path.relpath(root, src.path)
        rel_root = "" if rel_root == "." else rel_root
        dirs[:] = [d for d in dirs
                   if not src.is_excluded(os.path.join(rel_root, d) if rel_root else d)]
        for f in files:
            rel = os.path.join(rel_root, f) if rel_root else f
            p = Path(root) / f
            if src.is_excluded(rel) or p.is_symlink() or not p.is_file():
                continue
            yield rel, p


def host_dir(dest: Path) -> Path:
    return dest / "local" / socket.gethostname()


def latest(dest: Path) -> Path | None:
    d = host_dir(dest)
    snaps = sorted(p for p in d.glob("*") if (p / MANIFEST).exists()) if d.exists() else []
    return snaps[-1] if snaps else None


def _redact_mcp_env(data: bytes) -> bytes:
    try:
        obj = json.loads(data)
    except ValueError:
        return data

    def scrub(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("env", "headers") and isinstance(v, dict):
                    o[k] = {kk: "<redacted>" for kk in v}
                else:
                    scrub(v)
        elif isinstance(o, list):
            for v in o:
                scrub(v)
    scrub(obj)
    return json.dumps(obj, indent=2).encode()


def plan(sources: list[Source]) -> dict:
    """What a backup would copy, without copying it."""
    out = []
    for s in sources:
        n = size = 0
        sensitive = []
        for rel, p in _walk(s):
            n += 1
            size += p.stat().st_size
            if s.is_sensitive(rel):
                sensitive.append(rel)
        out.append({"source": s.name, "path": str(s.path), "description": s.description,
                    "files": n, "bytes": size, "sensitive": sensitive[:50]})
    return {"sources": out, "files": sum(o["files"] for o in out),
            "bytes": sum(o["bytes"] for o in out)}


def create(sources: list[Source], dest: Path, redact_mcp_env: bool = False,
           now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    prev = latest(dest)
    prev_index = {}
    if prev:
        for e in json.loads((prev / MANIFEST).read_text())["files"]:
            prev_index[(e["source"], e["path"])] = e
    snap = host_dir(dest) / stamp
    tmp = snap.with_name(stamp + ".partial")
    if tmp.exists():
        shutil.rmtree(tmp)
    files_root = tmp / "files"
    entries, linked, copied, total = [], 0, 0, 0
    for s in sources:
        for rel, p in _walk(s):
            st = p.stat()
            target = files_root / s.name / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            redact = redact_mcp_env and s.is_sensitive(rel) and p.suffix == ".json"
            old = prev_index.get((s.name, rel.replace(os.sep, "/")))
            if (old and old.get("redacted", False) == redact and old["size"] == st.st_size
                    and old["mtime"] == int(st.st_mtime)):
                try:
                    os.link(prev / "files" / s.name / rel, target)
                    digest = old["sha256"]
                    linked += 1
                except OSError:
                    old = None
            if not (old and target.exists()):
                if redact:
                    target.write_bytes(_redact_mcp_env(p.read_bytes()))
                else:
                    shutil.copy2(p, target)
                digest = _sha256(target)
                copied += 1
            total += st.st_size
            entries.append({"source": s.name, "path": rel.replace(os.sep, "/"),
                            "size": st.st_size, "mtime": int(st.st_mtime), "sha256": digest,
                            "sensitive": s.is_sensitive(rel), "redacted": redact})
    manifest = {
        "tool": "cli-anything-claude-bak", "version": 1, "created": now.isoformat(),
        "host": socket.gethostname(),
        "sources": [{"name": s.name, "path": str(s.path)} for s in sources],
        "files": entries,
    }
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / MANIFEST).write_text(json.dumps(manifest, indent=1))
    os.replace(tmp, snap)
    return {"snapshot": str(snap), "files": len(entries), "bytes": total,
            "copied": copied, "hardlinked": linked, "previous": str(prev) if prev else None}


def verify(snap: Path) -> dict:
    m = json.loads((snap / MANIFEST).read_text())
    bad = []
    for e in m["files"]:
        f = snap / "files" / e["source"] / e["path"]
        if not f.exists():
            bad.append({"path": f"{e['source']}/{e['path']}", "problem": "missing"})
        elif _sha256(f) != e["sha256"]:
            bad.append({"path": f"{e['source']}/{e['path']}", "problem": "hash mismatch"})
    return {"snapshot": str(snap), "checked": len(m["files"]), "ok": not bad, "problems": bad}
