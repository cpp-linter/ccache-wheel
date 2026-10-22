#!/usr/bin/env python3
"""Repackage the official ccache binary releases as Python wheels.

For each platform the script downloads the upstream archive, checks its
minisign signature against the ccache release key, checks the binary's
format, and writes a wheel that installs the binary unchanged into the
environment's bin/ (Scripts\\ on Windows) directory. No Python wrapper is
involved, so running ccache from a wheel costs the same as running the
upstream binary.

Wheels go to dist/. The upstream source archive, its signature and a
SHA256SUMS file for the wheels go to release/, so a release can ship the
corresponding source next to the binaries (GPL-3.0-or-later).

Usage:
    python build_wheels.py                          # version in ccache_version.txt
    python build_wheels.py --version 4.14.2
    python build_wheels.py --version 4.14.2.post1   # packaging-only fix of 4.14.2

Needs Python 3.9+ and the `cryptography` package (for Ed25519).
"""

from __future__ import annotations

import argparse
import base64
import calendar
import csv
import hashlib
import io
import os
import re
import struct
import sys
import tarfile
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT = Path(__file__).resolve().parent
DOWNLOAD_URL = "https://github.com/ccache/ccache/releases/download/v{version}/{name}"
# Release signing key published on https://ccache.dev/download.html
# (also https://ccache.dev/minisign.pub, key id 7C55E705DB25EF17).
MINISIGN_PUBLIC_KEY = "RWQX7yXbBedVfI4PNx6FLdFXu9GHUFsr28s4BVGxm4BeybtnX3P06saF"
PROJECT_URL = "https://github.com/cpp-linter/ccache-wheel"


@dataclass(frozen=True)
class Platform:
    upstream: str  # suffix of the upstream archive name
    archive: str  # "tar.gz" or "zip"
    binary: str  # file name of the executable in the archive
    tags: str  # wheel platform tag (a compressed tag set is allowed)
    check: str  # expected binary format, see check_binary()


# Linux wheels use the upstream musl static builds: they run on any Linux
# (old glibc distributions and Alpine alike), so one wheel serves both the
# manylinux and the musllinux tags. The macOS binary is universal (x86_64
# 10.15+, arm64 11.0+), so one wheel serves both architectures.
PLATFORMS = [
    Platform(
        "darwin",
        "tar.gz",
        "ccache",
        "macosx_10_15_x86_64.macosx_11_0_arm64.macosx_10_15_universal2",
        "macho-universal",
    ),
    Platform(
        "linux-x86_64-musl-static",
        "tar.gz",
        "ccache",
        "manylinux_2_17_x86_64.manylinux2014_x86_64.musllinux_1_1_x86_64",
        "elf-x86_64",
    ),
    Platform(
        "linux-aarch64-musl-static",
        "tar.gz",
        "ccache",
        "manylinux_2_17_aarch64.manylinux2014_aarch64.musllinux_1_1_aarch64",
        "elf-aarch64",
    ),
    Platform(
        "linux-riscv64-musl-static",
        "tar.gz",
        "ccache",
        "manylinux_2_17_riscv64.musllinux_1_1_riscv64",
        "elf-riscv64",
    ),
    Platform(
        "linux-s390x-musl-static",
        "tar.gz",
        "ccache",
        "manylinux_2_17_s390x.manylinux2014_s390x.musllinux_1_1_s390x",
        "elf-s390x",
    ),
    Platform(
        "windows-x86_64",
        "zip",
        "ccache.exe",
        "win_amd64",
        "pe-x86_64",
    ),
]


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def http_get(url: str) -> bytes:
    headers = {"User-Agent": "cpp-linter-ccache-wheel"}
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=headers), timeout=120
            ) as resp:
                return resp.read()
        except OSError as exc:  # network hiccup (URLError, timeout): retry with backoff
            last_error = exc
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"failed to download {url}: {last_error}")


# --- minisign -------------------------------------------------------------


