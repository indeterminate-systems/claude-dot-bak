# claude-dot-bak

Back up your Claude account (claude.ai exports, Claude Code, Claude Desktop) on a
schedule, packaged as a [CLI-Anything](https://github.com/HKUDS/CLI-Anything) harness.

* Design and research: [docs/DESIGN.md](docs/DESIGN.md)
* Prototype CLI: [agent-harness/](agent-harness/)

```sh
pip install -e agent-harness
cli-anything-claude-bak scan                       # what's on this machine
cli-anything-claude-bak backup local               # snapshot to ~/ClaudeBackups
cli-anything-claude-bak backup cloud request       # opens claude.ai export page
cli-anything-claude-bak backup cloud ingest ~/Downloads/data-*.zip
cli-anything-claude-bak schedule install --at 03:30 --dry-run
```

## Optional: automate the claude.ai export click

Off by default. If you turn it on, a local browser clicks **Export data** for
you at most once a week. The emailed zip is still filed by `cloud watch`.

```sh
pip install -e 'agent-harness[browser]' && playwright install chromium
cli-anything-claude-bak backup cloud login          # sign in once, by hand
cli-anything-claude-bak backup cloud auto-export    # clicks if a week has passed
cli-anything-claude-bak schedule install --auto-export
```

> **Risk note.** Anthropic's Consumer Terms don't allow accessing claude.ai
> "through automated or non-human means" except with an API key. This feature
> automates one button on your own account, on your own machine, but it is still
> automation, and the account could be restricted. It's your call. To keep it
> light, it:
> - runs at most every 7 days (hard minimum) and only clicks the export button,
>   without reading chats or calling private APIs
> - uses a dedicated browser profile under `~/.local/share/claude-dot-bak/`
>   (or the OS equivalent). Cookies never go in this repo or in your backups.
>   Delete that folder to sign out.
> - never logs in for you, so you sign in yourself with `cloud login`
>
> You still have to open the emailed download link yourself while signed in.
