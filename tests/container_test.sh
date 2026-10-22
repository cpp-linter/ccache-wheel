#!/bin/sh
# Install the wheels from dist/ in a Linux container and run the smoke test.
# Used for Alpine (musl) and for the manylinux2014 image (glibc 2.17).
# Usage: tests/container_test.sh <expected ccache version>
set -eu

if command -v apk >/dev/null 2>&1; then
    apk add --no-cache python3 gcc musl-dev >/dev/null
    python=python3
else
    # quay.io/pypa/manylinux2014_*: gcc is installed, Python lives in /opt/python
    python=/opt/python/cp39-cp39/bin/python
fi

ldd --version 2>&1 | head -n 1 || true
"$python" -m venv /tmp/venv
/tmp/venv/bin/python -m pip install --no-index --find-links dist ccache
PATH="/tmp/venv/bin:$PATH" /tmp/venv/bin/python tests/smoke_test.py --version "$1"
