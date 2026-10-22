# ccache

[ccache](https://ccache.dev) is a compiler cache. It speeds up recompilation by
caching previous compilations and detecting when the same compilation is being
done again. It supports GCC, Clang, MSVC and other compilers.

This package installs the official ccache {version} binaries into your Python
environment, so you can get ccache with `pip` or `uv` on Linux, macOS and Windows:

```bash
pip install ccache            # or: uv tool install ccache
ccache --version
```

The `ccache` executable lands in the environment's `bin/` directory
(`Scripts\` on Windows). It is the upstream binary itself, not a Python
wrapper, so it starts as fast as a system install.

## Use it

With CMake:

```bash
cmake -B build -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache
```

Or prefix the compiler directly, for example `ccache gcc -c foo.c`. See the
[ccache manual](https://ccache.dev/manual/latest.html) for configuration,
remote storage and the other ways to run it.

## Platforms

| Platform | Wheel |
| --- | --- |
| Linux x86_64, aarch64, riscv64, s390x (glibc 2.17+ and musl) | upstream static build |
| macOS 10.15+ (x86_64) and 11.0+ (Apple Silicon) | upstream universal build |
| Windows x86_64 | upstream build |

Other platforms have no upstream binary yet, so there is no wheel for them.

## About this package

This is an unofficial package, maintained by [cpp-linter](https://github.com/cpp-linter)
in [cpp-linter/ccache-wheel](https://github.com/cpp-linter/ccache-wheel). The
wheels contain the binaries from the
[ccache {version} release](https://github.com/ccache/ccache/releases/tag/v{version})
unchanged; each download is checked against the ccache release signing key
before packaging. Wheel versions follow ccache versions; a `.postN` suffix
marks a packaging-only fix.

Report problems with the package in
[cpp-linter/ccache-wheel](https://github.com/cpp-linter/ccache-wheel/issues),
and problems with ccache itself [upstream](https://github.com/ccache/ccache/issues).

## License

ccache is free software under the GNU General Public License, version 3 or
later. The wheels include the license and the upstream `LICENSE.md` with the
notices of bundled third-party code. The corresponding source code
(`ccache-{version}.tar.gz` and its signature) is attached to the
[{wheel_version} release](https://github.com/cpp-linter/ccache-wheel/releases/tag/v{wheel_version})
of this package and is also available from [ccache.dev](https://ccache.dev/download.html).
