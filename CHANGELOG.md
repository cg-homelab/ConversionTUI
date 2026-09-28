# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — unreleased

First pre-release.

### Added

- Three-pane terminal interface (tree, file list, job queue) with a status bar,
  help overlay, conversion preview, and per-job error detail.
- `convtui convert` for headless use, with `--dry-run`, `--json`, glob
  `--include`/`--exclude`, and `--workers`.
- `convtui formats`, listing every format pair and whether it is usable now.
- MarkItDown backend: PDF, DOCX, PPTX, XLSX, XLS, CSV, HTML, EPUB, IPYNB, JSON,
  TXT and ZIP to Markdown; MSG and audio behind extras.
- Converter registry and `Executor` protocol, so further backends and a
  process-isolated execution mode can be added without touching callers.
- Four collision policies (skip, overwrite, rename, in-place) applied at plan
  time, so the preview matches what runs.
- TOML configuration under the platform config directory.