def verify_minisign(data: bytes, file_name: str, minisig: bytes) -> str:
    """Check a minisign signature; return the trusted comment."""
    key = base64.b64decode(MINISIGN_PUBLIC_KEY)
    if len(key) != 42 or key[:2] != b"Ed":
        raise ValueError("bad minisign public key")
    key_id, public_key = key[2:10], Ed25519PublicKey.from_public_bytes(key[10:])

    lines = minisig.decode("utf-8").splitlines()
    if len(lines) < 4 or not lines[2].startswith("trusted comment: "):
        raise ValueError(f"{file_name}: malformed .minisig file")
    sig = base64.b64decode(lines[1])
    if len(sig) != 74:
        raise ValueError(f"{file_name}: malformed signature")
    algorithm, sig_key_id, signature = sig[:2], sig[2:10], sig[10:]
    if sig_key_id != key_id:
        raise ValueError(f"{file_name}: signed with an unknown key")
    if algorithm == b"ED":  # prehashed (minisign default since 0.11)
        message = hashlib.blake2b(data, digest_size=64).digest()
    elif algorithm == b"Ed":
        message = data
    else:
        raise ValueError(f"{file_name}: unknown signature algorithm")

    trusted_comment = lines[2][len("trusted comment: ") :]
    global_signature = base64.b64decode(lines[3])
    try:
        public_key.verify(signature, message)
        public_key.verify(global_signature, signature + trusted_comment.encode())
    except InvalidSignature:
        raise ValueError(f"{file_name}: BAD SIGNATURE") from None

    # The trusted comment names the signed file; make sure it was not swapped.
    match = re.search(r"(?:^|\t)file:([^\t]+)", trusted_comment)
    if match and match.group(1) != file_name:
        raise ValueError(
            f"{file_name}: signature is for {match.group(1)!r}, not this file"
        )
    return trusted_comment


def download_verified(version: str, name: str, cache: Path) -> bytes:
    cache.mkdir(parents=True, exist_ok=True)
    path, sig_path = cache / name, cache / f"{name}.minisig"
    if not path.exists() or not sig_path.exists():
        log(f"downloading {name}")
        path.write_bytes(http_get(DOWNLOAD_URL.format(version=version, name=name)))
        sig_path.write_bytes(
            http_get(DOWNLOAD_URL.format(version=version, name=f"{name}.minisig"))
        )
    data = path.read_bytes()
    verify_minisign(data, name, sig_path.read_bytes())
    log(f"  signature OK: {name} (sha256 {hashlib.sha256(data).hexdigest()})")
    return data


# --- archive handling -----------------------------------------------------


def read_archive(data: bytes, kind: str, prefix: str) -> tuple[dict[str, bytes], int]:
    """Return {relative path: content} for the files under prefix/, and the
    binary's mtime (used as the timestamp of every wheel entry)."""
    files: dict[str, bytes] = {}
    mtime = 0
    if kind == "tar.gz":
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile() or not member.name.startswith(prefix + "/"):
                    continue
                rel = member.name[len(prefix) + 1 :]
                extracted = tar.extractfile(member)
                assert extracted is not None
                files[rel] = extracted.read()
                if rel == "ccache":
                    mtime = int(member.mtime)
    else:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for info in archive.infolist():
                if info.is_dir() or not info.filename.startswith(prefix + "/"):
                    continue
                rel = info.filename[len(prefix) + 1 :]
                files[rel] = archive.read(info)
                if rel == "ccache.exe":
                    mtime = calendar.timegm(info.date_time + (0, 0, 0))
    return files, mtime


