# ccache-wheel

[![PyPI](https://img.shields.io/pypi/v/ccache-bin?labelColor=454a63&color=007ec6)](https://pypi.org/project/ccache-bin/)
[![ci](https://img.shields.io/github/actions/workflow/status/cpp-linter/ccache-wheel/test.yml?branch=main&label=ci&labelColor=454a63)](https://github.com/cpp-linter/ccache-wheel/actions/workflows/test.yml)
[![part of cpp-linter](https://img.shields.io/badge/part%20of-cpp--linter-ffc20a?labelColor=454a63)](https://cpp-linter.github.io/)

[ccache](https://ccache.dev), the C/C++ compiler cache, as Python wheels on PyPI
(`ccache-bin`). The wheels contain the official ccache binaries, unchanged, and install the
`ccache` command.

[Website](https://cpp-linter.github.io/) ·
[PyPI](https://pypi.org/project/ccache-bin/) ·
[ccache manual](https://ccache.dev/manual/latest.html) ·
[Discussions](https://github.com/orgs/cpp-linter/discussions)

## Quick start

```bash
pip install ccache-bin        # or: uv tool install ccache-bin
ccache --version
```

The package is called `ccache-bin` because the name `ccache` is not available on PyPI. The
command it installs is still `ccache` (with uvx: `uvx --from ccache-bin ccache --version`).

## Usage

With CMake:

```bash
cmake -B build -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache
```

Or put `ccache` in front of the compiler:

```bash
ccache gcc -c hello.c -o hello.o
```

`ccache` is installed straight into the environment's `bin/` (`Scripts\` on Windows), with no
Python wrapper in between. A cached compile took about 3 ms with the binary and about 18 ms
through a Python wrapper. See the [ccache manual](https://ccache.dev/manual/latest.html) for
configuration and remote storage.

## Supported platforms

| Platform | Architecture | Wheel tag |
|----------|-------------|-----------|
| **macOS** 10.15+ / 11.0+ | Intel (x86_64) and Apple Silicon (arm64) | `macosx_10_15_x86_64.macosx_11_0_arm64.macosx_10_15_universal2` |
| **Linux** (glibc 2.17+ and musl) | x86_64 | `manylinux_2_17_x86_64.manylinux2014_x86_64.musllinux_1_1_x86_64` |
| **Linux** (glibc 2.17+ and musl) | aarch64 | `manylinux_2_17_aarch64.manylinux2014_aarch64.musllinux_1_1_aarch64` |
| **Linux** (glibc 2.31+ and musl) | riscv64 | `manylinux_2_31_riscv64.musllinux_1_1_riscv64` |
| **Linux** (glibc 2.17+ and musl) | s390x | `manylinux_2_17_s390x.manylinux2014_s390x.musllinux_1_1_s390x` |
| **Windows** | 64-bit | `win_amd64` |

The Linux wheels use the upstream static musl builds, so one wheel works on both glibc and musl
distributions. Upstream has no binaries for Windows ARM64, 32-bit Windows or other Linux
architectures, so there are no wheels for them.

The wheel version is the ccache version, for example `4.14.2`. A packaging-only fix is released
as `4.14.2.post1`.

## Acknowledgements

[ccache](https://github.com/ccache/ccache) is written by Joel Rosdahl and the ccache
contributors. The wheels contain the binaries from the
[ccache releases](https://github.com/ccache/ccache/releases): each archive is checked against
the ccache release signing key before it is packaged. This is not an official ccache project, so
report problems with ccache itself [upstream](https://github.com/ccache/ccache/issues).

## Contributing

See the [contributing guide](https://github.com/cpp-linter/ccache-wheel/blob/main/CONTRIBUTING.md)
and [open an issue](https://github.com/cpp-linter/ccache-wheel/issues) for packaging bugs and
feature requests.

## License

The build scripts and workflows in this repository are released under the
[MIT License](https://github.com/cpp-linter/ccache-wheel/blob/main/LICENSE). ccache, and so the
wheels, are under the [GNU General Public License v3.0 or later](https://ccache.dev/license.html):
the wheels carry its license files, and every
[release](https://github.com/cpp-linter/ccache-wheel/releases) of this repository includes the
matching ccache source archive and its signature.
