# Contributing

Contributions are welcome! Open an [issue](https://github.com/cpp-linter/ccache-wheel/issues),
start a discussion in [cpp-linter Discussions](https://github.com/orgs/cpp-linter/discussions),
or submit a pull request.

## Development setup

```bash
git clone https://github.com/cpp-linter/ccache-wheel.git
cd ccache-wheel
python -m pip install -r requirements.txt
python build_wheels.py
```

Test a wheel in a virtual environment:

```bash
python -m venv .venv
.venv/bin/python -m pip install --no-index --find-links dist ccache
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python tests/smoke_test.py --version "$(cat ccache_version.txt)"
```

Run `pre-commit run --all-files` before you push.

## Pull requests

PR titles follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`,
`chore:`, ...); Release Drafter uses them for the release notes. The release version always
comes from `ccache_version.txt`.
