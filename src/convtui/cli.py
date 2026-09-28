"""Command line surface.

`convtui` with no subcommand opens the TUI; `convtui convert` does the same
work headlessly so the tool is usable from scripts and CI. Both go through the
same planner and executor, so their behaviour cannot drift.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table

from convtui import __version__
from convtui.core.config import Config
from convtui.core.executor import ThreadExecutor
from convtui.core.models import CollisionPolicy, Job, JobState, Plan, Summary
from convtui.core.planner import PlanError, build_plan
from convtui.core.registry import load_backends

app = typer.Typer(
    name="convtui",
    help="Convert files between formats — one file, or a whole folder.",
    no_args_is_help=False,
    add_completion=True,
)
console = Console()
err_console = Console(stderr=True)

EXIT_USAGE = 2


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: Annotated[
        bool, typer.Option("--version", "-V", help="Show the version and exit.")
    ] = False,
) -> None:
    """Open the TUI when invoked with no subcommand."""
    if version:
        console.print(f"convtui {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        _launch_tui(Path.cwd())


@app.command()
def tui(
    path: Annotated[
        Path | None,
        typer.Argument(help="Folder or file to open (defaults to the current directory)."),
    ] = None,
) -> None:
    """Open the interactive interface."""
    _launch_tui(path or Path.cwd())


def _launch_tui(root: Path) -> None:
    # Imported lazily so `convtui convert` in a script never pays for Textual.
    from convtui.tui.app import ConvtuiApp

    if not root.exists():
        err_console.print(f"[red]no such file or directory:[/red] {root}")
        raise typer.Exit(EXIT_USAGE)
    ConvtuiApp(root=root.resolve()).run()


@app.command()
def convert(
    sources: Annotated[list[Path], typer.Argument(help="Files and/or folders to convert.")],
    out: Annotated[
        Path | None, typer.Option("--out", "-o", help="Output directory; mirrors the source tree.")
    ] = None,
    to: Annotated[str, typer.Option("--to", "-t", help="Target format, e.g. md.")] = "md",
    recursive: Annotated[
        bool, typer.Option("--recursive/--no-recursive", "-r", help="Descend into subfolders.")
    ] = True,
    overwrite: Annotated[bool, typer.Option("--overwrite", help="Replace existing files.")] = False,
    rename: Annotated[
        bool, typer.Option("--rename", help="Write name-1.md beside an existing file.")
    ] = False,
    in_place: Annotated[
        bool, typer.Option("--in-place", help="Write next to each source file.")
    ] = False,
    include: Annotated[
        list[str] | None, typer.Option("--include", help="Only convert paths matching this glob.")
    ] = None,
    exclude: Annotated[
        list[str] | None, typer.Option("--exclude", help="Skip paths matching this glob.")
    ] = None,
    hidden: Annotated[bool, typer.Option("--hidden", help="Include dotfiles.")] = False,
    workers: Annotated[
        int | None, typer.Option("--workers", "-j", help="Parallel conversions.")
    ] = None,
    converter: Annotated[
        str | None, typer.Option("--converter", help="Force a specific backend.")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", "-n", help="Show what would happen, then stop.")
    ] = False,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit one JSON object per job on stdout.")
    ] = False,
) -> None:
    """Convert files without opening the TUI."""
    cfg, warning = Config.load()
    if warning:
        err_console.print(f"[yellow]warning:[/yellow] {warning}")

    collision = _collision_from_flags(
        overwrite=overwrite, rename=rename, in_place=in_place, default=cfg.collision
    )
    registry = load_backends()

    try:
        plan = build_plan(
            sources,
            out,
            to,
            registry,
            recursive=recursive,
            collision=collision,
            include=include or (),
            exclude=exclude or cfg.exclude,
            show_hidden=hidden or cfg.show_hidden,
            prefer=converter,
        )
    except PlanError as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(EXIT_USAGE) from exc

    if converter and registry.by_name(converter) is None:
        err_console.print(f"[red]error:[/red] unknown converter: {converter}")
        raise typer.Exit(EXIT_USAGE)

    if dry_run:
        _print_plan(plan, as_json=as_json)
        raise typer.Exit(0)

    if not plan.runnable:
        _report_nothing_to_do(plan, as_json=as_json)
        raise typer.Exit(0)

    summary = _run(plan, registry, workers=workers or cfg.workers, as_json=as_json)
    raise typer.Exit(summary.exit_code)


@app.command()
def formats() -> None:
    """List every format pair convtui can handle, and whether it is usable now."""
    registry = load_backends()
    table = Table(title="Supported conversions", title_justify="left")
    table.add_column("from", style="cyan")
    table.add_column("to", style="cyan")
    table.add_column("backend")
    table.add_column("status")

    for conv in registry.all():
        for src_ext in sorted(conv.inputs):
            probe = getattr(conv, "available_for", None)
            availability = probe(src_ext) if probe else conv.available()
            if availability.ok:
                status = "[green]ready[/green]"
            else:
                # escape(): a hint like "convtui[audio]" is not rich markup.
                detail = escape(availability.hint or availability.reason or "unavailable")
                status = f"[yellow]{detail}[/yellow]"
            for dst_ext in sorted(conv.outputs):
                table.add_row(src_ext, dst_ext, conv.name, status)

    console.print(table)


# ---- helpers -----------------------------------------------------------


def _collision_from_flags(
    *, overwrite: bool, rename: bool, in_place: bool, default: CollisionPolicy
) -> CollisionPolicy:
    chosen = [
        flag
        for flag, active in (
            (CollisionPolicy.OVERWRITE, overwrite),
            (CollisionPolicy.RENAME, rename),
            (CollisionPolicy.IN_PLACE, in_place),
        )
        if active
    ]
    if len(chosen) > 1:
        err_console.print("[red]error:[/red] --overwrite, --rename and --in-place are exclusive")
        raise typer.Exit(EXIT_USAGE)
    return chosen[0] if chosen else default


def _run(plan: Plan, registry, *, workers: int, as_json: bool) -> Summary:
    """Execute a plan, rendering progress appropriately for the output mode."""
    runnable = plan.runnable
    interactive = sys.stdout.isatty() and not as_json

    if interactive:
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("converting", total=len(runnable))
            executor = ThreadExecutor(registry, workers=workers)
            try:
                for future in executor.submit_all(runnable):
                    result = future.result()
                    progress.advance(task)
                    if not result.ok:
                        progress.console.print(
                            f"[red]failed[/red] {result.job.src.name}: {escape(result.job.error)}"
                        )
            finally:
                executor.shutdown()
    else:
        executor = ThreadExecutor(registry, workers=workers)
        try:
            for future in executor.submit_all(runnable):
                result = future.result()
                if as_json:
                    print(json.dumps(_job_dict(result.job)), flush=True)
                elif not result.ok:
                    err_console.print(
                        f"failed {result.job.src}: {result.job.error}", highlight=False
                    )
        finally:
            executor.shutdown()

    summary = Summary.from_jobs(plan.jobs)
    if as_json:
        print(
            json.dumps(
                {
                    "summary": {
                        "done": summary.done,
                        "failed": summary.failed,
                        "skipped": summary.skipped,
                    }
                }
            ),
            flush=True,
        )
    else:
        style = "red" if summary.failed else "green"
        console.print(f"[{style}]{summary}[/{style}]")
    return summary


def _print_plan(plan: Plan, *, as_json: bool) -> None:
    if as_json:
        for job in plan.jobs:
            print(json.dumps(_job_dict(job)), flush=True)
        return

    heading = f"Plan — {plan.summary()}"
    if plan.out_dir:
        heading += f"   (into {plan.out_dir})"
    table = Table(title=heading, title_justify="left")
    table.add_column("source")
    table.add_column("→", justify="center")
    table.add_column("destination")
    table.add_column("state")
    for job in plan.jobs:
        root = plan.root or job.src.parent
        state = (
            f"[yellow]skip: {job.skip_reason.value}[/yellow]"
            if job.state is JobState.SKIPPED
            else "[green]convert[/green]"
        )
        dst_root = plan.out_dir or job.dst.parent
        table.add_row(_rel(job.src, root), "→", _rel(job.dst, dst_root), state)
    console.print(table)


def _report_nothing_to_do(plan: Plan, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"summary": {"done": 0, "failed": 0, "skipped": len(plan.skipped)}}))
        return
    if plan.skipped:
        console.print(
            f"[yellow]nothing to do[/yellow] — {len(plan.skipped)} skipped "
            "(use --overwrite or --rename to convert anyway)"
        )
    else:
        console.print("[yellow]no convertible files found[/yellow]")


def _job_dict(job: Job) -> dict[str, object]:
    return {
        "src": str(job.src),
        "dst": str(job.dst),
        "converter": job.converter,
        "state": job.state.value,
        "error": job.error,
        "skip_reason": job.skip_reason.value if job.skip_reason else None,
        "duration": round(job.duration, 3) if job.duration else None,
    }


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


#: Commands and global flags that must reach typer untouched.
_KNOWN_TOKENS = frozenset(
    {
        "tui",
        "convert",
        "formats",
        "--help",
        "-h",
        "--version",
        "-V",
        "--install-completion",
        "--show-completion",
    }
)


def main(argv: list[str] | None = None) -> None:
    """Entry point.

    `convtui ./docs` should open the TUI on that folder, but a positional
    argument on the group callback would make click read subcommand names as
    that argument ("convtui formats" opening a folder called "formats"). So the
    path form is rewritten to the explicit `tui` subcommand here instead.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in _KNOWN_TOKENS and not argv[0].startswith("-"):
        argv = ["tui", *argv]
    app(args=argv)


if __name__ == "__main__":
    main()