def check_binary(data: bytes, expected: str) -> None:
    """Fail early if an upstream archive holds a binary for another platform."""
    if expected.startswith("elf-"):
        machines = {"x86_64": 62, "aarch64": 183, "riscv64": 243, "s390x": 22}
        if data[:4] != b"\x7fELF":
            raise ValueError("not an ELF file")
        endian = "<" if data[5] == 1 else ">"
        machine = struct.unpack(endian + "H", data[18:20])[0]
        if machine != machines[expected[4:]]:
            raise ValueError(f"ELF machine {machine}, expected {expected}")
        if b"/lib/ld-" in data[:4096] or b"/lib64/ld-" in data[:4096]:
            raise ValueError("expected a static binary, found a program interpreter")
    elif expected == "macho-universal":
        if data[:4] != b"\xca\xfe\xba\xbe":
            raise ValueError("not a universal Mach-O binary")
        count = struct.unpack(">I", data[4:8])[0]
        cpus = {
            struct.unpack(">I", data[8 + 20 * i : 12 + 20 * i])[0] for i in range(count)
        }
        if cpus != {0x01000007, 0x0100000C}:  # x86_64, arm64
            raise ValueError(f"unexpected Mach-O slices {sorted(map(hex, cpus))}")
    elif expected == "pe-x86_64":
        if data[:2] != b"MZ":
            raise ValueError("not a PE file")
        pe = struct.unpack("<I", data[0x3C:0x40])[0]
        if (
            data[pe : pe + 4] != b"PE\0\0"
            or struct.unpack("<H", data[pe + 4 : pe + 6])[0] != 0x8664
        ):
            raise ValueError("not an x86_64 PE file")
    else:
        raise ValueError(f"unknown check {expected}")


# --- wheel writing --------------------------------------------------------


