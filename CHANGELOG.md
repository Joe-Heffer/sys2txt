# Changelog

## [0.3.0](https://github.com/Joe-Heffer/sys2txt/compare/sys2txt-v0.2.0...sys2txt-v0.3.0) (2026-04-14)


### Features

* add ANSI color formatting to log output when stderr is a TTY ([dc763e2](https://github.com/Joe-Heffer/sys2txt/commit/dc763e2b724e38606077c1844601128e789ad737))
* colorized log output when stderr is a TTY ([9d30d1c](https://github.com/Joe-Heffer/sys2txt/commit/9d30d1cc0db73530fdb9b4f94b057ddf3e15df04))

## [0.2.0](https://github.com/Joe-Heffer/sys2txt/compare/sys2txt-v0.1.2...sys2txt-v0.2.0) (2026-04-09)


### Features

* add publish to pypi workflows ([d3c0372](https://github.com/Joe-Heffer/sys2txt/commit/d3c03720abc9f09768e44b43185d49b352f2264d))
* add pypi publish workflow ([d75fb05](https://github.com/Joe-Heffer/sys2txt/commit/d75fb05e74597c31586d3d0499403523e4ab3ab2))
* add release-please for automatic version bumping ([3e13457](https://github.com/Joe-Heffer/sys2txt/commit/3e1345783ba378aab19853aa380d8ee63b065578))
* add release-please for automatic version bumping ([605a139](https://github.com/Joe-Heffer/sys2txt/commit/605a139af3c0a10ea8e55053197c21fae9078496))
* add security policy ([6d48abd](https://github.com/Joe-Heffer/sys2txt/commit/6d48abd7fb9dd596121ed9cd1fdb06bb758daea3))
* always write transcripts to output/ directory ([4c76d52](https://github.com/Joe-Heffer/sys2txt/commit/4c76d52740158caa29ce7ba6bbbaa4582dc541c8))
* auto-stop live mode after a period of silence ([152398d](https://github.com/Joe-Heffer/sys2txt/commit/152398da068ca9d273b99002a9ec735851b555a8))
* auto-stop live mode after a period of silence ([316087d](https://github.com/Joe-Heffer/sys2txt/commit/316087d42072e3153ffc2c793363fb37e551ba96))
* make whisper engines optional dependencies ([db6f33c](https://github.com/Joe-Heffer/sys2txt/commit/db6f33c462ee6b1d6fffda996190e2cc55914db1))
* make whisper engines optional dependencies ([33939d4](https://github.com/Joe-Heffer/sys2txt/commit/33939d48ceb2f26ca13bc80fef0d3eece8087a17))
* replace print statements with logging ([dba30bc](https://github.com/Joe-Heffer/sys2txt/commit/dba30bc27dc0db0f38c957be908bb5854984596e))
* replace print statements with logging module ([1e863d7](https://github.com/Joe-Heffer/sys2txt/commit/1e863d7ab581d4d3868f8e62529fa70e773c9bdb))
* restrict workflow triggers with path filters ([7756e4e](https://github.com/Joe-Heffer/sys2txt/commit/7756e4e5c0047c7b0f3a453d8f572c7089e96603))
* restrict workflow triggers with path filters ([c89ae0a](https://github.com/Joe-Heffer/sys2txt/commit/c89ae0a3b5890b5581685d9cf4ef07ae42591e5c))
* thread-safe model caching in transcribe.py ([221ccdb](https://github.com/Joe-Heffer/sys2txt/commit/221ccdb81bd8def3c800a3624a377ebab41725dd))
* thread-safe model caching in transcribe.py ([73471df](https://github.com/Joe-Heffer/sys2txt/commit/73471dfeedebd9d77bc050717870fde7d646e02f))


### Bug Fixes

* cache whisper models and add transcription timeout to prevent freezing ([0f05e63](https://github.com/Joe-Heffer/sys2txt/commit/0f05e63b19db286d277131fd0b2a90e54bcbce33))
* don't specify model list ([aa34c22](https://github.com/Joe-Heffer/sys2txt/commit/aa34c2233922566fc92ead7fbb0faea5a0d84502))
* prevent freezing on in-progress segments and add whisper.cpp engine ([3df1991](https://github.com/Joe-Heffer/sys2txt/commit/3df1991afaaca79ecb220bcc73b9ca34b0385262))
* prevent freezing on in-progress segments and add whisper.cpp engine ([c55debb](https://github.com/Joe-Heffer/sys2txt/commit/c55debb5edcdd545be1dfa18a4a58cbbf9ee4796))
* prevent freezing on in-progress segments and add whisper.cpp engine ([5883081](https://github.com/Joe-Heffer/sys2txt/commit/58830811e7ca5f1adb5e2ead81765062d7dccdd7))
* replace bare except clauses with specific exception types ([f24cc63](https://github.com/Joe-Heffer/sys2txt/commit/f24cc639192296c5698efd4915823e63a3e452d4))
* replace bare except clauses with specific exception types ([defaaf1](https://github.com/Joe-Heffer/sys2txt/commit/defaaf18214fabb9c17bc6a11fc79344be6504a3))
* use explicit import check for faster-whisper auto-detection ([1b22dab](https://github.com/Joe-Heffer/sys2txt/commit/1b22dab2e0b5b67875576eeb9a58588dea237ab4))
* use pypa/gh-action-pypi-publish ([9f86df4](https://github.com/Joe-Heffer/sys2txt/commit/9f86df4821cae29b6455bda73c11307ee852e97d))


### Documentation

* add link to guide ([eaad37c](https://github.com/Joe-Heffer/sys2txt/commit/eaad37c5de1daa25a9330e32c5026af9cb76851f))
* tweak README ([eb8f1b1](https://github.com/Joe-Heffer/sys2txt/commit/eb8f1b16f32290207898b0633de77501a27d65a6))
