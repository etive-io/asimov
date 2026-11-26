#!/usr/bin/env python3
"""
Run the tutorials which work on a single computer, exactly as they are written.

The pages are run one after another in the same shell, in a new directory, so
a page may carry on from the one before it. From each page:

* ``bash`` and ``console`` code blocks are run: each line starting with ``$``;
* a code block with a ``:caption:`` is written to the file it names;
* a ``text`` code block is the output which the page shows: each of its lines
  must appear, in order, in the output of the commands just before it.

A command which fails, or which prints a Python traceback, fails the run. A
comment on the line before a code block changes this:

``.. tutorial-test: may-fail``
    The block shows something going wrong, so its commands may fail or print a
    traceback. The output the page shows is still checked.
``.. tutorial-test: skip``
    The block is not run.

The commands which create an environment and install asimov are not run:
install the version to be tested first, and have it on the ``PATH``.

Usage: python scripts/run_tutorials.py [page.rst ...]
"""

import argparse
import re
import shlex
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs" / "source"
DEFAULT_PAGES = [
    DOCS / "getting-started.rst",
    DOCS / "tutorials" / "adding-a-pipeline.rst",
    DOCS / "tutorials" / "when-something-goes-wrong.rst",
    DOCS / "tutorials" / "scaling-up.rst",
    DOCS / "tutorials" / "results-to-release.rst",
]

#: Commands which set up the environment the tutorials are tested in.
ENVIRONMENT_COMMANDS = re.compile(
    r"^(python3? -m venv |source \S*activate|pip install [\"']asimov)"
)

MARKER = ".. tutorial-test:"
SKIP, MAY_FAIL = "skip", "may-fail"

DIRECTIVE = re.compile(r"^(\s*)\.\.\s+code-block\s*::\s*(\S+)\s*$")


def blocks(path):
    """
    The code blocks of a page, as ``(line number, language, caption, text,
    marker)``, where the marker is None unless the page gives one.
    """
    lines = path.read_text().split("\n")
    index = 0
    previous = ""
    while index < len(lines):
        match = DIRECTIVE.match(lines[index])
        if not match:
            previous = lines[index].strip() or previous
            index += 1
            continue
        number = index + 1
        indent, language = len(match.group(1)), match.group(2)
        index += 1
        caption = None
        while index < len(lines) and lines[index].strip().startswith(":"):
            option = lines[index].strip()
            if option.startswith(":caption:"):
                caption = option[len(":caption:"):].strip()
            index += 1
        body = []
        while index < len(lines) and (
            not lines[index].strip()
            or len(lines[index]) - len(lines[index].lstrip()) > indent
        ):
            body.append(lines[index])
            index += 1
        marker = previous[len(MARKER):].strip() if previous.startswith(MARKER) else None
        if marker not in (None, SKIP, MAY_FAIL):
            raise ValueError(f"{path.name}:{number}: unknown marker '{marker}'")
        if marker != SKIP:
            text = textwrap.dedent("\n".join(body)).strip("\n")
            yield number, language, caption, text, marker
        previous = ""


def build_script(pages, outputs):
    """
    A shell script which runs the pages, and the checks to make afterwards.

    Returns
    -------
    tuple
        The script, and a list of ``(where, output file, expected text)``,
        where the expected text is None for a check that the commands printed
        no traceback.
    """
    script = ["set -eo pipefail"]
    checks = []
    last_output = None
    count = 0
    for page in pages:
        last_output = None
        for number, language, caption, text, marker in blocks(page):
            where = f"{page.name}:{number}"
            if caption:
                if "TUTORIAL_EOF" in text:
                    raise ValueError(f"{where}: cannot write a file containing TUTORIAL_EOF")
                parent = shlex.quote(str(Path(caption).parent))
                script += [
                    f"mkdir -p {parent}",
                    f"cat > {shlex.quote(caption)} <<'TUTORIAL_EOF'",
                    text,
                    "TUTORIAL_EOF",
                ]
            elif language in ("bash", "console"):
                commands = []
                for line in text.split("\n"):
                    if not line.strip():
                        continue
                    if not line.startswith("$ "):
                        raise ValueError(f"{where}: expected a command starting with '$ ': {line}")
                    if not ENVIRONMENT_COMMANDS.match(line[2:]):
                        commands.append(line[2:])
                if not commands:
                    continue
                count += 1
                last_output = outputs / f"{count:03d}.log"
                may_fail = marker == MAY_FAIL
                script += [
                    f"echo {shlex.quote(where)}",
                    f"echo {shlex.quote(str(last_output))} > {shlex.quote(str(outputs / 'current'))}",
                    *(["set +e"] if may_fail else []),
                    # Braces, not a subshell: `cd` and `export` must last.
                    "{",
                    *commands,
                    f"}} > {shlex.quote(str(last_output))} 2>&1",
                    *(["set -e"] if may_fail else []),
                ]
                if not may_fail:
                    checks.append((where, last_output, None))
            elif language == "text":
                if last_output is None:
                    raise ValueError(f"{where}: output shown before any command")
                checks.append((where, last_output, text))
            else:
                raise ValueError(
                    f"{where}: a {language} block needs a :caption: naming its file, "
                    f"or '{MARKER} {SKIP}' before it"
                )
    return "\n".join(script) + "\n", checks


def normalise(line):
    return " ".join(line.split())


def missing_line(expected, actual):
    """The first line of ``expected`` not found, in order, in ``actual``."""
    remaining = iter(normalise(line) for line in actual.split("\n"))
    for line in filter(None, (normalise(line) for line in expected.split("\n"))):
        if not any(line in candidate for candidate in remaining):
            return line
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("pages", nargs="*", type=Path, default=DEFAULT_PAGES)
    parser.add_argument("--timeout", type=int, default=600, help="seconds for the whole run")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        outputs, work = root / "outputs", root / "work"
        outputs.mkdir()
        work.mkdir()
        script, checks = build_script([page.resolve() for page in args.pages], outputs)
        (root / "tutorial.sh").write_text(script)

        result = subprocess.run(
            ["bash", str(root / "tutorial.sh")], cwd=work, timeout=args.timeout
        )
        if result.returncode != 0:
            current = outputs / "current"
            if current.exists():
                print(Path(current.read_text().strip()).read_text())
            print(f"FAILED: a command exited with status {result.returncode} (see above)")
            return 1

        failures = []
        for where, output, expected in checks:
            actual = output.read_text()
            if expected is None:
                if "Traceback (most recent call last)" in actual:
                    failures.append(f"{where}: printed a traceback:\n{actual}")
            else:
                line = missing_line(expected, actual)
                if line is not None:
                    failures.append(
                        f"{where}: the output does not contain {line!r}. It was:\n{actual}"
                    )
    if failures:
        print("\n".join(failures))
        print(f"FAILED: {len(failures)} problem(s)")
        return 1
    print(f"OK: ran {len(args.pages)} page(s), {len(checks)} checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
