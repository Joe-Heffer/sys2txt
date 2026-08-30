# Changelog

## [0.7.0](https://github.com/Joe-Heffer/sys2txt/compare/v0.6.1...v0.7.0) (2026-08-30)


### Features

* auto-download missing whisper.cpp models ([#99](https://github.com/Joe-Heffer/sys2txt/issues/99)) ([f0d98ea](https://github.com/Joe-Heffer/sys2txt/commit/f0d98eab024884933faf8013f6e279d54692450c)), closes [#71](https://github.com/Joe-Heffer/sys2txt/issues/71)


### Bug Fixes

* whisper.cpp engine parses -oj JSON instead of scraping console output ([#97](https://github.com/Joe-Heffer/sys2txt/issues/97)) ([67e6acd](https://github.com/Joe-Heffer/sys2txt/commit/67e6acd629b5aa2f5f8aa12d9a9de426f1523d05))

## [0.6.1](https://github.com/Joe-Heffer/sys2txt/compare/v0.6.0...v0.6.1) (2026-08-30)


### Bug Fixes

* bound ffmpeg shutdown and stop live transcription racing temp-dir cleanup ([#88](https://github.com/Joe-Heffer/sys2txt/issues/88)) ([0d06b07](https://github.com/Joe-Heffer/sys2txt/commit/0d06b07592a1dc295a8cd7ebf456f15361bc9f0f)), closes [#55](https://github.com/Joe-Heffer/sys2txt/issues/55)
* correct logging config precedence, record mutation, and unprefixed env vars ([#59](https://github.com/Joe-Heffer/sys2txt/issues/59)) ([#94](https://github.com/Joe-Heffer/sys2txt/issues/94)) ([be6595b](https://github.com/Joe-Heffer/sys2txt/commit/be6595b2963e69f2e0f43d011abf964da0611bda))
* drain ffmpeg's stderr in live mode to prevent deadlock ([#85](https://github.com/Joe-Heffer/sys2txt/issues/85)) ([d6190f4](https://github.com/Joe-Heffer/sys2txt/commit/d6190f4efda9f65c12c4de3720cb80e8ce370751)), closes [#52](https://github.com/Joe-Heffer/sys2txt/issues/52)
* drop dead RuntimeError clause and avoid double pactl call in pulse.py ([#96](https://github.com/Joe-Heffer/sys2txt/issues/96)) ([86156e3](https://github.com/Joe-Heffer/sys2txt/commit/86156e31a50829a92af56db31f79ade9d042fd2f)), closes [#61](https://github.com/Joe-Heffer/sys2txt/issues/61)
* gate publishing on tests and stop dropping releases via path filters ([#92](https://github.com/Joe-Heffer/sys2txt/issues/92)) ([9a65243](https://github.com/Joe-Heffer/sys2txt/commit/9a652433a14c6d20767869917eaabf1d6fcabe26)), closes [#57](https://github.com/Joe-Heffer/sys2txt/issues/57)
* only create output/ directory when it will actually be used ([#95](https://github.com/Joe-Heffer/sys2txt/issues/95)) ([6ef7a1e](https://github.com/Joe-Heffer/sys2txt/commit/6ef7a1ee2a4929c81be74ad42c7caf379d9acb4d)), closes [#60](https://github.com/Joe-Heffer/sys2txt/issues/60)
* raise on ffmpeg failure in record_once instead of discarding it ([#87](https://github.com/Joe-Heffer/sys2txt/issues/87)) ([08e1cd0](https://github.com/Joe-Heffer/sys2txt/commit/08e1cd08480c18d882669b6e972c3cc32cfe84fe)), closes [#54](https://github.com/Joe-Heffer/sys2txt/issues/54)
* validate --output path is writable before recording or transcription ([#56](https://github.com/Joe-Heffer/sys2txt/issues/56)) ([#90](https://github.com/Joe-Heffer/sys2txt/issues/90)) ([e3b46b2](https://github.com/Joe-Heffer/sys2txt/commit/e3b46b20a40595b367e2445261bdad093b270100))
* warn on --device/--engine combinations that silently fall back to CPU ([#58](https://github.com/Joe-Heffer/sys2txt/issues/58)) ([#93](https://github.com/Joe-Heffer/sys2txt/issues/93)) ([0d37163](https://github.com/Joe-Heffer/sys2txt/commit/0d37163902a34a589a6ff380b394c42a1dd4461c))

## [0.6.0](https://github.com/Joe-Heffer/sys2txt/compare/v0.5.4...v0.6.0) (2026-08-30)


### Features

* add a public library API and make live capture a generator ([#73](https://github.com/Joe-Heffer/sys2txt/issues/73)) ([038e4c7](https://github.com/Joe-Heffer/sys2txt/commit/038e4c706f611bda8c82f36627a155af57d50c3c)), closes [#62](https://github.com/Joe-Heffer/sys2txt/issues/62)
* add SRT, WebVTT, JSON and TSV transcript output formats ([#76](https://github.com/Joe-Heffer/sys2txt/issues/76)) ([89c9425](https://github.com/Joe-Heffer/sys2txt/commit/89c9425a6484667491cab4d47bc3d7ef1b799499))
* report and cap how far live transcription falls behind recording ([#79](https://github.com/Joe-Heffer/sys2txt/issues/79)) ([89b97e6](https://github.com/Joe-Heffer/sys2txt/commit/89b97e63a59425e8af2c97cead69407cf786ca98)), closes [#66](https://github.com/Joe-Heffer/sys2txt/issues/66)


### Bug Fixes

* tell transcription failures apart from silence in live mode ([#75](https://github.com/Joe-Heffer/sys2txt/issues/75)) ([0860cbb](https://github.com/Joe-Heffer/sys2txt/commit/0860cbb04d53dfd66904710eaa064d80d2e5fe61)), closes [#53](https://github.com/Joe-Heffer/sys2txt/issues/53)


### Documentation

* remove duplicate changelog entries ([0f71e3f](https://github.com/Joe-Heffer/sys2txt/commit/0f71e3f4f146544fd0cccf5b3614c5fd1179ff1c))
* simplify security policy, remove outdated version table and email contact ([154a236](https://github.com/Joe-Heffer/sys2txt/commit/154a23686547e64855168d7f9df24e00933d766d))

## [0.5.4](https://github.com/Joe-Heffer/sys2txt/compare/v0.5.3...v0.5.4) (2026-08-27)


### Bug Fixes

* handle Ctrl-C gracefully at top level and inform live-mode users ([#45](https://github.com/Joe-Heffer/sys2txt/issues/45)) ([262d027](https://github.com/Joe-Heffer/sys2txt/commit/262d02734583fad3c659321731cac527a176bfac))

## [0.5.3](https://github.com/Joe-Heffer/sys2txt/compare/v0.5.2...v0.5.3) (2026-08-27)


### Bug Fixes

* use PAT for release-please to trigger downstream publish workflow ([#48](https://github.com/Joe-Heffer/sys2txt/issues/48)) ([01419bd](https://github.com/Joe-Heffer/sys2txt/commit/01419bd434035bc02060db34323311897e920e2a))

## [0.5.2](https://github.com/Joe-Heffer/sys2txt/compare/v0.5.1...v0.5.2) (2026-08-27)


### Bug Fixes

* default log level to WARNING to suppress engine INFO spam ([5268c21](https://github.com/Joe-Heffer/sys2txt/commit/5268c215373fd1aefb883387ddd7f614b10baa88))

## [0.5.1](https://github.com/Joe-Heffer/sys2txt/compare/v0.5.0...v0.5.1) (2026-07-23)


### Bug Fixes

* always request timestamps from whisper-cli to fix empty transcripts ([a3c36e7](https://github.com/Joe-Heffer/sys2txt/commit/a3c36e7d5ad1a0933e9cc4dd4970961836bfa5fa)), closes [#42](https://github.com/Joe-Heffer/sys2txt/issues/42)

## [0.5.0](https://github.com/Joe-Heffer/sys2txt/compare/v0.4.0...v0.5.0) (2026-06-04)


### Features

* add --version flag to CLI ([4ac9e20](https://github.com/Joe-Heffer/sys2txt/commit/4ac9e20b5d6f046cfe763f675e09359c376278f1))

## [0.4.0](https://github.com/Joe-Heffer/sys2txt/compare/v0.3.0...v0.4.0) (2026-04-14)


### Features

* add ANSI color formatting to log output when stderr is a TTY ([dc763e2](https://github.com/Joe-Heffer/sys2txt/commit/dc763e2b724e38606077c1844601128e789ad737))
* add publish to pypi workflows ([d3c0372](https://github.com/Joe-Heffer/sys2txt/commit/d3c03720abc9f09768e44b43185d49b352f2264d))
* add release-please for automatic version bumping ([3e13457](https://github.com/Joe-Heffer/sys2txt/commit/3e1345783ba378aab19853aa380d8ee63b065578))
* add security policy ([6d48abd](https://github.com/Joe-Heffer/sys2txt/commit/6d48abd7fb9dd596121ed9cd1fdb06bb758daea3))
* always write transcripts to output/ directory ([4c76d52](https://github.com/Joe-Heffer/sys2txt/commit/4c76d52740158caa29ce7ba6bbbaa4582dc541c8))
* auto-stop live mode after a period of silence ([152398d](https://github.com/Joe-Heffer/sys2txt/commit/152398da068ca9d273b99002a9ec735851b555a8))
* make whisper engines optional dependencies ([db6f33c](https://github.com/Joe-Heffer/sys2txt/commit/db6f33c462ee6b1d6fffda996190e2cc55914db1))
* replace print statements with logging ([dba30bc](https://github.com/Joe-Heffer/sys2txt/commit/dba30bc27dc0db0f38c957be908bb5854984596e))
* restrict workflow triggers with path filters ([7756e4e](https://github.com/Joe-Heffer/sys2txt/commit/7756e4e5c0047c7b0f3a453d8f572c7089e96603))
* thread-safe model caching in transcribe.py ([221ccdb](https://github.com/Joe-Heffer/sys2txt/commit/221ccdb81bd8def3c800a3624a377ebab41725dd))


### Bug Fixes

* cache whisper models and add transcription timeout to prevent freezing ([0f05e63](https://github.com/Joe-Heffer/sys2txt/commit/0f05e63b19db286d277131fd0b2a90e54bcbce33))
* don't specify model list ([aa34c22](https://github.com/Joe-Heffer/sys2txt/commit/aa34c2233922566fc92ead7fbb0faea5a0d84502))
* prevent freezing on in-progress segments and add whisper.cpp engine ([3df1991](https://github.com/Joe-Heffer/sys2txt/commit/3df1991afaaca79ecb220bcc73b9ca34b0385262))
* replace bare except clauses with specific exception types ([f24cc63](https://github.com/Joe-Heffer/sys2txt/commit/f24cc639192296c5698efd4915823e63a3e452d4))
* use explicit import check for faster-whisper auto-detection ([1b22dab](https://github.com/Joe-Heffer/sys2txt/commit/1b22dab2e0b5b67875576eeb9a58588dea237ab4))
* use pypa/gh-action-pypi-publish ([9f86df4](https://github.com/Joe-Heffer/sys2txt/commit/9f86df4821cae29b6455bda73c11307ee852e97d))


### Documentation

* add link to guide ([eaad37c](https://github.com/Joe-Heffer/sys2txt/commit/eaad37c5de1daa25a9330e32c5026af9cb76851f))
* tweak README ([eb8f1b1](https://github.com/Joe-Heffer/sys2txt/commit/eb8f1b16f32290207898b0633de77501a27d65a6))
* Update copyright year in LICENSE file ([151b94f](https://github.com/Joe-Heffer/sys2txt/commit/151b94fdc9a76ba2ef8c773efe7e99260059b380))
* update installation instructions to reference PyPI and remove cd step ([99314ee](https://github.com/Joe-Heffer/sys2txt/commit/99314eea39b0b043e847b6523549962c666be89f))
* Update supported versions in SECURITY.md ([8f150f8](https://github.com/Joe-Heffer/sys2txt/commit/8f150f81eb779a50c0a54b6b4ca6fa9b19ba294c))

## [0.3.0](https://github.com/Joe-Heffer/sys2txt/compare/sys2txt-v0.2.0...sys2txt-v0.3.0) (2026-04-14)


### Features

* add ANSI color formatting to log output when stderr is a TTY ([dc763e2](https://github.com/Joe-Heffer/sys2txt/commit/dc763e2b724e38606077c1844601128e789ad737))

## [0.2.0](https://github.com/Joe-Heffer/sys2txt/compare/sys2txt-v0.1.2...sys2txt-v0.2.0) (2026-04-09)


### Features

* add publish to pypi workflows ([d3c0372](https://github.com/Joe-Heffer/sys2txt/commit/d3c03720abc9f09768e44b43185d49b352f2264d))
* add release-please for automatic version bumping ([3e13457](https://github.com/Joe-Heffer/sys2txt/commit/3e1345783ba378aab19853aa380d8ee63b065578))
* add security policy ([6d48abd](https://github.com/Joe-Heffer/sys2txt/commit/6d48abd7fb9dd596121ed9cd1fdb06bb758daea3))
* always write transcripts to output/ directory ([4c76d52](https://github.com/Joe-Heffer/sys2txt/commit/4c76d52740158caa29ce7ba6bbbaa4582dc541c8))
* auto-stop live mode after a period of silence ([152398d](https://github.com/Joe-Heffer/sys2txt/commit/152398da068ca9d273b99002a9ec735851b555a8))
* make whisper engines optional dependencies ([db6f33c](https://github.com/Joe-Heffer/sys2txt/commit/db6f33c462ee6b1d6fffda996190e2cc55914db1))
* replace print statements with logging ([dba30bc](https://github.com/Joe-Heffer/sys2txt/commit/dba30bc27dc0db0f38c957be908bb5854984596e))
* restrict workflow triggers with path filters ([7756e4e](https://github.com/Joe-Heffer/sys2txt/commit/7756e4e5c0047c7b0f3a453d8f572c7089e96603))
* thread-safe model caching in transcribe.py ([221ccdb](https://github.com/Joe-Heffer/sys2txt/commit/221ccdb81bd8def3c800a3624a377ebab41725dd))


### Bug Fixes

* cache whisper models and add transcription timeout to prevent freezing ([0f05e63](https://github.com/Joe-Heffer/sys2txt/commit/0f05e63b19db286d277131fd0b2a90e54bcbce33))
* don't specify model list ([aa34c22](https://github.com/Joe-Heffer/sys2txt/commit/aa34c2233922566fc92ead7fbb0faea5a0d84502))
* prevent freezing on in-progress segments and add whisper.cpp engine ([3df1991](https://github.com/Joe-Heffer/sys2txt/commit/3df1991afaaca79ecb220bcc73b9ca34b0385262))
* replace bare except clauses with specific exception types ([f24cc63](https://github.com/Joe-Heffer/sys2txt/commit/f24cc639192296c5698efd4915823e63a3e452d4))
* use explicit import check for faster-whisper auto-detection ([1b22dab](https://github.com/Joe-Heffer/sys2txt/commit/1b22dab2e0b5b67875576eeb9a58588dea237ab4))
* use pypa/gh-action-pypi-publish ([9f86df4](https://github.com/Joe-Heffer/sys2txt/commit/9f86df4821cae29b6455bda73c11307ee852e97d))


### Documentation

* add link to guide ([eaad37c](https://github.com/Joe-Heffer/sys2txt/commit/eaad37c5de1daa25a9330e32c5026af9cb76851f))
* tweak README ([eb8f1b1](https://github.com/Joe-Heffer/sys2txt/commit/eb8f1b16f32290207898b0633de77501a27d65a6))
