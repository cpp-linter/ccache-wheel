"""Check an installed ccache wheel the way a user would use it.

Run it with the Python of the environment the wheel was installed into:

    python tests/smoke_test.py --version 4.14.2 [--compiler cc]

It checks that `ccache` on PATH is the binary from this environment, that it
reports the expected version, and that compiling the same file twice gives
one cache miss and then one cache hit.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

WINDOWS = sys.platform == "win32"


def run(*cmd: str, cwd: Path | None = None, env: dict | None = None) -> str:
    print("+", " ".join(cmd), flush=True)
    result = subprocess.run(
        cmd, cwd=cwd, env=env, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        print(result.stdout, result.stderr, sep="\n")
        raise SystemExit(f"command failed with exit code {result.returncode}")
    return result.stdout


def stats(ccache: str, env: dict) -> dict[str, int]:
    out = run(ccache, "--print-stats", env=env)
    values = {}
    for line in out.splitlines():
        key, _, value = line.partition("\t")
        if value.strip().isdigit():
            values[key] = int(value)
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True, help="wheel or ccache version")
    parser.add_argument("--compiler", default="cl" if WINDOWS else "cc")
    args = parser.parse_args()

    scripts = Path(sysconfig.get_path("scripts"))
    expected = scripts / ("ccache.exe" if WINDOWS else "ccache")
    found = shutil.which("ccache", path=str(scripts) + os.pathsep + os.environ["PATH"])
    if (
        not expected.is_file()
        or found is None
        or Path(found).resolve() != expected.resolve()
    ):
        raise SystemExit(f"ccache is not installed in {scripts} (found {found})")
    ccache = str(expected)

    first_line = run(ccache, "--version").splitlines()[0]
    print(first_line)
    # A .postN wheel ships the same ccache version.
    expected_version = args.version.split(".post")[0]
    if first_line != f"ccache version {expected_version}":
        raise SystemExit(f"expected ccache {expected_version}, got {first_line!r}")

    if not WINDOWS:
        man = Path(sysconfig.get_path("data")) / "share" / "man" / "man1" / "ccache.1"
        if not man.is_file():
            raise SystemExit(f"man page missing: {man}")

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / "hello.c").write_text(
            '#include <stdio.h>\nint main(void) { puts("hi"); return 0; }\n'
        )
        env = dict(os.environ, CCACHE_DIR=str(work / "cache"))
        if WINDOWS:
            compile_cmd = [
                ccache,
                args.compiler,
                "/nologo",
                "/c",
                "hello.c",
                "/Fohello.obj",
            ]
        else:
            compile_cmd = [ccache, args.compiler, "-c", "hello.c", "-o", "hello.o"]

        run(ccache, "--zero-stats", env=env)
        run(*compile_cmd, cwd=work, env=env)
        run(*compile_cmd, cwd=work, env=env)
        values = stats(ccache, env)
        hits = values.get("direct_cache_hit", 0) + values.get(
            "preprocessed_cache_hit", 0
        )
        misses = values.get("cache_miss", 0)
        print(f"hits={hits} misses={misses}")
        if hits != 1 or misses != 1:
            print(run(ccache, "--show-stats", "-v", env=env))
            raise SystemExit("expected one cache miss followed by one cache hit")

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
