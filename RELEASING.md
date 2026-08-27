# Releasing

Releases are automated with [release-please](https://github.com/googleapis/release-please).

1. Merge changes to `main` using [Conventional Commits](https://www.conventionalcommits.org/)
   messages (`fix:`, `feat:`, `feat!:`/`BREAKING CHANGE:`, etc). These determine the next
   version and populate `CHANGELOG.md`.
2. release-please keeps an open "chore(main): release X.Y.Z" PR up to date on `main`. Merge
   it when you're ready to release.
3. Merging that PR triggers release-please to bump the version in `pyproject.toml`, update
   `CHANGELOG.md`, tag the commit, and publish a GitHub release.
4. Publishing the GitHub release triggers `.github/workflows/publish-to-pypi.yml`, which
   builds, signs (Sigstore), and publishes the package to [PyPI](https://pypi.org/project/sys2txt/)
   via trusted publishing.

## Release candidates

To test a release on TestPyPI before publishing for real, push a tag matching `v*-rc*`
(e.g. `v0.6.0-rc1`). This triggers `.github/workflows/publish-to-testpypi.yml`, which
publishes to [TestPyPI](https://test.pypi.org/project/sys2txt/).

## Manual version bumps

Avoid editing the version in `pyproject.toml` by hand — let release-please manage it based
on commit history.
