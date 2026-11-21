# Atelier RV64: the gallery site

A static site (plain HTML, CSS and a little vanilla JavaScript) with two parts:

- **La Galerie** (`gallery.html`): one generated drawing per CPU architecture version, with a placard and an enlargeable view.
- **Le Journal** (`journal.html`): the development log (`DEVLOG.md`) as a dated timeline, commits, a chart of simulated Dhrystone DMIPS/MHz and the run index.

Open `docs/index.html` in a browser to view it locally. No build step is needed to view it.

## Regenerate

From the repository root:

    python -B scripts/build_site.py

The script reads `cpu/VERSION`, the history table in `cpu/architecture.md` (section 9), `DEVLOG.md` and `git tag -l "cpu-v*"` (read-only), and rewrites `docs/data/*.json`, `docs/art/*.svg` and the three HTML pages. It is deterministic. `docs/assets/` (style and script) is hand-written and untouched. A new version needs one entry in the `WORKS` list in `scripts/build_site.py` (title, caption, unit parameters) before it gets a drawing.

## Publish

GitHub Pages: Settings, Pages, "Deploy from a branch", branch `main`, folder `/docs`. `docs/.nojekyll` makes Pages serve the files as they are. Enabled on 2026-11-21 (branch `main`, folder `/docs`): https://monstercameron.github.io/RISC-V-FPGA-CPU-Research/ . The site shows what is on `main` on GitHub, so it updates when `main` is pushed.

## Honesty notes

Every performance figure is a simulation result from `DEVLOG.md`, labelled as such; nothing is a hardware measurement. Drawing sizes are symbolic, counts follow the history rows. The 0.10.0 core is sized after published measurements of the Apple M5 performance core; it is not Apple's design.
