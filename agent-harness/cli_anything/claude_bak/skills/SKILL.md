---
name: cli-anything-claude-bak
description: Back up Claude Code, Claude Desktop and claude.ai export data, and schedule it. Use when asked to back up, snapshot, verify or restore Claude data.
---

# cli-anything-claude-bak

Always pass `--json` for machine-readable output.

| Task | Command |
| - | - |
| See what exists and what may hold secrets | `cli-anything-claude-bak --json scan` |
| Snapshot local data now | `cli-anything-claude-bak --json backup local [--dest DIR] [--redact-mcp-env]` |
| Start a claude.ai export (user must click) | `cli-anything-claude-bak backup cloud request` |
| File a downloaded export zip | `cli-anything-claude-bak --json backup cloud ingest PATH.zip` |
| Pick up exports from ~/Downloads | `cli-anything-claude-bak --json backup cloud watch` |
| Scheduled job body | `cli-anything-claude-bak --json backup run` |
| List / verify | `cli-anything-claude-bak --json list`, `... verify` |
| Install daily schedule | `cli-anything-claude-bak schedule install --at 03:30 [--dry-run]` |

Rules: never log in to or scrape claude.ai; the export button and the signed-in
download are done by the user. Credential files are excluded automatically.
