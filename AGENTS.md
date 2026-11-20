## Agent skills

### Issue tracker

Issues and specs are tracked as local markdown files under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Committing and publishing

提交 (commit) stays in this repo; 发布 (publish) is a push of `main` to GitHub, only when the user asks. See `docs/agents/publishing.md`.

### Tests

When changing the UI (`stocking/static/`), use [uibrowser.py](tests/uibrowser.py) to start the isolated page and take screenshots; do not write a second screenshot script. See [Development](README.md#开发) for running the tests and [UI verification](README.md#界面验证) for budgets, error reports, and what a quiet screenshot cannot prove.

### Test images and diagnostic artifacts

Before adding test images, generating visual diagnostics, or staging their outputs, read [the media policy](docs/agents/publishing.md#test-images-and-diagnostic-artifacts). Prefer synthetic fixtures; private artwork and derivatives belong in verified ignored paths, not public `.scratch/` content.

### Domain docs

Single-context: one `CONTEXT.md` plus `docs/adr/` at the repo root. See `docs/agents/domain.md`.
