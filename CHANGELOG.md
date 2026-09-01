# Changelog

All notable changes to `grantcheck` are documented here. This project follows [Semantic Versioning](https://semver.org/) and the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [Unreleased]

### Added
- M2 TEOS parsers: `ingest/teos.py` covering the EO Business Master File, Publication 78,
  the Automatic Revocation List, and the Form 990-N e-Postcard file, with
  quarantine-and-count for structurally invalid rows. Fixtures are real committed slices
  of the real IRS files with `.source.json` provenance sidecars.
- M1 models and EIN handling: `ein.py` (normalize, validate, format, shard-prefix
  extraction) and `models.py` (`Report`, `Check`, `Vintage`, `Organization`,
  `Opportunity`, `MatchConfidence`) with lossless JSON round-trip, the `schema_version`
  contract, readiness derivation, and exit codes.
- M0 skeleton: `pyproject.toml` with the `grantcheck` console entry point, `uv` project,
  `ruff` lint and format configuration, `pytest`, and the package layout under `src/`.
- Program-level documents vendored under `docs/program/` so a fresh clone resolves every
  reference without fetching another repository.
- Repository scaffolding: documentation, research dossier, and build prompts.

### Fixed
- The EIN used throughout the documentation for Code for America Labs was `27-0125367`,
  which is absent from the Business Master File entirely. The real EIN is `27-1067272`.
  The README example's NTEE code and ruling date were also wrong (`W20` and `2010-06`).
- `docs/research/data-sources.md` corrected against the real files: the three
  pipe-delimited datasets have no header row, the BMF uses RFC 4180 quoting, the
  revocation list is 1.25M rows of which 181,259 are reinstated, and `AFFILIATION` rather
  than `GROUP` distinguishes a group subordinate from a central organization.

### Changed
- `docs/research/competitive.md` rewritten to describe the capability gap without naming
  or pricing any commercial product, per program decision D-002.
