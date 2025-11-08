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

### Version Numbering

We follow [PEP 440](https://peps.python.org/pep-0440/) versioning:
- Standard releases: `0.1.0`, `0.2.0`, `1.0.0`
- Post releases (patches after a release): `0.1.0.post1`, `0.1.0.post2`
- Release candidates (for testing): `0.1.0rc1`, `0.1.0rc2`

### Creating a Release

#### 1. Update Version

Update the version in `pyproject.toml`:

```toml
[project]
version = "0.1.2"  # or "0.1.1.post1" for post-release
```

#### 2. Commit Version Bump

```bash
git add pyproject.toml
git commit -m "chore: bump version to 0.1.2"
git push origin main
```

#### 3. Create and Push Git Tag

```bash
# Create annotated tag
git tag -a v0.1.2 -m "Release v0.1.2"

# Push tag to GitHub
git push origin v0.1.2
```

**Important**: The tag name must match the version in `pyproject.toml` with a `v` prefix:
- Version `0.1.2` → Tag `v0.1.2`
- Version `0.1.1.post1` → Tag `v0.1.1post1`

#### 4. Create GitHub Release

1. Go to https://github.com/Joe-Heffer/sys2txt/releases/new
2. Select the tag you just pushed (e.g., `v0.1.2`)
3. Set release title (e.g., "Release v0.1.2")
4. Add release notes describing changes
5. Click "Publish release"

This will automatically trigger the PyPI publishing workflow.

### Testing a Release (TestPyPI)

For release candidates, you can test the publishing process using TestPyPI:

#### 1. Update Version to RC

```toml
[project]
version = "0.1.2rc1"  # Release candidate
```

#### 2. Create RC Tag and Push

```bash
git add pyproject.toml
git commit -m "chore: prepare release candidate 0.1.2rc1"
git push origin main

git tag -a v0.1.2-rc1 -m "Release candidate v0.1.2rc1"
git push origin v0.1.2-rc1
```

This will publish to TestPyPI at https://test.pypi.org/project/sys2txt/

#### 3. Test Installation from TestPyPI

```bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ sys2txt
```

### CI/CD Workflows

The project uses GitHub Actions for automated testing and publishing:

- **CI** (`.github/workflows/ci.yml`): Runs on every push and PR
  - Tests on Python 3.9, 3.10, 3.11, 3.12
  - Formatting check with `ruff format --check`
  - Linting with `ruff check`
  - Unit tests

- **TestPyPI** (`.github/workflows/publish-to-testpypi.yml`):
  - Triggered by tags matching `v*-rc*` (e.g., `v0.1.2-rc1`)
  - Publishes to https://test.pypi.org

- **PyPI** (`.github/workflows/publish-to-pypi.yml`):
  - Triggered when a GitHub release is published
  - Publishes to https://pypi.org
  - Signs packages with Sigstore
  - Uploads signed artifacts to release

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
- Target Python 3.9+ compatibility
- Use type hints where beneficial
- Write docstrings for public functions

## Questions or Issues?

- Open an issue: https://github.com/Joe-Heffer/sys2txt/issues
- Discussions: https://github.com/Joe-Heffer/sys2txt/discussions
