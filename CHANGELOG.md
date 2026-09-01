# Changelog

All notable changes to `grantcheck` are documented here. This project follows [Semantic Versioning](https://semver.org/) and the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added
- M1 models and EIN handling: `ein.py` (normalize, validate, format, shard-prefix
  extraction) and `models.py` (`Report`, `Check`, `Vintage`, `Organization`,
  `Opportunity`, `MatchConfidence`) with lossless JSON round-trip, the `schema_version`
  contract, readiness derivation, and exit codes.
- M0 skeleton: `pyproject.toml` with the `grantcheck` console entry point, `uv` project,
  `ruff` lint and format configuration, `pytest`, and the package layout under `src/`.
- Program-level documents vendored under `docs/program/` so a fresh clone resolves every
  reference without fetching another repository.
- Repository scaffolding: documentation, research dossier, and build prompts.

### Changed
- `docs/research/competitive.md` rewritten to describe the capability gap without naming
  or pricing any commercial product, per program decision D-002.
