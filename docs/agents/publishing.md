# Committing and publishing

One repo: `main`, origin `github.com/silvermoong/stocking-texture-tool`. Everything in it is public, the development material too (`.scratch/`, `AGENTS.md`, `docs/agents/`); `.gitattributes` keeps those out of GitHub's code ZIPs, so `install.bat` never copies them to users. Agents work on `agents/*` branches in worktrees and merge into `main`. Users get `main` the next time they run `install.bat`, so a push is a release.

## 提交 (commit)

Commit in the style of `git log`. That is all a 提交 does: nothing is pushed.

## 发布 (publish)

Only when the user asks.

1. **Commit** the pending work, as for 提交. Done when `git status --porcelain --untracked-files=no` prints nothing.
2. **Pull**: `git pull --ff-only`. GitHub may hold a merged pull request that is not here yet. If it refuses, rebase the local commits onto `origin/main` and run the tests again.
3. **Push**: `git push origin main`. Done when `git status -sb` reads `## main...origin/main` with nothing ahead.

## Pull requests and issues from others

- A pull request is merged on GitHub, never copied by hand, so its author stays on the commit and it shows as merged. Then `git pull --ff-only` here.
- To try one first: `git fetch origin pull/<N>/head:pr-<N>` and check it out in a worktree.
- Issues and pull requests from others are handled on GitHub. The local tracker under `.scratch/` is for our own work.

## Test images and diagnostic artifacts

Prefer procedural, synthetic fixtures; add real-image fixtures sparingly. Public fixtures must be suitable for a public repository and have documented redistribution permission. Keep NSFW images and artwork without confirmed redistribution rights local, even when useful for testing. Permission to inspect an image is not permission to publish it.

Use ignored `tests/data/`, `out/`, or a verified ignored experiment directory for private originals and derivatives. This includes crops, rendered comparisons, PSD layers, image arrays (`.npz`, `.npy`), archives, and images embedded in HTML, notebooks or other text. `.scratch/` is public unless a specific path is ignored; ZIP exclusion via `.gitattributes` does not make Git content private.

Keep reusable test code, synthetic generators and sanitized findings separate from private inputs and outputs. Before staging, verify local artifact paths with `git check-ignore -v`, then inspect the staged file list and diff for images, embedded data and identifying metadata. Missing private samples should cause the relevant tests to skip, not download or copy artwork into tracked paths. Use explicit paths when staging; never force-add ignored private artifacts.

If an image is already tracked, ignoring it does not remove it from Git or history. Report the issue and confirm the intended cleanup with the maintainer; do not delete assets or rewrite history without authorization.

## Rules

- Push `main` only: never `--all`, `--mirror` or a tag without a request. The `pre-push` hook in this repo's `.git/hooks` refuses any other ref and any commit made under the old personal address; `--no-verify` only when the user asks for it.
- Commits here are made as `Silvermoong <17035106+silvermoong@users.noreply.github.com>`: it is set in this repo's own git config, since the global one is the personal address.
- `tools/commit.txt` keeps the placeholder `$Format:%H$`: GitHub fills it in its code ZIPs, and `install.ps1` compares it with the newest commit to decide on an update. Never rewrite or force-push `main`: an installed copy looks its old commit up in the history.
- Commits titled "Agent host session … turn N" under `refs/agents/` are VS Code's agent checkpoints; they stay local.
- Releases and tags happen only on request. A version tag (`v1.0.0`) is a GitHub release. A new install files package (`deps-N`, when requirements or models change) is built by `tools/make_deps.py`, whose docstring has the steps.
