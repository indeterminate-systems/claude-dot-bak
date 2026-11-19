"""cli-anything-claude-bak: back up Claude Code, Claude Desktop and claude.ai exports."""
from __future__ import annotations

import json
import os
from pathlib import Path

import click

from .core import cloud, schedule, snapshot, sources

DEFAULT_DEST = Path(os.environ.get("CLAUDE_BAK_DEST", Path.home() / "ClaudeBackups"))


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _out(ctx, data, human=None):
    if ctx.obj["json"]:
        click.echo(json.dumps(data, indent=2, default=str))
    elif human:
        human(data)
    else:
        click.echo(json.dumps(data, indent=2, default=str))


@click.group(invoke_without_command=True)
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
@click.pass_context
def cli(ctx, as_json):
    """Back up everything a Claude account keeps, on a schedule."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = as_json
    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)


@cli.command()
@click.option("--include-ui-state", is_flag=True, help="Also Desktop IndexedDB/Local Storage.")
@click.pass_context
def scan(ctx, include_ui_state):
    """Show what Claude data exists on this machine."""
    p = snapshot.plan(sources.discover(include_ui_state))

    def human(d):
        for s in d["sources"]:
            click.echo(f"{s['source']:<20} {s['files']:>7} files {_human(s['bytes']):>9}  {s['path']}")
            if s["sensitive"]:
                click.echo(f"{'':<20} may hold secrets: {', '.join(s['sensitive'][:5])}")
        click.echo(f"{'total':<20} {d['files']:>7} files {_human(d['bytes']):>9}")
    _out(ctx, p, human)


@cli.group()
def backup():
    """Make backups."""


@backup.command("local")
@click.option("--dest", type=click.Path(path_type=Path), default=DEFAULT_DEST, show_default=True)
@click.option("--redact-mcp-env", is_flag=True, help="Replace MCP env/header values with <redacted>.")
@click.option("--include-ui-state", is_flag=True)
@click.pass_context
def backup_local(ctx, dest, redact_mcp_env, include_ui_state):
    """Snapshot ~/.claude, ~/.claude.json, Claude Desktop data and ~/Claude."""
    r = snapshot.create(sources.discover(include_ui_state), dest, redact_mcp_env)
    _out(ctx, r, lambda d: click.echo(
        f"Snapshot {d['snapshot']}: {d['files']} files, {_human(d['bytes'])} "
        f"({d['copied']} copied, {d['hardlinked']} unchanged)"))


@backup.group("cloud")
def backup_cloud():
    """claude.ai official data export (assisted, never scripted)."""


@backup_cloud.command("request")
@click.option("--no-browser", is_flag=True)
@click.pass_context
def cloud_request(ctx, no_browser):
    """Open claude.ai Settings > Privacy so you can click Export data."""
    _out(ctx, cloud.request(not no_browser),
         lambda d: click.echo(d["url"] + "\n" + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(d["next"]))))


@backup_cloud.command("ingest")
@click.argument("zip_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--dest", type=click.Path(path_type=Path), default=DEFAULT_DEST, show_default=True)
@click.option("--move", is_flag=True, help="Move instead of copy.")
@click.pass_context
def cloud_ingest(ctx, zip_path, dest, move):
    """File a downloaded claude.ai export zip into the backup store."""
    _out(ctx, cloud.ingest(zip_path, dest, move))


@backup_cloud.command("watch")
@click.option("--downloads", type=click.Path(path_type=Path), default=Path.home() / "Downloads")
@click.option("--dest", type=click.Path(path_type=Path), default=DEFAULT_DEST, show_default=True)
@click.pass_context
def cloud_watch(ctx, downloads, dest):
    """Pick up any Claude export zips in your Downloads folder."""
    _out(ctx, {"ingested": cloud.watch(downloads, dest)})


@backup.command("run")
@click.option("--dest", type=click.Path(path_type=Path), default=DEFAULT_DEST, show_default=True)
@click.option("--cloud-every", default=30, show_default=True, help="Days between claude.ai exports.")
@click.option("--redact-mcp-env", is_flag=True)
@click.pass_context
def backup_run(ctx, dest, cloud_every, redact_mcp_env):
    """What the scheduler runs: local snapshot, pick up exports, remind when one is due."""
    result = {"local": snapshot.create(sources.discover(), dest, redact_mcp_env)}
    downloads = Path.home() / "Downloads"
    result["cloud_ingested"] = cloud.watch(downloads, dest) if downloads.exists() else []
    age = cloud.last_export_age_days(dest)
    result["cloud_export_age_days"] = age
    result["cloud_export_due"] = age is None or age >= cloud_every
    _out(ctx, result)


@cli.command("list")
@click.option("--dest", type=click.Path(path_type=Path), default=DEFAULT_DEST, show_default=True)
@click.pass_context
def list_(ctx, dest):
    """List snapshots and stored exports."""
    host = snapshot.host_dir(dest)
    local = sorted(p.name for p in host.glob("*") if (p / snapshot.MANIFEST).exists()) if host.exists() else []
    clouds = sorted(p.name for p in (dest / "cloud").glob("*.zip")) if (dest / "cloud").exists() else []
    _out(ctx, {"dest": str(dest), "local": local, "cloud": clouds})


@cli.command()
@click.argument("snap", required=False, type=click.Path(path_type=Path))
@click.option("--dest", type=click.Path(path_type=Path), default=DEFAULT_DEST, show_default=True)
@click.pass_context
def verify(ctx, snap, dest):
    """Re-hash a snapshot (latest by default) against its manifest."""
    snap = snap or snapshot.latest(dest)
    if not snap:
        raise click.ClickException("No snapshots yet.")
    r = snapshot.verify(Path(snap))
    _out(ctx, r)
    if not r["ok"]:
        ctx.exit(1)


@cli.group("schedule")
def schedule_():
    """Install a daily run with systemd, launchd or Task Scheduler."""


@schedule_.command("install")
@click.option("--at", default="03:30", show_default=True, help="Local time HH:MM.")
@click.option("--dest", type=click.Path(path_type=Path), default=DEFAULT_DEST, show_default=True)
@click.option("--dry-run", is_flag=True, help="Print what would be installed.")
@click.pass_context
def schedule_install(ctx, at, dest, dry_run):
    r = schedule.install(dest, at, dry_run)

    def human(d):
        for path, content in d.get("files", {}).items():
            click.echo(f"--- {path}\n{content}")
        for c in d.get("enable", []):
            click.echo("$ " + " ".join(c))
        if not d["dry_run"]:
            click.echo("Installed.")
    _out(ctx, r, human)


@schedule_.command("remove")
@click.option("--dry-run", is_flag=True)
@click.pass_context
def schedule_remove(ctx, dry_run):
    _out(ctx, schedule.remove(dry_run))


@cli.command()
@click.pass_context
def repl(ctx):
    """Interactive mode."""
    click.echo("cli-anything-claude-bak. Commands: scan, backup local, list, verify, "
               "schedule install --dry-run, quit")
    while True:
        try:
            line = input("claude-bak> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if line in ("quit", "exit", "q"):
            break
        if not line:
            continue
        try:
            cli.main(args=line.split(), standalone_mode=False, obj=dict(ctx.obj))
        except click.ClickException as e:
            e.show()
        except SystemExit:
            pass


def main():
    cli(obj={})


if __name__ == "__main__":
    main()
