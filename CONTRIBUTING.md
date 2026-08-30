# Contributing to sys2txt

Thank you for your interest in contributing to sys2txt!

## Development Setup

1. Clone the repository:
```bash
git clone https://github.com/Joe-Heffer/sys2txt.git
cd sys2txt
```

2. Install system dependencies:
```bash
sudo apt update && sudo apt install -y ffmpeg python3-venv python3-pip
```

3. Create virtual environment and install Python dependencies:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Development Workflow

### Running Tests

```bash
# Run all tests
python -m unittest discover -s tests -p "test_*.py"

# Run with verbose output
python -m unittest discover -s tests -p "test_*.py" -v

# Run specific test file
python -m unittest tests/test_audio.py

# Run specific test class
python -m unittest tests.test_audio.TestRecordOnce
```

### Code Quality

We use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting:

```bash
# Format code
ruff format src/

# Lint code
ruff check src/

# Auto-fix linting issues
ruff check --fix src/
```

### Running Locally

```bash
# Install in editable mode
pip install -e .

# Run the CLI
sys2txt once --model small
sys2txt live --model small --segment-seconds 8

# Or run as module without installing
python -m sys2txt once --model small
```

## Release Process

Releases are automated with release-please; see [RELEASING.md](RELEASING.md) for the full
process, including test releases via TestPyPI. Do not bump the version in `pyproject.toml`
by hand — release-please manages it from Conventional Commit messages.

### CI/CD Workflows

The project uses GitHub Actions for automated testing and publishing:

- **CI** (`.github/workflows/ci.yml`): Runs on every push and PR
  - Tests on Python 3.10, 3.11, 3.12, 3.13, 3.14
  - Formatting check with `ruff format --check`
  - Linting with `ruff check`
  - Unit tests

- **TestPyPI** (`.github/workflows/publish-to-testpypi.yml`):
  - Triggered by tags matching `v*-rc*` (e.g., `v0.1.2-rc1`)
  - Publishes to https://test.pypi.org

- **PyPI** (`.github/workflows/publish-to-pypi.yml`):
  - Triggered by pushing a tag matching `v*` or `sys2txt-v*`
  - Publishes to https://pypi.org via trusted publishing

## Pull Request Guidelines

1. Fork the repository and create a feature branch
2. Make your changes with clear, descriptive commits
3. Add tests for new functionality
4. Ensure all tests pass: `python -m unittest discover -s tests`
5. Format and lint your code: `ruff format src/ && ruff check src/`
6. Update documentation if needed (README.md, CLAUDE.md)
7. Submit a pull request with a clear description of changes

## Code Style

- Follow PEP 8 (enforced by Ruff)
- Line length: 120 characters
- Target Python 3.10+ compatibility
- Use type hints where beneficial
- Write docstrings for public functions

## Questions or Issues?

- Open an issue: https://github.com/Joe-Heffer/sys2txt/issues
- Discussions: https://github.com/Joe-Heffer/sys2txt/discussions