def record_hash(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return "sha256=" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def metadata(version: str, upstream_version: str) -> str:
    readme = (ROOT / "PYPI_README.md").read_text(encoding="utf-8")
    readme = readme.replace("{version}", upstream_version).replace(
        "{wheel_version}", version
    )
    headers = [
        ("Metadata-Version", "2.4"),
        ("Name", "ccache"),
        ("Version", version),
        ("Summary", "ccache, the C/C++ compiler cache, packaged as Python wheels"),
        ("Author", "Joel Rosdahl and the ccache contributors"),
        ("Maintainer", "cpp-linter"),
        ("License-Expression", "GPL-3.0-or-later"),
        ("License-File", "GPL-3.0.txt"),
        ("License-File", "LICENSE.md"),
        ("Keywords", "ccache,compiler,cache,c,c++,build"),
        ("Classifier", "Development Status :: 5 - Production/Stable"),
        ("Classifier", "Intended Audience :: Developers"),
        ("Classifier", "Operating System :: MacOS"),
        ("Classifier", "Operating System :: Microsoft :: Windows"),
        ("Classifier", "Operating System :: POSIX :: Linux"),
        ("Classifier", "Programming Language :: C"),
        ("Classifier", "Programming Language :: C++"),
        ("Classifier", "Topic :: Software Development :: Build Tools"),
        ("Classifier", "Topic :: Software Development :: Compilers"),
        ("Project-URL", "Homepage, https://ccache.dev"),
        ("Project-URL", "Documentation, https://ccache.dev/documentation.html"),
        ("Project-URL", "Upstream, https://github.com/ccache/ccache"),
        ("Project-URL", f"Source, {PROJECT_URL}/releases/tag/v{version}"),
        ("Project-URL", f"Packaging, {PROJECT_URL}"),
        (
            "Project-URL",
            "Changelog, https://ccache.dev/releasenotes.html#_ccache_"
            + upstream_version.replace(".", "_"),
        ),
        ("Description-Content-Type", "text/markdown; charset=UTF-8"),
    ]
    return "".join(f"{k}: {v}\n" for k, v in headers) + "\n" + readme


def build_wheel(
    platform: Platform,
    version: str,
    upstream_version: str,
    files: dict[str, bytes],
    mtime: int,
    license_text: bytes,
    out_dir: Path,
) -> Path:
    dist_info = f"ccache-{version}.dist-info"
    data_dir = f"ccache-{version}.data"
    binary = files[platform.binary]
    check_binary(binary, platform.check)

    # (path in wheel, content, executable?)
    entries: list[tuple[str, bytes, bool]] = [
        (f"{data_dir}/scripts/{platform.binary}", binary, True),
    ]
    if "ccache.1" in files:
        entries.append(
            (f"{data_dir}/data/share/man/man1/ccache.1", files["ccache.1"], False)
        )
    entries += [
        (f"{dist_info}/METADATA", metadata(version, upstream_version).encode(), False),
        (
            f"{dist_info}/WHEEL",
            (
                "Wheel-Version: 1.0\n"
                "Generator: cpp-linter ccache-wheel build_wheels.py\n"
                "Root-Is-Purelib: false\n"
                + "".join(f"Tag: py3-none-{tag}\n" for tag in platform.tags.split("."))
            ).encode(),
            False,
        ),
        (
            f"{dist_info}/licenses/GPL-3.0.txt",
            files.get("GPL-3.0.txt", license_text),
            False,
        ),
        (f"{dist_info}/licenses/LICENSE.md", files["LICENSE.md"], False),
    ]

    record = io.StringIO()
    writer = csv.writer(record, lineterminator="\n")
    for path, content, _ in entries:
        writer.writerow([path, record_hash(content), len(content)])
    writer.writerow([f"{dist_info}/RECORD", "", ""])
    entries.append((f"{dist_info}/RECORD", record.getvalue().encode(), False))

    out_dir.mkdir(parents=True, exist_ok=True)
    wheel_path = out_dir / f"ccache-{version}-py3-none-{platform.tags}.whl"
    date_time = time.gmtime(max(mtime, 315532800))[:6]  # zip cannot go before 1980
    with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as whl:
        for path, content, executable in entries:
            info = zipfile.ZipInfo(path, date_time=date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3  # Unix, so the mode below is honoured
            info.external_attr = (0o100755 if executable else 0o100644) << 16
            whl.writestr(info, content, compresslevel=9)
    return wheel_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--version",
        default=(ROOT / "ccache_version.txt").read_text().strip(),
        help="wheel version: the ccache version, optionally with .postN "
        "(default: the content of ccache_version.txt)",
    )
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    parser.add_argument("--release-dir", type=Path, default=ROOT / "release")
    parser.add_argument("--cache", type=Path, default=ROOT / "downloads")
    args = parser.parse_args()

    match = re.fullmatch(r"(\d+\.\d+(?:\.\d+)?)(?:\.post\d+)?", args.version)
    if not match:
        parser.error(
            f"bad version {args.version!r}, expected e.g. 4.14.2 or 4.14.2.post1"
        )
    version, upstream_version = args.version, match.group(1)
    log(f"ccache {upstream_version} -> wheel version {version}")

    # Source archive first: it is published next to the wheels and supplies
    # GPL-3.0.txt, which the Windows archive does not include.
    source_name = f"ccache-{upstream_version}.tar.gz"
    source = download_verified(upstream_version, source_name, args.cache)
    source_files, _ = read_archive(source, "tar.gz", f"ccache-{upstream_version}")
    license_text = source_files["GPL-3.0.txt"]
    args.release_dir.mkdir(parents=True, exist_ok=True)
    (args.release_dir / source_name).write_bytes(source)
    (args.release_dir / f"{source_name}.minisig").write_bytes(
        (args.cache / f"{source_name}.minisig").read_bytes()
    )

    wheels = []
    for platform in PLATFORMS:
        stem = f"ccache-{upstream_version}-{platform.upstream}"
        data = download_verified(
            upstream_version, f"{stem}.{platform.archive}", args.cache
        )
        files, mtime = read_archive(data, platform.archive, stem)
        wheel = build_wheel(
            platform, version, upstream_version, files, mtime, license_text, args.out
        )
        log(f"  wrote {wheel.name}")
        wheels.append(wheel)

    sums = "".join(
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in wheels
    )
    (args.release_dir / "SHA256SUMS").write_text(sums)
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as out:
            out.write(f"upstream_version={upstream_version}\nversion={version}\n")
    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
