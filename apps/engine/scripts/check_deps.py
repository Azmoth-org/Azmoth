#!/usr/bin/env python3
"""Refuse to start when the image's packages are older than the mounted source.

`docker-compose.yml` bind-mounts `apps/engine/app` over the image's own copy, so the container
runs whatever is in the working tree — but its site-packages are whatever `pip install` put there
when the image was last built. Add a dependency, and `docker compose up` (without `--build`)
starts a container whose code imports a package it does not have.

That failure is bad out of proportion to its cause: uvicorn's reloader catches the
ModuleNotFoundError, prints forty lines of traceback, respawns, and fails again — so the container
never exits, `docker ps` reports `Up (unhealthy)` rather than a crash, and the actual missing name
is buried in the middle of a repeating stack trace.

This check turns that into one line naming the package and the fix. It compares the pins in
requirements.txt against what is installed; compose mounts the working tree's copy of that file
over the image's, so the comparison is host-declared against image-installed. Unmounted (a plain
`docker run`) it compares the baked file against the packages installed from it, which passes for
free.

Only `==` pins are checked, which is all this file uses, and only the distribution version — not
extras, which are not recorded in a way that can be read back. Exit 0 if everything matches, 1 if
anything is missing or at the wrong version.

Set CHECK_DEPS=false to skip.
"""

from __future__ import annotations

import re
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

REQUIREMENTS = Path(__file__).resolve().parents[1] / "requirements.txt"

#: `name[extra,extra]==version`. Anything else in the file — comments, blanks, a URL, a `>=` — is
#: deliberately skipped rather than guessed at: this check exists to catch the common case loudly,
#: not to reimplement a resolver.
PIN = re.compile(r"^\s*([A-Za-z0-9._-]+)\s*(?:\[[^\]]*\])?\s*==\s*([A-Za-z0-9._+!-]+)\s*$")


def main() -> int:
    if not REQUIREMENTS.is_file():
        print(f"check_deps: {REQUIREMENTS} not found — skipping", file=sys.stderr)
        return 0

    problems: list[str] = []
    checked = 0

    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        if not (match := PIN.match(line.split("#", 1)[0])):
            continue
        name, want = match.group(1), match.group(2)
        checked += 1
        try:
            have = version(name)
        except PackageNotFoundError:
            problems.append(f"  {name}=={want} is declared but NOT INSTALLED")
            continue
        if have != want:
            problems.append(f"  {name}: image has {have}, requirements.txt pins {want}")

    if not problems:
        return 0

    print(
        f"\ncheck_deps: the image is out of date with apps/engine/requirements.txt "
        f"({len(problems)} of {checked} pins do not match):\n"
        + "\n".join(problems)
        + "\n\nThe source is bind-mounted but the packages are not: the container is running the"
        "\nworking tree's code against an older image. Rebuild it:\n"
        "\n    docker compose -f infra/docker/docker-compose.yml up --build\n"
        "\n(Set CHECK_DEPS=false to start anyway.)\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
