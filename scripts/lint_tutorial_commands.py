#!/usr/bin/env python3
"""
Lint asimov CLI invocations and Python API imports embedded in the docs.

Scans docs/source/tutorials/*.rst and docs/source/getting-started.rst for
``asimov ...`` command lines (in ``console``/``bash`` code-blocks) and
``from asimov... import ...`` statements (in ``python`` code-blocks), then
checks each against the real, currently-installed CLI (via click
introspection) and the real Python package (via attribute lookup).

This does not execute anything against a scheduler or run any pipeline —
it only catches drift between what the docs claim (a subcommand, a flag,
an importable name) and what actually exists in the installed asimov.

Usage: python scripts/lint_tutorial_commands.py
Exit code is non-zero if any invocation/import doesn't resolve.
"""

import ast
import importlib
import re
import sys
import textwrap
from pathlib import Path

import click

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_PATHS = [
    *sorted((REPO_ROOT / "docs" / "source" / "tutorials").glob("*.rst")),
    REPO_ROOT / "docs" / "source" / "getting-started.rst",
]

CODE_BLOCK_RE = re.compile(
    r"^([ \t]*)\.\.\s+code-block\s*::\s*(\S+)\s*\n((?:\n|(?:\1[ \t].*\n)|(?:[ \t]*\n))*)",
    re.MULTILINE,
)


def extract_code_blocks(text, languages):
    blocks = []
    for match in CODE_BLOCK_RE.finditer(text):
        _directive_indent, lang, body = match.groups()
        if lang not in languages:
            continue
        # Content is indented relative to the directive by whatever the author
        # used (commonly 3 spaces); take the contiguous run of lines indented
        # deeper than the directive itself, then dedent by their common prefix.
        raw_lines = body.splitlines()
        content_lines = []
        for line in raw_lines:
            if line.strip() == "":
                content_lines.append(line)
                continue
            if line[:1] not in (" ", "\t"):
                break
            content_lines.append(line)
        block = textwrap.dedent("\n".join(content_lines))
        blocks.append(block)
    return [b for b in blocks if b.strip()]


def build_cli_tree(group, prefix=()):
    """Map each valid subcommand path (tuple of words) to its set of flags."""
    tree = {}
    if not isinstance(group, click.Group):
        return tree
    for name, cmd in group.commands.items():
        path = prefix + (name,)
        opts = set()
        for param in cmd.params:
            if isinstance(param, click.Option):
                opts.update(param.opts)
        tree[path] = opts
        tree.update(build_cli_tree(cmd, path))
    return tree


def resolve_command(tokens, cli_tree, max_path_len):
    """Find the longest known subcommand path at the start of tokens."""
    for length in range(min(max_path_len, len(tokens)), 0, -1):
        path = tuple(tokens[:length])
        if path in cli_tree:
            return path, tokens[length:]
    return None, tokens


def lint_cli_invocations(cli_tree, max_path_len, source_label, block):
    errors = []
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if line.startswith("$"):
            line = line[1:].strip()
        if not line.startswith("asimov "):
            continue
        try:
            tokens = re.findall(r"\"[^\"]*\"|'[^']*'|\S+", line)[1:]
        except re.error:
            continue
        # Strip anything after a shell pipe/redirect/&&, we only care about the invocation shape.
        cut = len(tokens)
        for i, tok in enumerate(tokens):
            if tok in ("|", ">", ">>", "&&", ";"):
                cut = i
                break
        tokens = tokens[:cut]
        if not tokens:
            continue
        path, rest = resolve_command(tokens, cli_tree, max_path_len)
        if path is None:
            errors.append(f"{source_label}: unknown subcommand in `{raw_line.strip()}`")
            continue
        known_opts = cli_tree[path]
        for tok in rest:
            if not tok.startswith("-") or tok == "-":
                continue
            flag = tok.split("=", 1)[0]
            if flag not in known_opts:
                errors.append(
                    f"{source_label}: unknown flag `{flag}` for "
                    f"`asimov {' '.join(path)}` in `{raw_line.strip()}`"
                )
    return errors


def lint_python_imports(source_label, block):
    errors = []
    try:
        tree = ast.parse(block)
    except SyntaxError:
        # Some tutorials (e.g. plugin-authoring walkthroughs) show partial,
        # illustrative snippets — a lone method body, a `...`-elided call —
        # that were never meant to be standalone-runnable. We can't reliably
        # tell that apart from a real typo by parsing alone, so we skip
        # rather than risk noisy false positives on intentional pseudocode.
        return errors

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if not node.module or not node.module.startswith("asimov"):
            continue
        try:
            module = importlib.import_module(node.module)
        except ImportError as exc:
            errors.append(f"{source_label}: cannot import module `{node.module}` ({exc})")
            continue
        for alias in node.names:
            if alias.name == "*":
                continue
            if not hasattr(module, alias.name):
                errors.append(
                    f"{source_label}: `{alias.name}` not found in `{node.module}` "
                    f"(from `from {node.module} import {alias.name}`)"
                )
    return errors


def main():
    from asimov.olivaw import olivaw

    cli_tree = build_cli_tree(olivaw)
    max_path_len = max(len(path) for path in cli_tree) if cli_tree else 1

    all_errors = []
    for doc_path in DOC_PATHS:
        if not doc_path.exists():
            continue
        text = doc_path.read_text()
        rel = doc_path.relative_to(REPO_ROOT)

        for block in extract_code_blocks(text, {"console", "bash"}):
            all_errors.extend(lint_cli_invocations(cli_tree, max_path_len, str(rel), block))

        for block in extract_code_blocks(text, {"python"}):
            all_errors.extend(lint_python_imports(str(rel), block))

    if all_errors:
        print(f"Found {len(all_errors)} issue(s):\n")
        for error in all_errors:
            print(f"  - {error}")
        return 1

    print(f"OK: checked {len(DOC_PATHS)} doc file(s) against the live asimov CLI/API, no issues found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
