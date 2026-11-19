# claude-dot-bak: design

Scheduled backups of everything a Claude account owns, packaged as a
[CLI-Anything](https://github.com/HKUDS/CLI-Anything) harness
(`cli-anything-claude-bak`).

Status: research + prototype. Researched 2026-11-19.

---

## 1. What exists and how to get it

### 1.1 Hosted (claude.ai)

| Data | Official way to get it | In the export? |
| - | - | - |
| Conversations (incl. artifact source, which lives in message content) | **Settings > Privacy > Export data** | Yes |
| Projects, project instructions, project knowledge docs | same export | Projects yes; knowledge **files** you uploaded are not |
| Account/user info | same export | Yes |
| Memory | same export (verify on first real export) | Probably; verify |
| Uploaded files (chat attachments, project files) | none | **No** ("They don't include the original files you uploaded") |
| Files Claude created (docx/xlsx/pptx/pdf) | download from the chat while available | **No** |
| Settings, connectors, styles | none | Partly via user data |

How the official export works
([support article](https://support.claude.com/en/articles/9450526-export-your-claude-data)):

1. You click **Export data** on the web app or Claude Desktop (not mobile).
2. An email arrives at the account address with a download link.
3. The link needs you to be **signed in**, expires after **24 h**, and may work
   **only once**.
4. Team/Enterprise members only see the button if an owner enabled
   "Allow members to export their own data"; Primary Owners export the whole org
   from Organization settings instead
   ([org article](https://support.claude.com/en/articles/13346720-export-your-organization-s-data)).

There is **no public API** for consumer claude.ai data. The Compliance API is
Enterprise-only.

### 1.2 Why not script claude.ai directly

Community tools call the web app's private endpoints
(`/api/organizations/{org}/chat_conversations`, `.../projects`, ...) with the
browser's `sessionKey` cookie. We should **not** do that by default:

* The [Consumer Terms](https://www.anthropic.com/legal/consumer-terms) forbid
  "except when you are accessing our Services via an Anthropic API Key or where
  we otherwise explicitly permit it, to access the Services through automated or
  non-human means, whether through a bot, script, or otherwise", and forbid
  scraping "other than as permitted". A scheduled cookie scraper is exactly that,
  and the risk is the account being suspended: the thing we are trying to protect.
* The endpoints are undocumented and change without notice; Cloudflare already
  returns 403 to plain scripted requests (checked: `GET /api/organizations` →
  403 from a non-browser client).
* A long-lived session cookie on disk is a full account credential.

So by default the hosted side is **assisted, not automated**: the tool does every step
except the click and the signed-in download, which stay human. An **opt-in**
`cloud auto-export` clicks the button for you with a dedicated local browser
profile, at most weekly (see README risk note and `core/autoexport.py`).

### 1.3 Local: Claude Code

All under `~/.claude/` (`%USERPROFILE%\.claude` on Windows; `$CLAUDE_CONFIG_DIR`
if set) plus `~/.claude.json`
([docs](https://code.claude.com/docs/en/claude-directory)):

| Path | What | Back up? |
| - | - | - |
| `~/.claude.json` | account details, trusted folders, **personal MCP servers** (may hold secrets in `env`) | Yes, treat as sensitive |
| `CLAUDE.md`, `settings.json`, `keybindings.json`, `themes/` | config | Yes |
| `skills/`, `commands/`, `agents/`, `rules/`, `output-styles/`, `workflows/`, `agent-memory/`, `hooks` scripts | your authored stuff | Yes |
| `plugins/` | installed plugins + marketplaces | Yes (manifests); caches optional |
| `projects/<project>/*.jsonl` | **session transcripts** | Yes. Claude Code deletes them after `cleanupPeriodDays` (default 30), so a backup is the only long-term copy |
| `projects/<project>/memory/` | auto memory | Yes |
| `todos/`, `plans/`, `history.jsonl`, `file-history/` | session state | Yes |
| `.credentials.json` (Linux/Windows) | OAuth tokens | **No**, excluded |
| `shell-snapshots/`, `statsig/`, `telemetry/`, `debug/`, caches | noise | No |

Per-repo `.claude/` and `.mcp.json` live in each project and are normally in git;
optional opt-in scan root.

### 1.4 Local: Claude Desktop

| OS | App data | Notes |
| - | - | - |
| macOS | `~/Library/Application Support/Claude/` | logs in `~/Library/Logs/Claude/` |
| Windows | `%APPDATA%\Claude\`, newer builds `%LOCALAPPDATA%\Claude\`; MSIX: `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\{Roaming,Local}\Claude\` | check all |
| Linux | `~/.config/Claude/` | |

Plus `~/Claude/` (or legacy `~/Documents/Claude/`): Artifacts, scheduled-task
results and project files the app writes for you.

Inside the app-data dir
([data-storage docs](https://claude.com/docs/third-party/claude-desktop/data-storage)):

| Path | What | Back up? |
| - | - | - |
| `claude_desktop_config.json` | MCP servers (may hold secrets) | Yes, sensitive |
| `local-agent-mode-sessions/` | **Cowork/Chat local history**, `audit.jsonl`, uploads/outputs, local **memory** (`memory/`, `spaces/<id>/memory/`), `cowork_account_settings.json` | Yes. This exists only on this device |
| `claude-code-sessions/` | Code-tab session records (transcripts are in `~/.claude/projects`) | Yes |
| `cowork_plugins/`, `extensions*` | installed plugins/extensions | Yes |
| `configLibrary/` | local configs (keys encrypted) | Yes |
| `plugin-mcp-auth/`, `connectors/*/plugin-mcp/.credentials.json` | sign-ins | **No**, excluded |
| `vm_bundles/`, `claude-code/`, `claude-code-vm/` | binaries, VM disks (GBs) | No |
| `Cache/`, `Code Cache/`, `GPUCache/`, `blob_storage/`, `Crashpad/` | Chromium cache | No |
| `IndexedDB/`, `Local Storage/`, `Session Storage/` | UI state | Optional (`--include-ui-state`) |

The `Claude-3p/` sibling directory (third-party-provider mode) has the same
layout and is picked up when present.

---

## 2. Recommended design

One Python package, built to CLI-Anything's harness conventions so agents can
drive it (`--json` everywhere, REPL when run bare, `SKILL.md` shipped):

```
cli-anything-claude-bak
├── scan                      # what's on this machine, sizes, sensitive files
├── backup local              # snapshot ~/.claude, ~/.claude.json, Desktop, ~/Claude
├── backup cloud request      # opens Settings > Privacy in your browser + notifies you
├── backup cloud ingest ZIP   # file the downloaded export into the store, dedupe
├── backup cloud watch        # pick up new data-*.zip from ~/Downloads automatically
├── backup run                # what the scheduler calls: local + watch + reminders
├── list / verify / restore   # browse snapshots, check hashes, restore a path
└── schedule install|remove|status   # systemd timer / launchd / Task Scheduler
```

### 2.1 Storage

```
<dest>/                       default ~/ClaudeBackups (configurable, e.g. a synced drive)
├── local/<host>/<UTC-stamp>/       one snapshot per run
│   ├── manifest.json               every file: path, size, sha256, mtime, source
│   └── files/<source>/...          or files.tar.zst when --archive
├── cloud/<UTC-stamp>-<sha8>.zip    the untouched official export
└── state.json                      last runs, last export, schedule info
```

* Snapshots are plain copies with a hash manifest so they are readable without
  the tool. Unchanged files are hard-linked to the previous snapshot
  (rsync `--link-dest` style), so daily runs cost almost nothing on disk.
* Retention: keep 14 daily, 8 weekly, 12 monthly (configurable).
* Optional encryption of the whole snapshot with `age` (recipient in config).
* Optional off-site: point `<dest>` at a synced folder, or hand off to
  `restic`/`rclone` as a post-run hook.

### 2.2 Secrets

Credential files are excluded by default (list in §1.3/§1.4). Config files that
can embed MCP secrets (`~/.claude.json`, `claude_desktop_config.json`) are
backed up but flagged in the manifest; `--redact-mcp-env` replaces `env` values
with `"<redacted>"`. Nothing is ever uploaded by the tool itself.

### 2.3 Scheduling

`schedule install --every daily --at 03:30` writes a native unit that runs
`cli-anything-claude-bak backup run --json`:

* **Linux**: `~/.config/systemd/user/claude-dot-bak.{service,timer}`,
  `Persistent=true` so a missed run catches up at next boot.
* **macOS**: `~/Library/LaunchAgents/ai.claude-dot-bak.plist` with
  `StartCalendarInterval`.
* **Windows**: `schtasks /Create /SC DAILY /ST 03:30 /TN claude-dot-bak ...`
  with "run as soon as possible after a missed start".

The cloud side runs on its own cadence (default monthly): `backup run` checks
the age of the newest cloud export; when it's overdue it sends a desktop
notification ("Time to export your claude.ai data") and opens
`https://claude.ai/settings/data-privacy-controls`. After you click and
download, `cloud watch` notices the `data-*.zip` in `~/Downloads`, verifies it
is a Claude export (contains `conversations.json`), and moves it into the store.

### 2.4 Hosted job?

Not recommended. Local data only exists on your machines, so the job has to run
there anyway, and a hosted job would need either your session cookie (ToS and
security problem) or mailbox access plus a signed-in browser for the one-time
link. A future opt-in could watch Gmail for the export email and pop the link
open, but the click and download still need you.

### 2.5 Optional: richer cloud coverage (opt-in, off by default)

If you accept the ToS risk for your own account, a `--unofficial-web` mode could
pull uploaded files and per-conversation JSON through your **already open,
signed-in browser** (Claude in Chrome / CDP), rate-limited and read-only. We
recommend leaving this out until the official export proves insufficient.

### 2.6 Per-project mirror into a private GitHub repo

The official export's coverage is uncertain, so each Claude project can also be
mirrored by **Claude itself, from inside the project**, using the tools a
project session already has. This is the product's own access path, not
scraping, so it stays within the Terms.

What a project session can read today (checked 2026-11-19):

| Content | How the routine reads it | In the official export? |
| - | - | - |
| Project chat | `read_project_chat` | Unclear |
| Every thread, full transcript | `list_threads` + `read_thread` | Unclear |
| Project memory (`MEMORY.md` + notes) | memory folder on disk | Probably not |
| Project files (`/mnt/project-files/`, incl. uploads) | file copy | **No** (uploads are excluded) |
| Artifacts (HTML, published files, comments, data) | `Artifact list/read`, `ArtifactData` | Artifact source only if in chat messages |
| Docs | Claude Docs `read`/`export` | Unknown |
| Project instructions, repos, settings | session context | Partly |
| PRs/code | already in the project's repos | n/a |

Not covered: regular claude.ai chats outside projects. For those, use the
official export (2.3). **Don't** snapshot the cloud sandbox itself: it is
temporary and holds proxy credentials and tokens.

Layout, one private repo per project (`<project>-claude-ai--cloud-environment`):

```
README.md                 project name, topic, instructions, repos, last run
chat/project-chat.md      top-level messages, oldest first
threads/<date>-<slug>.md  one file per thread (+ .json raw)
memory/                   copy of project memory
files/                    copy of project files
artifacts/<slug>/         index.html, published files, comments.json, data.json
docs/<slug>.md            Claude Docs as Markdown
```

Run as a **scheduled task in each project** (daily). Each run rewrites the tree
and commits only the diff, so git history works as versioning. The repo must exist
and be attached to the project first. Creating repos stays a manual step for the
user.

---

## 3. Plan

1. **Prototype (this PR)**: `scan`, `backup local` (exclusions, sha256 manifest,
   hard-link dedupe, `--redact-mcp-env`), `verify`, `list`,
   `backup cloud request|ingest|watch`, `backup run`, `schedule install|remove`
   for systemd / launchd / Task Scheduler. 9 tests.
2. Retention pruning, `restore`, desktop notification when an export is due.
3. Real-export check: confirm what's in a current claude.ai zip (memory? artifacts?).
4. `age` encryption, post-run hooks (rclone/restic), CLI-Anything `SKILL.md`,
   tests per the harness TEST.md convention, submit to CLI-Hub.

## 4. Open questions

* Where should backups go (local disk, a synced folder, rclone remote)?
* How often for local (daily?) and for the claude.ai export (monthly?)
* Should MCP `env` secrets be kept, redacted, or encrypted?
