# claude-play

A workspace for small apps and one-off pieces of work done from Claude Code on the web.

## Conventions

- **One folder per task**, named in kebab-case (e.g. `sb-riviera-walk/`). Everything for
  that task lives inside it: source, scripts, data, generated output and its own README.
- **Published with GitHub Pages from the repo root** of the default branch, so a folder's
  `index.html` is live at `https://techdan.github.io/claude-play/<folder>/`.
  Keep pages self-contained or use relative links so they work under that sub-path.
- **Add each new app to the root `index.html`** (one card: title, one-line description,
  link) and to the table in the root `README.md`.
- `.nojekyll` stays at the root so GitHub serves files as-is.
- Large raw downloads and caches are git-ignored inside the task folder (see
  `sb-riviera-walk/.gitignore`); commit only what is needed to rebuild or view.
