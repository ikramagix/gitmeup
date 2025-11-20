import argparse
import os
import shlex
import subprocess
import sys
from textwrap import dedent

from openai import OpenAI  # installed via pyproject dependencies


SYSTEM_PROMPT = dedent("""
You are a Conventional Commits writer. You generate precise commit messages that follow Conventional Commits 1.0.0:

<type>[optional scope]: <description>

Valid types include: feat, fix, chore, docs, style, refactor, perf, test, ci, revert.
Use "!" or a BREAKING CHANGE footer for breaking changes.
Avoid non-standard types.
Suggest splitting changes into multiple commits when appropriate and reflect that by outputting multiple git commit commands.

You receive:
- A `git diff --stat` output
- A `git status` output
- A `git diff` output where binary/image formats may have been excluded from the diff body

RULES FOR DECIDING COMMITS:
- Keep each commit atomic and semantically focused (for example: feature, refactor, docs, locales, tests, CI, assets).
- Never invent files. Operate only on files that appear in the provided git status or diff.
- Respect staged vs unstaged when that information is present. If unclear, assume everything is unstaged and must be added.
- If the changes are too heterogeneous, split them into multiple commits and multiple batches.

STRICT PATH QUOTING (MANDATORY):
You output git commands that the user will paste directly in a POSIX shell.

For every path in git add/rm/mv:
- Determine deterministically if quoting is required.
- Quote the path with double quotes ONLY IF it contains characters outside the safe set `[A-Za-z0-9._/\\-]`.
- ALWAYS quote paths containing: space, tab, (, ), [, ], {, }, &, |, ;, *, ?, !, ~, $, `, ', ", <, >, #, %, or any non-ASCII character.
- Never quote safe paths unnecessarily.
- Do not invent or “fix” paths. Use exactly the paths you see, correctly quoted.

COMMAND GROUPING AND ORDER:
- Group files into small, meaningful batches.
- For each batch:
  - First output one or more git add/rm/mv commands.
  - Immediately after those, output one git commit -m "type[optional scope]: description" command for that batch.
- Ensure overall command order is valid: all add/rm/mv before their corresponding commit.
- Do not include git push or any remote-related commands.

OUTPUT FORMAT (VERY IMPORTANT):
- Respond with ONE fenced code block, with language "bash".
- Inside that block, output ONLY executable commands, one per line.
- No prose, no comments, no blank lines at the start or end.
- You MAY separate batches with a single blank line between them, but not at the very top or bottom of the block.
- Do NOT output any text outside this single bash code block.

STYLE OF COMMIT MESSAGES:
- Descriptions are short, imperative, and specific (e.g. "update DTO proposal section copy").
- Keep type consistent with the dominant kind of change in the batch.
""")


def run_git(args, check=True):
    """Run a git command and return stdout."""
    proc = subprocess.run(
        ["git"] + list(args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if check and proc.returncode != 0:
        print(f"Error running git {' '.join(args)}:\n{proc.stderr}", file=sys.stderr)
        sys.exit(proc.returncode)
    return proc.stdout


def ensure_repo():
    out = run_git(["rev-parse", "--is-inside-work-tree"])
    if out.strip() != "true":
        print("gitmeup must be run inside a git repository.", file=sys.stderr)
        sys.exit(1)


def collect_context():
    # 1) Summary of changes including images
    diff_stat = run_git(["diff", "--stat"])
    # 2) Status
    status = run_git(["status", "--short"])
    # 3) Detailed diff excluding noisy binary/image formats from body
    diff_args = [
        "diff",
        "--",
        ".",
        ":(exclude)*.png",
        ":(exclude)*.jpg",
        ":(exclude)*.jpeg",
        ":(exclude)*.gif",
        ":(exclude)*.svg",
        ":(exclude)*.webp",
    ]
    diff = run_git(diff_args)
    return diff_stat, status, diff


def build_user_prompt(diff_stat, status, diff):
    return dedent(f"""
    Here are the current git changes.

    === git diff --stat ===
    {diff_stat or "(no diff stat output)"}

    === git status --short ===
    {status or "(no status output)"}

    === git diff (images excluded) ===
    {diff or "(no diff output)"}

    Based on this, generate atomic Conventional Commits and matching git add/rm/mv + git commit commands as instructed.
    """)


def call_llm(model, api_key, user_prompt):
    client = OpenAI(api_key=api_key)
    resp = client.responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=user_prompt,
        temperature=0,
    )
    # The Python SDK exposes a convenience property to join textual parts
    return resp.output_text  # type: ignore[attr-defined]


def extract_bash_block(text):
    """Extract first ```bash ... ``` block. Return its inner content."""
    in_block = False
    lang_ok = False
    lines = []

    for line in text.splitlines():
        if line.startswith("```"):
            fence = line.strip()
            if not in_block:
                lang = fence[3:].strip()
                lang_ok = (lang == "" or lang.lower() in {"bash", "sh", "shell"})
                in_block = True
                continue
            else:
                # closing fence
                break
        elif in_block and lang_ok:
            lines.append(line)

    return "\n".join(lines).strip()


def parse_commands(cmd_block):
    """Split the bash block into individual git commands."""
    cmds = []
    for line in cmd_block.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if not line.startswith("git "):
            continue
        cmds.append(line)
    return cmds


def run_commands(commands, apply):
    if not commands:
        print("gitmeup: no git commands produced by the model.")
        return

    print("gitmeup proposed commands:\n")
    for cmd in commands:
        print(cmd)
    print()

    if not apply:
        print("Dry run. Re-run with --apply to execute these commands.")
        return

    print("Executing commands...")
    for cmd in commands:
        print(f"> {cmd}")
        try:
            subprocess.run(shlex.split(cmd), check=True)
        except subprocess.CalledProcessError as e:
            print(f"Command failed with exit code {e.returncode}. Aborting.", file=sys.stderr)
            sys.exit(e.returncode)

    print("\nCommands executed.\n")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="gitmeup",
        description="Generate Conventional Commits from current git changes using an LLM.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("GITMEUP_MODEL", "gpt-4.1-mini"),
        help="OpenAI model name (default: gpt-4.1-mini or $GITMEUP_MODEL).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute generated git commands. Without this flag, just print them.",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("OPENAI_API_KEY"),
        help="OpenAI API key (default: $OPENAI_API_KEY).",
    )

    args = parser.parse_args(argv)

    if not args.api_key:
        print("Missing OpenAI API key. Set OPENAI_API_KEY or use --api-key.", file=sys.stderr)
        sys.exit(1)

    ensure_repo()

    porcelain = run_git(["status", "--porcelain"])
    if porcelain.strip() == "":
        print("Working tree clean. Nothing to commit.")
        sys.exit(0)

    diff_stat, status, diff = collect_context()
    user_prompt = build_user_prompt(diff_stat, status, diff)

    raw_output = call_llm(args.model, args.api_key, user_prompt)
    bash_block = extract_bash_block(raw_output)

    if not bash_block:
        print("gitmeup: failed to extract bash command block from model output.", file=sys.stderr)
        print("Raw output:\n", raw_output)
        sys.exit(1)

    commands = parse_commands(bash_block)
    run_commands(commands, apply=args.apply)

    print("\nFinal git status:\n")
    print(run_git(["status", "-sb"], check=False))

    print("Review your history with:")
    print("  git log --oneline --graph --decorate -n 10")
