"""Hatchling build hook that repackages an official ccache binary as a wheel.

The metadata hook downloads the upstream ccache archive for one platform,
checks its minisign signature against the ccache release key and the
binary's format, and stages the files in upstream/. The build hook hands the
binary to hatchling as a shared script. pip and uv install it
unchanged into the environment's bin/ (Scripts\\ on Windows), with no Python
wrapper in between.

Pick the platform with CCACHE_PLATFORM (one of `python hatch_build.py
platforms`); without it, the platform of the build machine is used:

    CCACHE_PLATFORM=windows-x86_64 uv build --wheel
    pip install .

`python hatch_build.py source DIR` saves the signed ccache source archive,
which every release ships next to the wheels (GPL-3.0-or-later).
"""

from __future__ import annotations

import base64
import hashlib
import io
import os
import platform as host
import re
import shutil
import struct
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import NamedTuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT = Path(__file__).resolve().parent
# Upstream files for the wheel being built; pyproject.toml takes the license
# files from here.
STAGE = ROOT / "upstream"
CACHE = ROOT / ".cache" / "downloads"
DOWNLOAD_URL = "https://github.com/ccache/ccache/releases/download/v{version}/{name}"
# Release signing key published on https://ccache.dev/download.html
# (also https://ccache.dev/minisign.pub, key id 7C55E705DB25EF17).
MINISIGN_PUBLIC_KEY = "RWQX7yXbBedVfI4PNx6FLdFXu9GHUFsr28s4BVGxm4BeybtnX3P06saF"


class Platform(NamedTuple):
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
        # uv only accepts manylinux_2_31 or newer for riscv64, the first glibc
        # with a manylinux image for it.
        "manylinux_2_31_riscv64.musllinux_1_1_riscv64",
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


def ccache_version() -> str:
    """The ccache version inside the wheels: ccache_version.txt without .postN."""
    version = (ROOT / "ccache_version.txt").read_text().strip()
    match = re.fullmatch(r"(\d+\.\d+(?:\.\d+)?)(?:\.post\d+)?", version)
    if not match:
        raise ValueError(f"bad version {version!r} in ccache_version.txt")
    return match.group(1)


def host_platform() -> Platform:
    machine = host.machine().lower()
    if sys.platform == "darwin":
        name = "darwin"
    elif sys.platform == "win32" and machine in ("amd64", "x86_64"):
        name = "windows-x86_64"
    elif sys.platform.startswith("linux"):
        name = f"linux-{'aarch64' if machine == 'arm64' else machine}-musl-static"
    else:
        name = f"{sys.platform}-{machine}"
    return get_platform(name)


def get_platform(name: str) -> Platform:
    for platform in PLATFORMS:
        if platform.upstream == name:
            return platform
    choices = ", ".join(p.upstream for p in PLATFORMS)
    raise ValueError(f"no upstream ccache binary for {name!r}; choose one of {choices}")


def extract(data: bytes, kind: str, prefix: str) -> dict[str, bytes]:
    """Return {relative path: content} for the files under prefix/."""
    files: dict[str, bytes] = {}
    if kind == "tar.gz":
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for member in tar.getmembers():
                if member.isfile() and member.name.startswith(prefix + "/"):
                    extracted = tar.extractfile(member)
                    assert extracted is not None
                    files[member.name[len(prefix) + 1 :]] = extracted.read()
    else:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for info in archive.infolist():
                if not info.is_dir() and info.filename.startswith(prefix + "/"):
                    files[info.filename[len(prefix) + 1 :]] = archive.read(info)
    return files


def stage(platform: Platform, version: str) -> None:
    """Put the binary, the man page and the license files in STAGE."""
    stem = f"ccache-{version}-{platform.upstream}"
    files = extract(
        download_verified(version, f"{stem}.{platform.archive}", CACHE),
        platform.archive,
        stem,
    )
    binary = files[platform.binary]
    check_binary(binary, platform.check)
    if "GPL-3.0.txt" not in files:  # the Windows archive has no copy
        source = download_verified(version, f"ccache-{version}.tar.gz", CACHE)
        files["GPL-3.0.txt"] = extract(source, "tar.gz", f"ccache-{version}")[
            "GPL-3.0.txt"
        ]

    shutil.rmtree(STAGE, ignore_errors=True)
    STAGE.mkdir(parents=True)
    (STAGE / platform.binary).write_bytes(binary)
    (STAGE / platform.binary).chmod(0o755)
    for name in ("GPL-3.0.txt", "LICENSE.md", "ccache.1"):
        if name in files:
            (STAGE / name).write_bytes(files[name])


def selected_platform() -> Platform:
    name = os.environ.get("CCACHE_PLATFORM")
    return get_platform(name) if name else host_platform()


try:
    from hatchling.builders.hooks.plugin.interface import BuildHookInterface
    from hatchling.metadata.plugin.interface import MetadataHookInterface
except ImportError:  # running as a script
    BuildHookInterface = MetadataHookInterface = object  # type: ignore[assignment,misc]


class CustomMetadataHook(MetadataHookInterface):  # type: ignore[misc,valid-type]
    """Stage the upstream files before hatchling reads `license-files`."""

    def update(self, metadata: dict) -> None:
        platform = selected_platform()
        log(f"ccache {ccache_version()} for {platform.upstream}")
        stage(platform, ccache_version())


class CustomBuildHook(BuildHookInterface):  # type: ignore[misc,valid-type]
    """Put the staged binary and man page into the wheel."""

    def initialize(self, version: str, build_data: dict) -> None:
        if self.target_name != "wheel":
            raise RuntimeError("ccache is published as wheels only")
        platform = selected_platform()
        binary = STAGE / platform.binary
        if not binary.is_file():
            raise RuntimeError(f"{binary} is missing; the metadata hook did not run")

        build_data["pure_python"] = False
        build_data["tag"] = f"py3-none-{platform.tags}"
        build_data["shared_scripts"][str(binary)] = platform.binary
        if (STAGE / "ccache.1").is_file():
            build_data["shared_data"][str(STAGE / "ccache.1")] = (
                "share/man/man1/ccache.1"
            )


def main(argv: list[str]) -> int:
    if argv[:1] == ["platforms"]:
        print("\n".join(p.upstream for p in PLATFORMS))
    elif len(argv) == 2 and argv[0] == "source":
        version, out = ccache_version(), Path(argv[1])
        name = f"ccache-{version}.tar.gz"
        out.mkdir(parents=True, exist_ok=True)
        (out / name).write_bytes(download_verified(version, name, CACHE))
        shutil.copyfile(CACHE / f"{name}.minisig", out / f"{name}.minisig")
    else:
        print("usage: python hatch_build.py platforms | source DIR", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
