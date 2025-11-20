# gitmeup

`gitmeup` looks at your current `git diff` / `git status` and turns that messy working tree into small, focused, Conventional Commit–style `git add` / `git commit` commands, with safe quoting for awkward paths. It does **not** push anything, it just helps you decide *what* to commit and *how* to phrase it.

---

## What problem does it solve?

Typical flow when you have a pile of changes:

- You stare at `git status` and `git diff` deciding how to split changes.
- You manually type `git add` commands, hoping you did not miss a file.
- You spend too long crafting a commit message that fits Conventional Commits.
- You worry about weird file paths breaking your shell.

`gitmeup` automates that boring part:

- Groups changes into **atomic, semantically focused commits** (refactor, docs, assets, etc.).
- Proposes ready-to-paste `git add` / `git commit -m "type(scope): message"` sequences.
- Handles **strict path quoting** so file names with spaces, brackets, unicode, etc. do not explode your shell.
- Runs in **dry-run** by default, so nothing happens until you opt in.

---

## How it works (in practice)

From inside a git repo, `gitmeup` collects:

- `git diff --stat`
- `git status --short`
- `git diff` with noisy formats excluded from the body:
  - `*.png`, `*.jpg`, `*.jpeg`, `*.gif`, `*.svg`, `*.webp`

This context is sent to a Gemini model, which returns a single `bash` code block with:

- Batches of `git add` / `git rm` / `git mv`
- Followed by matching `git commit -m "…"`, using Conventional Commits

You can then:

- Inspect the proposed commands (default), or
- Let `gitmeup` run them with `--apply`.

No `git push` is ever generated.

---

## Installation

### From PyPI (recommended)

```bash
pip install gitmeup
````

This installs the `gitmeup` CLI into your environment.

### From source (editable dev install)

```bash
git clone https://github.com/ikramagix/gitmeup
cd gitmeup

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -e .
```

---

## Configuration

`gitmeup` talks to Google Gemini via `google-genai`. It needs:

* A Gemini API key
* A model name (default is `gemini-2.0-flash-lite` unless overridden)

### 1. Secrets via env file (recommended)

`gitmeup` will automatically load:

1. `~/.gitmeup.env` (global, for secrets and defaults)
2. `./.env` in the current repo (for local overrides, optional)

Values in the environment override file values, and CLI flags override both.

Example global config:

```env
# ~/.gitmeup.env
GEMINI_API_KEY=your-gemini-key-here
GITMEUP_MODEL=gemini-2.0-flash-lite
```

> Keep `~/.gitmeup.env` out of any git repo. It lives only in your home directory.

Optional per-repo overrides:

```env
# ./.env (inside a project, usually without secrets if repo is shared)
GITMEUP_MODEL=gemini-2.0-pro
```

If you use a local `.env` with secrets, **ensure** `.env` is listed in that repo’s `.gitignore`.

### 2. Environment variables

You can also configure via plain env vars:

```bash
export GEMINI_API_KEY="your-gemini-key"
export GITMEUP_MODEL="gemini-2.0-flash-001"
```

### 3. CLI overrides (use sparingly)

The CLI accepts overrides:

```bash
gitmeup --model gemini-2.0-pro        # override model for this run only
gitmeup --api-key "your-key-here"     # override key (not recommended; leaks to history!)
```

For security, prefer `~/.gitmeup.env` or environment variables over `--api-key`.

---

## Usage

From any git repository with uncommitted changes:

```bash
gitmeup
```

This:

* Ensures you are inside a git repo.
* Checks `git status --porcelain`.
* If there are changes, sends context to the model and prints **proposed commands**.

### Dry run (default)

```bash
gitmeup
```

Example output:

```bash
Proposed commands:

git add -- gitmeup/stuff.py README.md
git commit -m 'docs: Update README with export for GITMEUP_MODEL'

Dry run: not executing commands. Re-run with --apply to execute.
```

Nothing is executed until you explicitly ask.

### Apply mode

To actually run the proposed `git add` and `git commit` commands:

```bash
gitmeup --apply
```

`gitmeup` will:

* Print each command as it executes.
* Stop on the first failure and exit with a non-zero status.
* Finally show a concise status:

```bash
Final git status:

## main...origin/main
 M some/file
?? other/file

Review your history with:
  git log --oneline --graph --decorate -n 10
```

---

## Examples

Basic flow, with everything configured via env / `.env`:

```bash
# inside a repo with changes
gitmeup          # review suggested batches
gitmeup --apply  # once you are happy with the plan
git log --oneline --graph --decorate -n 10
```

Override model just for this run:

```bash
gitmeup --model gemini-2.0-flash-lite
```

---

## Behaviour

* **No pushing**: `gitmeup` never outputs `git push` or remote commands.
* **No invented files**: it only operates on files present in `git status` / `git diff`.
* **Strict quoting**: paths containing spaces, brackets, unicode, etc. are double-quoted; safe paths are not over-quoted.
* **Atomic commits**: model is instructed to group changes into small, semantic batches (e.g. `refactor`, `docs`, `assets`), rather than one huge “misc” commit.

You still review and decide when to run `--apply`.

---

## License

MIT License. See [`LICENSE`](./LICENSE) for details.

---

## Maintainer

Created and maintained by [@ikramagix](https://github.com/ikramagix).