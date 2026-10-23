# Contributing

Thanks for your interest in contributing to `ccache-wheel`! Open an
[issue](https://github.com/cpp-linter/ccache-wheel/issues), start a discussion in
[cpp-linter Discussions](https://github.com/orgs/cpp-linter/discussions), or submit a pull
request.

## Setup

```bash
git clone https://github.com/cpp-linter/ccache-wheel.git
cd ccache-wheel
python -m pip install --group dev   # pip 25.1 or later
pre-commit install
```

## Building the wheels

The wheels are built with [hatchling](https://hatch.pypa.io/latest/) from `pyproject.toml`. The
build hooks in `hatch_build.py` download the upstream ccache archive for one platform, check its
minisign signature against the ccache release key
(`RWQX7yXbBedVfI4PNx6FLdFXu9GHUFsr28s4BVGxm4BeybtnX3P06saF`, from
[ccache.dev](https://ccache.dev/download.html)) and the binary's format, and put the binary, its
man page and the license files into the wheel. The version comes from `ccache_version.txt`.

```bash
python -m build --wheel                                  # for this machine
CCACHE_PLATFORM=windows-x86_64 python -m build --wheel   # for another platform
python hatch_build.py platforms                          # list the platforms
python hatch_build.py source release                     # ccache source code for a release
```

`pip install .` builds and installs the wheel for this machine. The same input always gives the
same wheels.

## Running Tests

```bash
python -m venv .venv
.venv/bin/python -m pip install --no-index --find-links dist ccache-bin
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python tests/smoke_test.py --version "$(cat ccache_version.txt)"
```

The test checks that `ccache` comes from the environment, reports the right version, and that a
second compile of the same file is a cache hit. CI runs it with pip and uv on Linux, macOS and
Windows, and in Alpine, manylinux2014 and QEMU (riscv64, s390x) containers.

## Code Style

We use [ruff](https://docs.astral.sh/ruff/) for linting and formatting, through pre-commit:

```bash
pre-commit run --all-files
```

## Releasing

1. When ccache has a new release, a daily workflow opens an issue.
2. Open a PR titled `feat: update ccache to <version>` that sets `ccache_version.txt` to the new
   version. PR titles follow [Conventional Commits](https://www.conventionalcommits.org/).
3. After the merge, Release Drafter drafts the `v<version>` release. The version always comes from
   `ccache_version.txt`.
4. Optional: run the **Upload Python Package** workflow on `main` to upload the wheels to TestPyPI.
5. Publish the draft release. The workflow tests the wheels again, attaches them and the ccache
   source archive to the release, adds build provenance attestations, and uploads the wheels to
   PyPI with trusted publishing.
