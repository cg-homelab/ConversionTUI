# convtui

A terminal UI for converting files between formats — one file, or a whole
folder at a time. Built for the way `lazygit` and `lazydocker` work: a
persistent three-pane dashboard and single-key actions, not a wizard.

Version 0.1.0 converts documents and data files to Markdown using
[MarkItDown](https://github.com/microsoft/markitdown).

```
┌─ 1 Tree ────┬─ 2 Files ───────────────┬─ 3 Queue ──────────┐
│ ▸ docs/     │ [x] report.pdf     2.1M │ ✓ a.docx → a.md    │
│   ▸ specs/  │ [x] notes.docx    140K  │ ▶ b.pdf  → b.md    │
│   ▸ img/    │ [ ] sheet.xlsx     88K  │ · c.pptx → c.md    │
│             │                         │ ✗ d.pdf  No /Root  │
├─────────────┴─────────────────────────┴────────────────────┤
│ 12 selected · → md · out: ./out · skip · 4 workers  ?:help │
└────────────────────────────────────────────────────────────┘
```

## Install

```bash
pipx install convtui      # or: uv tool install convtui
```

**A note on size:** the install is around 350 MB. MarkItDown depends on
`magika` for file-type detection, which pulls in `onnxruntime`. Nothing
convtui does can avoid that, and the optional extras below change *which
formats work*, not how much is downloaded.

Optional extras:

```bash
pipx install 'convtui[audio]'    # .mp3/.wav/.m4a transcription
pipx install 'convtui[outlook]'  # .msg files
pipx install 'convtui[all]'      # everything
```

## Use

```bash
convtui                 # open the current folder
convtui ~/Documents     # open a specific folder
```

Or headlessly, for scripts and CI:

```bash
convtui convert ./docs -o ./out --to md -r      # recurse, mirror the tree
convtui convert ./docs -o ./out --dry-run       # show the plan, write nothing
convtui convert ./docs -o ./out --json          # one JSON object per job
convtui formats                                 # what can be converted now
```

Exit codes: `0` success, `1` some jobs failed, `2` bad invocation.

### Keys

| Key | Action |
|---|---|
| `j` `k` `↑` `↓` | move |
| `tab` `1` `2` `3` | focus tree / files / queue |
| `space` | toggle selection |
| `a` / `A` | select all / clear |
| `/` | filter (substring or glob) |
| `t` | target format |
| `o` | output directory |
| `p` | cycle collision policy |
| `enter` | convert (files pane) / show error (queue pane) |
| `c` | cancel the queue |
| `r` | retry failed jobs |
| `s` | save current settings as defaults |
| `?` / `q` | help / quit |

### Output and collisions

Conversions mirror the source tree into the output directory: with
`-o out`, `docs/a/b.pdf` becomes `out/a/b.md`. When a destination already
exists the default is to **skip** it — nothing is ever destroyed unless you
ask. Press `p` (or pass a flag) to change that:

| Policy | Behaviour |
|---|---|
| `skip` | leave the existing file alone (default) |
| `overwrite` | replace it |
| `rename` | write `b-1.md` alongside |
| `in-place` | write next to each source file |

Two sources that map to one destination (`a.pdf` and `a.docx` both wanting
`a.md`) are reported as a collision rather than silently overwriting.

## Configuration

Settings are stored at `~/.config/convtui/config.toml` (or the platform
equivalent), written only when you press `s`:

```toml
[defaults]
output_dir = "./out"
target_format = "md"
collision = "skip"
workers = 4
recursive = true

[ui]
theme = "gruvbox"
show_hidden = false

[exclude]
globs = [".git/**", "node_modules/**", "__pycache__/**"]
```

Precedence is CLI flags → `CONVTUI_*` environment variables → this file →
built-in defaults. A malformed config warns and falls back to defaults.

## Known limitations in 0.1.0

- **Only Markdown output.** The converter registry is built for more, but
  MarkItDown is the only backend shipped.
- **Mislabelled files convert to nonsense.** MarkItDown falls back to reading
  a file as plain text when its bytes don't match its extension, so a `.docx`
  that isn't really a `.docx` yields its raw bytes instead of an error.
- **Cancelling is cooperative.** Queued work stops immediately, but a file
  already inside a converter runs to completion — threads can't be killed. The
  status bar says how many are still in flight.
- **Images are not supported.** MarkItDown needs an LLM or exiftool to
  describe an image; without one it produces an empty document.
- **Symlinks are not followed.**

## Development

```bash
uv sync
uv run pytest
uv run ruff check src tests scripts
uv run textual run --dev convtui.tui.app:ConvtuiApp   # with the Textual devtools
uv run python scripts/make_fixtures.py                # regenerate test fixtures
```

The core (`convtui/core/`) never imports Textual, and the TUI and CLI are both
thin clients of it — so conversion behaviour is tested without a terminal, and
the two surfaces cannot drift apart.

## License

MIT
