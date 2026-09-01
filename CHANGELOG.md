# Changelog

All notable changes to `grantcheck` are documented here. This project follows [Semantic Versioning](https://semver.org/) and the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## [0.1.0] — 2026-09-01

First release. `uvx grantcheck --ein 27-1067272` returns a sourced, dated federal grant
readiness report with no account, no API key, and no database.

### Added
- Optional OpenGrants enrichment. Setting `OPENGRANTS_API_KEY` appends live matched
  opportunities to a clean report, marked `— live from OpenGrants`. Every failure path —
  no key, bad key, rate limited, timeout, network down, malformed or reshaped response —
  produces output byte-identical to running with no key at all, asserted in the tests.
  The tool is complete without an account and never mentions the key in its output.
- Monthly index build workflow publishing to GitHub Releases, and a PyPI publish workflow
  using Trusted Publishing rather than a stored token.
- M8 MCP server: `grantcheck mcp` serves `check_readiness`, `find_ein`, `explain_check`, and
  `dataset_vintages` over stdio, every one calling the same `build_report()` the CLI calls.
  Eleven plain-English check explainers, also served by `grantcheck explain <check_id>`.
- M7 output formats: `--format table|markdown|json`, a committed JSON Schema for the
  version 1.0 contract that real output is validated against in the test suite, and the
  documented exit codes 0 to 4 verified end to end against the real index.
- M6 single audit screen: the threshold rule (`$750,000` for fiscal years beginning before
  2024-10-01, `$1,000,000` on or after), fiscal-year inference from the Business Master
  File accounting period, and a check that is a screen rather than a determination — never
  a failure, and never silent about what the reported figure excludes. `acct_pd` is now
  carried through the parser and the index schema.
- M5 SAM.gov: `ingest/matching.py` infers the EIN-to-UEI link by normalized legal name and
  state with a published confidence score and tier, and the three federal-registration
  checks (`sam_registration`, `sam_expiration`, `uei`). `--uei` pins the match and skips
  inference. Below the confidence floor, and when the index carries no SAM.gov data at all,
  the checks report `unknown` rather than a finding.
- M4 checks and terminal rendering: the seven non-SAM checks (exempt status, Publication 78
  deductibility, automatic revocation, organization type, most recent filing, filing
  recency, NTEE), `report.build_report()` as the single entry point both adapters call, the
  terminal renderer, and `grantcheck --ein` and `grantcheck cache`.
- M3 index build and client: `ingest/build.py` shards the merged datasets by EIN prefix
  into compressed SQLite with a checksummed manifest, and `sources/index.py` fetches,
  verifies, caches, and queries them. A real build produces 234 shards totalling 145 MB,
  median shard 0.66 MB, largest 4.83 MB — none over the 8 MB target.
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
- `--format markdown > report.md` wrote cp1252 rather than UTF-8 on Windows, producing a
  file that is not valid UTF-8 anywhere else. Markdown and JSON are file formats and are
  now written as UTF-8 bytes on every platform. Reconfiguring `sys.stdout` was not
  sufficient, because click caches its own text wrapper around the original stream.
- Terminal output could still emit non-ASCII when the stream could not carry it: check
  values contain typographic characters (an em dash in `Listed — PC`) independently of the
  renderer's own glyphs. ASCII mode now transliterates the whole rendered string.
- Private foundations were reported as having no annual return required. They carry
  `FILING_REQ_CD=00`, which alone reads that way, but 129,561 of them also carry
  `PF_FILING_REQ_CD=1` and file a Form 990-PF — and are subject to the same three-year
  automatic revocation counter. Only 4,507 organizations have both codes clear.
- Terminal output used box-drawing and en-dash characters that a default Windows console
  (cp1252) cannot encode, so the ASCII degradation path was incomplete and would have
  raised `UnicodeEncodeError` instead of printing a report.
- Organizations revoked more than once were reported using whichever row came last in the
  file. 19,136 EINs carry multiple rows on the Automatic Revocation List — revoked,
  reinstated, then revoked again — and the merge now selects by latest revocation date.
  The previous behaviour reported three verified currently-revoked organizations as
  reinstated and in good standing.
- A well-formed EIN whose two-digit prefix has no shard now reports not found rather than
  raising. Ten prefixes (07, 09, 17, 18, 19, 28, 29, 49, 79, 89) have no shard because the
  IRS has never issued them, and those must exit 4, not 1.
- A malformed month in a BMF date field nulled the whole organization row. One real row
  carries `RULING=190900`. Field-level problems now null the field and are counted
  separately from structural quarantine.
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
