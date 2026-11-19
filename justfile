# claude-dot-bak shortcuts. `just` lists them; `just <name> [args]` runs one.

cli := "python -m cli_anything.claude_bak"

# List recipes
default:
    @just --list --unsorted

# Enter the dev shell, or run a command in it: just dev pytest agent-harness
dev *cmd:
    {{ if cmd == "" { "nix develop" } else { "nix develop --command " + cmd } }}

# Run any CLI command from this checkout: just cli list
cli *args:
    {{cli}} {{args}}

# Show what Claude data is on this machine
scan *args:
    {{cli}} scan {{args}}

# Back up local Claude Code / Desktop data now
local *args:
    {{cli}} backup local {{args}}

# Verify the latest snapshot against its hashes
verify *args:
    {{cli}} verify {{args}}

# List snapshots and stored exports
list *args:
    {{cli}} list {{args}}

# Sign in to claude.ai once, for auto-export
login:
    {{cli}} backup cloud login

# Click Export data on claude.ai, browser visible (at most weekly)
export *args:
    {{cli}} backup cloud auto-export --headed {{args}}

# File any export zips from ~/Downloads
watch *args:
    {{cli}} backup cloud watch {{args}}

# Install the CLI on your PATH (needed before `just schedule`)
install:
    nix profile install .

# Install the daily schedule (default 03:30) with weekly auto-export
schedule at="03:30":
    cli-anything-claude-bak schedule install --at {{at}} --auto-export

# Preview the schedule files without installing
schedule-preview at="03:30":
    {{cli}} schedule install --at {{at}} --auto-export --dry-run

# Run the scheduled backup now
now:
    systemctl --user start claude-dot-bak.service

# Follow the scheduled backup log
log:
    journalctl --user -u claude-dot-bak -f

# Show the backup timer
timers:
    systemctl --user list-timers claude-dot-bak.timer

# Run the tests
test *args:
    python -m pytest -q agent-harness {{args}}
