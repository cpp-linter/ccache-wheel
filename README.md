# ccache-wheel

[![PyPI](https://img.shields.io/pypi/v/ccache?labelColor=454a63&color=007ec6)](https://pypi.org/project/ccache/)
[![ci](https://img.shields.io/github/actions/workflow/status/cpp-linter/ccache-wheel/release.yml?branch=main&label=ci&labelColor=454a63)](https://github.com/cpp-linter/ccache-wheel/actions/workflows/release.yml)
[![part of cpp-linter](https://img.shields.io/badge/part%20of-cpp--linter-ffc20a?labelColor=454a63)](https://cpp-linter.github.io/)

[ccache](https://ccache.dev), the C/C++ compiler cache, as Python wheels on PyPI. The wheels
contain the official ccache binaries, unchanged.

[Website](https://cpp-linter.github.io/) ·
[ccache documentation](https://ccache.dev/documentation.html) ·
[Discussions](https://github.com/orgs/cpp-linter/discussions)

## Quick start

```bash
pip install ccache            # or: uv tool install ccache
ccache --version
```

Use it with CMake:

```bash
cmake -B build -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache
```

`ccache` is installed straight into the environment's `bin/` (`Scripts\` on Windows). There is
no Python entry point in between: a cached compile through a Python wrapper took about 18 ms,
the binary alone about 3 ms.

## Supported platforms

| Platform | Upstream archive | Wheel tag |
| --- | --- | --- |
| macOS x86_64 (10.15+) and arm64 (11.0+) | `darwin` (universal) | `macosx_10_15_x86_64.macosx_11_0_arm64.macosx_10_15_universal2` |
| Linux x86_64 | `linux-x86_64-musl-static` | `manylinux_2_17_x86_64.manylinux2014_x86_64.musllinux_1_1_x86_64` |
| Linux aarch64 | `linux-aarch64-musl-static` | `manylinux_2_17_aarch64.manylinux2014_aarch64.musllinux_1_1_aarch64` |
| Linux riscv64 | `linux-riscv64-musl-static` | `manylinux_2_17_riscv64.musllinux_1_1_riscv64` |
| Linux s390x | `linux-s390x-musl-static` | `manylinux_2_17_s390x.manylinux2014_s390x.musllinux_1_1_s390x` |
| Windows x86_64 | `windows-x86_64` | `win_amd64` |

The Linux wheels use the static musl builds, so one wheel works on glibc distributions back to
glibc 2.17 and on Alpine. Upstream has no binaries for Windows ARM64, 32-bit Windows or other
Linux architectures, so there are no wheels for them.

## How the wheels are made

[`build_wheels.py`](build_wheels.py) downloads each upstream archive from the
[ccache release](https://github.com/ccache/ccache/releases), checks its signature against the
ccache release key (minisign key `RWQX7yXbBedVfI4PNx6FLdFXu9GHUFsr28s4BVGxm4BeybtnX3P06saF`
from [ccache.dev](https://ccache.dev/download.html)) and the binary's format, and writes the
wheel. The same input always gives the same wheel.

```bash
python -m pip install -r requirements.txt
python build_wheels.py   # wheels in dist/, ccache source archive in release/
```

CI installs every wheel with pip and uv on Linux (x86_64, aarch64, Alpine, manylinux2014, and
riscv64 and s390x under QEMU), macOS (Intel and Apple Silicon) and Windows (MSVC), and checks
that a second compile of the same file is a cache hit.

## Versions and releases

The wheel version is the ccache version in [`ccache_version.txt`](ccache_version.txt), for
example `4.14.2`. A packaging-only fix is released as `4.14.2.post1`. Files on PyPI are never
replaced.

1. A daily workflow opens an issue when ccache has a new release.
2. A PR titled `feat: update ccache to <version>` updates `ccache_version.txt`; its CI tests
   the new wheels. Merged PRs upload the wheels to TestPyPI, and Release Drafter drafts the
   `v<version>` release.
3. Publishing the draft release uploads the wheels to PyPI with trusted publishing, attaches the
   wheels and the ccache source archive to the release, and adds build provenance attestations.

## Contributing

See the [contributing guide](CONTRIBUTING.md). Report packaging problems in
[this repository](https://github.com/cpp-linter/ccache-wheel/issues) and problems with ccache
itself [upstream](https://github.com/ccache/ccache/issues). This is not an official ccache
project.

## License

ccache is under the [GNU General Public License v3.0 or later](https://ccache.dev/license.html).
The wheels carry its license and the upstream `LICENSE.md`, and every release of this repository
includes the matching ccache source archive. The scripts and workflows in this repository are
under the [MIT License](LICENSE).
