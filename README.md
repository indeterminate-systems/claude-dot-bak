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
