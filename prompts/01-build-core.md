# Build Prompt: grantcheck core library, CLI, and MCP server

You are building `grantcheck` from an empty repository that currently contains only documentation.
Assume you have no context beyond this file and the files it tells you to read. Work through the
milestones in order. Do not skip ahead to polish.

---

## 1. Mission

Organizations spend forty hours writing a federal grant application they were never able to
submit. Their tax exemption was automatically revoked for three consecutive years of not filing.
Their SAM.gov registration expired. Their Unique Entity ID was never issued. They crossed the
single audit threshold and do not know it.

Every one of those is a hard disqualification. Every one is checkable in seconds against public
federal data. No free tool checks them together, because the data lives in two agencies that do
not share a join key.

You are building the tool that checks them together:

```bash
uvx grantcheck --ein 27-1067272
```

One command, no account, no API key, no database, no 2-million-row download. A one-page readiness
report in about two seconds, with the source and the publication date on every line.

**The thing that makes this work is the packaging, not the data.** The data is public and several
projects already parse it. What does not exist is a path from "I have an EIN" to "here is the
answer" that takes under a minute and costs nothing. Protect that path above every other
consideration in this build.

---

## 2. Read these first, in this order

Read each one completely before writing code. They are binding, not background.

1. `docs/program/CONVENTIONS.md` — Egeria program conventions. The two hard rules, the dual-interface requirement,
   the OpenGrants integration rules, the attribution requirements, the required disclosure text,
   and the engineering standards all come from here and are not negotiable.
2. `docs/research/data-sources.md` — **the most important file in this repository.** Every dataset,
   its exact fields, its cadence, and the specific ways each one will give you a plausible wrong
   answer. Most of the bugs you can ship are already described in it.
3. `README.md` — the user-facing promise, the example output, and the check descriptions. The
   report you build must match what the README shows.
4. `docs/NON-GOALS.md` — the scope boundary. If you find yourself building something on that list,
   stop.
5. `CONTRIBUTING.md` — in particular the fixture-based testing rule, which is a hard requirement.

---

## 3. Hard constraints

Violating any of these means the build is wrong regardless of what else works.

1. **`uvx grantcheck --ein 12-3456789` works on a clean machine with an empty environment.** No
   account, no key, no config file, no prior `refresh`. First run downloads what it needs and
   caches it. If a new user cannot get a real result within 60 seconds of reading the README, the
   design is wrong.
2. **The user never downloads the full dataset.** The IRS bulk files are ~2M rows and hundreds of
   megabytes. See section 6 for the sharded index design that avoids this. This is the central
   engineering problem of the build.
3. **Business logic lives in the library.** `src/grantcheck/` holds all check logic. The CLI and
   the MCP server are thin adapters that call the same functions and format the same result object.
   A rule implemented inside a Click callback is a bug. The MCP server is not written last and is
   not a wrapper around the CLI.
4. **Every user-visible fact carries its source and its dataset vintage.** No exceptions. "As of" is
   not optional.
5. **The tool never makes an eligibility determination.** It reports observable facts and what they
   usually mean. `readiness` is `ready`, `attention`, or `blocked`, where `blocked` means a
   mechanical hard stop was observed, not that we judged the organization ineligible. There is no
   score, no grade, no probability.
6. **The required disclosure appears in the output footer of every command that reports on an
   organization**, verbatim:

   > This is informational only, derived from public data on the dates shown. It is not an eligibility determination, and not legal, tax, or accounting advice. Verify against the official source before relying on it.

7. **OpenGrants enrichment is optional and silent.** Never required, never nagged about, never
   mentioned in command output when absent. A missing, invalid, expired, or rate-limited key, or
   any network failure, must degrade to the un-enriched report without a warning, a delay over the
   timeout, or a non-zero exit. Enriched lines are marked `— live from OpenGrants`.
8. **SAM.gov public tier only.** Never request sensitive-tier fields. Never accept a key with
   sensitive entitlements knowingly.
9. **No telemetry, no analytics, no phoning home.** The tool fetches index shards and, optionally,
   SAM.gov and OpenGrants. Nothing else leaves the machine. It must never report which EINs were
   checked.
10. **Fixture tests against real committed data.** No mock-shaped tests for anything that parses an
    upstream format. The failure mode that actually matters here is schema drift, and mocks are
    blind to it.
11. **Python 3.11+, `uv`, `ruff` for lint and format, `pytest`.** `pyproject.toml` with a console
    entry point. Apache 2.0.
12. **Dependencies are few and boring.** Target under ten runtime dependencies. Every one is a
    thing that can break `uvx` cold start. Prefer the standard library.

---

## 4. Module architecture

```
grantcheck/
├── pyproject.toml
├── src/grantcheck/
│   ├── __init__.py
│   ├── models.py           # dataclasses: Organization, Check, Report, Vintage, MatchConfidence
│   ├── ein.py              # normalize, validate, format, prefix extraction
│   ├── report.py           # THE entry point: build_report(ein, options) -> Report
│   ├── checks/
│   │   ├── __init__.py     # registry: id -> check function, ordered
│   │   ├── exempt_status.py
│   │   ├── pub78.py
│   │   ├── auto_revocation.py
│   │   ├── organization_type.py
│   │   ├── filing_recency.py
│   │   ├── ntee.py
│   │   ├── sam_registration.py
│   │   ├── uei.py
│   │   └── single_audit.py
│   ├── sources/
│   │   ├── index.py        # shard fetch, cache, manifest, SQLite queries
│   │   ├── sam.py          # live SAM.gov Entity Management client
│   │   ├── opengrants.py   # optional enrichment client
│   │   └── propublica.py   # optional gap-filling lookups
│   ├── ingest/             # builds the index; NOT shipped in the runtime path
│   │   ├── teos.py         # the four TEOS bulk file parsers
│   │   ├── efile.py        # 990 e-file index + concordance-driven XML field extraction
│   │   ├── sam_extract.py
│   │   ├── matching.py     # EIN <-> UEI name/state inference with confidence
│   │   └── build.py        # shard, compress, manifest, publish
│   ├── render/
│   │   ├── table.py        # terminal, default
│   │   ├── markdown.py
│   │   └── json.py
│   ├── explanations/*.md   # one plain-English explainer per check id
│   ├── data/
│   │   ├── codes/*.csv     # IRS code tables, committed, sourced from the data dictionary
│   │   └── concordance/    # pinned subset of the NODC Master Concordance File + SHA
│   ├── cli.py              # Click/Typer adapter. Zero business logic.
│   └── mcp_server.py       # MCP adapter. Zero business logic.
└── tests/
    ├── fixtures/           # real slices of real upstream files + .source.json each
    └── ...
```

The shape to hold onto: **`report.build_report()` is the only thing either adapter calls.** It
returns a fully populated `Report` object containing every fact, every source, every vintage, and
the disclosure string. Renderers turn a `Report` into text. Adapters call the builder and pick a
renderer. Nothing else.

### The Report object

```python
@dataclass(frozen=True)
class Vintage:
    dataset: str          # 'bmf' | 'pub78' | 'revocation' | 'epostcard' | 'efile_index' | 'sam' | 'fac'
    published: date       # what the SOURCE declares, not when we downloaded it
    source_url: str

@dataclass(frozen=True)
class Check:
    id: str               # stable, snake_case; part of the public JSON contract
    label: str            # 'SAM.gov registration'
    group: str            # 'tax_exemption' | 'filing_health' | 'federal_registration' | 'audit_posture'
    status: str           # 'pass' | 'warn' | 'fail' | 'unknown' | 'not_applicable'
    blocking: bool        # a 'fail' here mechanically prevents submission
    value: str | None     # the short rendered value: 'Active', 'Expired 2026-05-02'
    detail: str | None    # one to three sentences, plain English, including what to do about it
    vintage: Vintage | None
    confidence: float | None   # only where a fact was inferred rather than looked up

@dataclass(frozen=True)
class Report:
    schema_version: str   # '1.0'
    ein: str              # formatted '27-1067272'
    queried_at: datetime  # UTC, ISO 8601
    organization: Organization | None
    checks: list[Check]
    readiness: str        # 'ready' | 'attention' | 'blocked' | 'not_found'
    blocking_check_ids: list[str]
    opportunities: list[Opportunity] | None   # only when enrichment ran
    vintages: list[Vintage]
    disclosure: str       # the verbatim required text
    notes: list[str]      # e.g. 'Matched to SAM.gov by legal name and state, confidence 0.91'
```

`readiness` derivation: `not_found` if the EIN is absent from the index; `blocked` if any check is
`fail` and `blocking`; `attention` if any check is `warn` or a non-blocking `fail`; `ready`
otherwise. **`unknown` never causes `blocked`.** An unchecked thing is not a failed thing, and
conflating them is the most damaging bug this tool can have.

### The checks

Implement exactly these, in this order, in these groups.

| id | group | blocking | Source | Pass condition |
|---|---|---|---|---|
| `exempt_status` | tax_exemption | yes | EO BMF | `SUBSECTION == '03'` and `STATUS == '01'` |
| `pub78_deductibility` | tax_exemption | no | Pub 78 | Listed. **Absent + non-zero `GROUP` is `not_applicable`, never a failure** — see below. |
| `auto_revocation` | tax_exemption | yes | Revocation List | Absent, or present with a reinstatement date on or after the revocation date |
| `organization_type` | tax_exemption | no | EO BMF foundation code | Not a private foundation. Warn, with the explanation that most federal programs exclude private foundations. |
| `most_recent_filing` | filing_health | no | e-file index UNION 990-N | A filing exists |
| `filing_recency` | filing_health | no | derived | 0 or 1 years since last filing = pass; 2 = warn; 3 or more = fail (non-blocking) with the automatic revocation explanation |
| `ntee` | filing_health | no | EO BMF | Informational. `unknown` when absent, never a failure. The terminal renderer promotes it to the organization header line rather than printing it as a row; it is still a `Check` in the JSON. |
| `sam_registration` | federal_registration | yes | SAM snapshot or live | Status active |
| `sam_expiration` | federal_registration | yes | SAM snapshot or live | Not expired; warn inside 60 days |
| `uei` | federal_registration | yes | SAM snapshot or live | A UEI exists |
| `single_audit` | audit_posture | no | 990 government grants + FAC + USAspending | Screen only. Never `fail`; `warn` above the threshold, `pass` below, `unknown` with no data. |

### The four correctness traps you must not fall into

These are not edge cases. Each one affects hundreds of thousands of organizations, and each
produces an answer that looks right and is catastrophically wrong.

1. **Group exemption subordinates are not individually listed in Publication 78.** The central
   organization is listed and covers them. A local chapter with a non-zero `GROUP` in the BMF will
   correctly be absent from Pub 78. Reporting that as a problem tells a compliant organization it
   cannot receive deductible contributions. **Check `GROUP` before evaluating `pub78_deductibility`
   and before evaluating filing recency**, since subordinates are often covered by a group return
   and have no filings of their own.
2. **Presence on the Automatic Revocation List does not mean currently revoked.** Reinstated
   organizations stay on the list forever with a reinstatement date populated. Read the
   reinstatement date. The correct output for a reinstated organization is a history — "revoked
   2019-05-15, reinstated 2020-11-15, currently in good standing" — with a `pass` status.
3. **Filing recency must union the 990-N e-Postcard file with the 990 e-file index.** The majority
   of exempt organizations file the 990-N, which is not in the e-file XML index. Build recency from
   the index alone and you will tell every small nonprofit in the country that it is three years
   delinquent and about to be revoked.
4. **`TAX_PERIOD` in the BMF is not a filing date.** It is the period of the most recent processed
   return at month precision, lagging actual filing by weeks to over a year. Use it only as a
   labelled fallback, never as the primary recency signal.

Write a test for each of these four, named after the trap, before you write the check.

---

## 5. Output

### Terminal (default)

Match the README example. Grouped sections, a status glyph per row, aligned values, the readiness
verdict directly under the organization header, blocking failures listed first when the verdict is
`blocked`. Colour where the terminal supports it, degrading cleanly when it does not and when
`NO_COLOR` is set. Never require a wide terminal — wrap at 80 columns.

The footer always carries: the source list with vintages, any match-confidence note, and the
disclosure verbatim.

### Markdown (`--format markdown`)

Same content as a document someone pastes into a memo or an email. Tables, not glyph art.

### JSON (`--format json`)

The `Report` object serialized, with `schema_version`. This is a public contract — additive changes
only within a major version. Keys are snake_case. Dates are ISO 8601. `null` for unknown, never an
empty string.

### Exit codes

```
0  ready
1  usage or runtime error (bad EIN format, network failure with no cache, etc.)
2  blocked  — at least one blocking check failed
3  attention — warnings only
4  not_found — the EIN is not in the index
```

Document these in `--help`. They exist so a consultant can put this in a cron job over a client
roster, which is a real use and one the design should welcome even though the tool itself will
never grow watch mode.

---

## 6. The index: data ingestion and local cache

**This is the design that makes the 60-second quickstart possible. Get it right before anything
else.**

### The problem

The IRS EO Business Master File is ~1.9M rows. Pub 78 is ~1.3M. The revocation list is ~800K. Even
compressed, the joined dataset is well over 100 MB. A tool whose first run downloads that has no
quickstart, and one that queries a hosted API on every run is a tool that stops working when we
stop paying for the API and quietly reports what EINs its users are researching.

### The solution: shard by EIN prefix

An EIN's first two digits are a stable partition key. There are on the order of 90 prefixes in
active use. Shard the index on that prefix, and a user checking one EIN downloads roughly one
ninetieth of the data.

> Note for your own understanding, not for the output: EIN prefixes originally encoded the issuing
> IRS district and no longer map to geography, since EINs are now issued by campus and online.
> They remain a stable, well-distributed partition key, which is all we need.

**Published artifacts**, built by the ingest job and published to R2 with a GitHub release mirror:

```
{base}/{vintage}/manifest.json
{base}/{vintage}/shard-{NN}.sqlite.zst
```

`manifest.json`:

```json
{
  "manifest_version": 1,
  "vintage": "2026-08",
  "built_at": "2026-08-14T06:12:03Z",
  "datasets": [
    {"dataset": "bmf", "published": "2026-08-11", "source_url": "...", "row_count": 1904221},
    {"dataset": "pub78", "published": "2026-08-11", "source_url": "...", "row_count": 1312884},
    {"dataset": "revocation", "published": "2026-08-11", "source_url": "...", "row_count": 812004},
    {"dataset": "epostcard", "published": "2026-08-11", "source_url": "...", "row_count": 688119},
    {"dataset": "efile_index", "published": "2026-07-20", "source_url": "...", "row_count": 2210443},
    {"dataset": "sam", "published": "2026-08-29", "source_url": "...", "row_count": 742118}
  ],
  "shards": [
    {"prefix": "27", "file": "shard-27.sqlite.zst", "bytes": 2841204,
     "sha256": "...", "rows": 21847}
  ]
}
```

**Shard contents.** One SQLite database per prefix, holding one denormalized row per EIN with
every field the checks need, plus a small `meta` table carrying the vintages. Denormalized on
purpose: a check should be one indexed lookup, not five joins.

**Size discipline.** Target every shard under 8 MB compressed. Prefixes are unevenly distributed
(a handful of them are very large). If a shard exceeds the target, split it by the third digit into
`shard-{NNN}` and record both forms in the manifest so the client resolves the most specific
available shard. The client must handle both shapes.

### The client

```
1. Resolve the base URL: GRANTCHECK_INDEX_BASE_URL, else the default, else the GitHub release mirror.
2. GET manifest.json. Cache it with a 12-hour TTL. On network failure, use the cached manifest and
   say so in the report footer.
3. Compute the prefix from the normalized EIN. Find its shard.
4. If the cached shard for this vintage exists and its sha256 matches, use it.
5. Otherwise download, verify the sha256, decompress, write atomically (temp file + rename), and
   proceed. Show a progress indicator only if the download exceeds ~500 ms.
6. Query. One indexed SELECT.
7. Prune shards from vintages older than the two most recent.
```

Cache location: `GRANTCHECK_CACHE_DIR`, else `platformdirs.user_cache_dir("grantcheck")`, laid out
as `{cache}/{vintage}/shard-{NN}.sqlite`. Never write outside it. Handle a read-only or full
filesystem by running from a temp directory for the session with a single warning.

**`grantcheck refresh`** — fetch the current manifest, report which datasets changed vintage,
re-download shards already held, prune old vintages. `--all` downloads every shard for offline or
bulk use and states the total size before starting. Warn when any dataset vintage is more than 45
days old, because that usually means the IRS moved a URL and the ingest is silently stale.

**`grantcheck cache info` / `cache clear`** — show what is held and its vintage; remove it.

### SAM.gov, and the join that does not exist

**You cannot look up a SAM.gov entity by EIN on the public tier.** The taxpayer identification
number is sensitive-tier. Public search keys are UEI, CAGE, and legal business name.
**Verify this against the current Entity Management API documentation before building — it shapes
the entire SAM half of the tool.**

So the EIN-to-UEI link is inferred:

1. Take `NAME`, `SORT_NAME`, `STATE`, and `CITY` from the BMF.
2. Normalize aggressively: uppercase, strip punctuation, drop corporate suffixes (INC, CORP, LLC,
   THE, FOUNDATION where trailing), collapse whitespace, expand common abbreviations.
3. Match against the SAM snapshot on state plus normalized name similarity.
4. Emit a confidence score. **Print it.** Never present an inferred match as a lookup.
5. `--uei UEI` pins the match and skips inference entirely. Document this prominently, because it
   is the escape hatch for every mismatch.
6. Below a confidence floor, report the three SAM checks as `unknown` with "could not confidently
   match this EIN to a SAM.gov entity; re-run with `--uei`", not as failures.

Keyless operation reads the SAM snapshot bundled into the index shard, labelled with the snapshot
date. With `SAM_API_KEY` set, the three SAM checks go live and are labelled as of the run.

> **Decided — no longer blocking. Bundle the snapshot.** See `docs/program/DECISIONS.md`, D-001, and
> `docs/research/data-sources.md` section 3. Take exactly these public-tier fields and no others:
> UEI, legal business name, state, city, registration status, registration expiration date,
> registration purpose. Never request or store anything from the "For Official Use Only" or
> sensitive tiers. Ship `data/SOURCES.md` alongside the index naming the fields taken and the
> extract date; that file is a deliverable of M5, not documentation to add later.

### The ingest job

`src/grantcheck/ingest/` is a separate extra (`uv sync --extra ingest`) and is not on the runtime
path — a user running `uvx grantcheck` must never install its dependencies. It runs in GitHub
Actions monthly and on manual dispatch.

Steps: scrape the two IRS landing pages for current links and fail loudly if they differ from the
pinned defaults; download; parse with quarantine-and-count for malformed rows and a failure
threshold; extract the government-grants field from the e-file XML using the pinned concordance
subset; build the SAM snapshot and run the matching; shard, compress, checksum; write the manifest;
publish to R2 and mirror to a GitHub release; smoke-test a fixed list of EINs against the new
index before the manifest is published, since the manifest is the commit point.

---

## 7. The MCP server

Same capabilities, agent-shaped. `grantcheck mcp` starts it on stdio.

| Tool | Arguments | Returns |
|---|---|---|
| `check_readiness` | `ein`, optional `uei` | The full `Report` as JSON, plus a short rendered Markdown summary the model can quote directly |
| `find_ein` | `name`, optional `state` | Up to ten candidate organizations with EIN, name, city, state |
| `explain_check` | `check_id` | The plain-English explainer for that check |
| `dataset_vintages` | none | Current vintages, so an agent can state how fresh its answer is |

Every tool description tells the model that results are informational only and includes the
disclosure. Tool results carry vintages in-band; a model that quotes this tool must be able to
attribute it without a second call.

Write it against the official Python MCP SDK. It calls `report.build_report()` — the same function
the CLI calls. It does not shell out to the CLI, and it does not reimplement a check.

---

## 8. Milestones, in build order

Each milestone ends green: `ruff check`, `ruff format --check`, and `pytest` all pass, and the
stated demo works.

**M0 — Skeleton.** `pyproject.toml` with the console entry point, `uv` project, `ruff` and
`pytest` configured, `LICENSE` (Apache 2.0 full text), `NOTICE` (already written — do not
regenerate it), `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), `SECURITY.md`, `.gitignore`
including `.env`, `CHANGELOG.md`, and `.github/workflows/ci.yml` running lint and tests on 3.11,
3.12, 3.13. `uvx --from . grantcheck --version` works.
*Demo: the version prints.*

**M1 — EIN handling and models.** `ein.py` and `models.py`. Normalization accepts `27-1067272`,
`271067272`, `27 0125367`, and rejects everything else with a message that shows the expected
format. Prefix extraction. `Report`, `Check`, `Vintage`, `Organization` dataclasses with JSON
serialization and a round-trip test.
*Demo: `pytest tests/test_ein.py` covers valid, invalid, whitespace, unicode, and empty input.*

**M2 — TEOS parsers with real fixtures.** `ingest/teos.py` parsing all four files. Handle every
gotcha in `docs/research/data-sources.md`: embedded pipes, Latin-1 bytes, inconsistent zero
padding, fixed-width space padding, mixed line endings, the BMF CSV-versus-pipe inconsistency.
Commit real fixture slices with `.source.json` sidecars.
*Demo: parsing the fixtures produces correct typed records, and a deliberately malformed row is
quarantined and counted rather than silently misparsed.*

**M3 — Index build and shard client.** `ingest/build.py` produces sharded SQLite from parsed data;
`sources/index.py` fetches, verifies, caches, and queries. Build a real index locally from a real
download and query it.
*Demo: a shard downloads, verifies its checksum, caches, and answers a query. A second run does no
network I/O.*

**M4 — Checks, minus SAM.** All checks except the three SAM ones. **Write the four
correctness-trap tests first**, then make them pass. Terminal renderer. Disclosure in the footer.
*Demo: `grantcheck --ein 27-1067272` prints a real report with real vintages.*

**M5 — SAM.gov.** Matching with confidence, the bundled snapshot path, the live path behind
`SAM_API_KEY`, `--uei`, and the low-confidence `unknown` path.
*Demo: the same command now shows registration, expiration, and UEI, with a visible confidence
note; `--uei` pins the match.*

**M6 — Single audit screen.** Government grants from the e-file XML via the pinned concordance,
FAC filing history where a key is present, the threshold logic including the $750,000-to-$1,000,000
change and its effective date. Wording is a screen, never an answer.
*Demo: an organization over the threshold gets a warning that tells them to go look at their SEFA.*

**M7 — Output formats and exit codes.** Markdown, JSON with `schema_version`, exit codes 0–4,
`NO_COLOR`, 80-column wrapping.
*Demo: `--format json | jq .readiness` and `echo $?` both behave as documented.*

**M8 — MCP server.** All four tools over stdio, calling the same `build_report()`.
*Demo: an MCP client lists the tools and gets a real report for a real EIN.*

**M9 — OpenGrants enrichment.** `POST /match-grants-api` when a clean report and a key are both
present. Hard timeout, total silence on every failure path, `— live from OpenGrants` marker.
*Demo: with a key, matched opportunities append. With a bad key, with no key, and with the network
down, the report is identical minus that section, and the exit code does not change.*

**M10 — Explainers, refresh, and release.** `grantcheck explain <check_id>` and
`grantcheck refresh`. Eleven explainer files. README example output regenerated from a real run
and reconciled with the committed README. First tagged release, `uvx grantcheck` verified from
PyPI on a clean machine.
*Demo: a colleague with no context runs one command from the README and gets a correct report.*

---

## 9. Acceptance criteria

Checkable, not aspirational. Every one is verifiable by running something.

**Quickstart**
- [ ] On a container with no cache, no `.env`, and no keys, `uvx grantcheck --ein 27-1067272`
      returns a complete report in under 15 seconds and downloads under 10 MB.
- [ ] A second run of the same command completes in under 1 second with no network access at all.
- [ ] `uvx grantcheck --help` names every command and documents the exit codes.

**Correctness**
- [ ] A group exemption subordinate (non-zero `GROUP`) absent from Pub 78 reports
      `not_applicable` with the group ruling named, and never `fail`.
- [ ] An organization on the revocation list with a reinstatement date reports `pass` with the full
      history in `detail`.
- [ ] A 990-N-only small filer reports its most recent e-Postcard period and a correct
      years-since-filing count.
- [ ] No check produces `blocked` from an `unknown` status. Assert this over the whole check
      registry in a test.
- [ ] Every `Check` with a non-`unknown` status has a non-null `vintage`. Assert over the registry.
- [ ] `--format json` validates against the committed JSON Schema, which is itself committed and
      tested.

**Architecture**
- [ ] No module under `checks/`, `sources/`, or `render/` imports from `cli.py` or `mcp_server.py`.
      Enforce with a test that walks the import graph.
- [ ] `cli.py` and `mcp_server.py` contain no conditional logic on check status or values. Both are
      under 300 lines.
- [ ] `grantcheck --format json --ein X` and the MCP `check_readiness` tool return identical
      payloads for the same EIN and vintage. Assert in a test.

**Resilience**
- [ ] With the network fully unavailable and a warm cache, every command works and the footer says
      the manifest is cached.
- [ ] With the network unavailable and a cold cache, the tool exits 1 with an actionable message,
      never a traceback.
- [ ] With `OPENGRANTS_API_KEY` set to garbage, output is byte-identical to no key at all and the
      command is not measurably slower.
- [ ] With SAM.gov returning 500 and `SAM_API_KEY` set, the SAM checks fall back to the snapshot
      and say so.
- [ ] A malformed manifest, a checksum mismatch, and a truncated shard each produce a clear error
      and leave no corrupt file in the cache.

**Compliance with program conventions**
- [ ] The disclosure text appears verbatim in the footer of every report in all three formats.
- [ ] The README mentions the optional OpenGrants key exactly once and command output never
      mentions it.
- [ ] No secret in the repository. `.env` is gitignored. CI uses repository secrets.
- [ ] `NOTICE` names every upstream project. The vendored concordance subset carries its upstream
      commit SHA.
- [ ] CI is green on 3.11, 3.12, and 3.13, and the badge in the README resolves.

---

## 10. Verification: what to test, against which real organizations

Do this by hand before the first release, and freeze each result as a fixture with the date it was
verified. **Check every one against the live official source** — the IRS Tax Exempt Organization
Search at https://apps.irs.gov/app/eos/ and the SAM.gov entity record — not against another
aggregator.

| EIN | Organization | What it exercises |
|---|---|---|
| `27-1067272` | Code for America Labs | Active 501(c)(3), full 990 filer, likely SAM-registered. The happy path and the README example. |
| `20-0049703` | Wikimedia Foundation | Large, well-known, name in SAM is likely to differ from the BMF legal name. Tests name matching. |
| `53-0196605` | The American National Red Cross | Congressionally chartered. Tests an unusual organization type end to end. |
| `36-3673599` | Feeding America | Large national with affiliates. Tests that a central organization is not confused with its network. |
| `94-2278431` | The David and Lucile Packard Foundation | Private foundation. Must produce the `organization_type` warning and correct 990-PF handling. |
| `13-5562976` | Boys & Girls Clubs of America | Central organization of a large group. Pair it with a local club (find one in the BMF with a non-zero `GROUP` pointing at it) to test the subordinate path. |
| `00-0000000` | — | Not a valid EIN. Must exit 1 with a format message, never reach the network. |
| `99-9999999` | — | Well-formed and absent. Must exit 4 with the not-found explanation covering churches, government entities, and newly recognized organizations. |

**Cases you must find yourself in the real data**, because they cannot be named in advance and each
one is a correctness trap:

- **A currently revoked organization.** Take the most recent revocation posting from the file where
  the reinstatement date is empty. Verify the tool reports `blocked` with the correct revocation
  and posting dates.
- **A revoked-then-reinstated organization.** Same file, reinstatement date populated. Verify
  `pass` with the full history. **This is the single most important verification in the list** —
  getting it wrong tells a compliant organization it cannot apply for federal money.
- **A group exemption subordinate.** Non-zero `GROUP` in the BMF, absent from Pub 78. Verify
  `not_applicable` with the group ruling named, and verify filing recency does not flag it.
- **A 990-N-only filer.** Present in the e-Postcard file, absent from the e-file index. Verify
  recency is computed from the e-Postcard period.
- **An organization with a name in SAM.gov that differs materially from its BMF legal name.**
  Verify the confidence score is honest and that `--uei` fixes it.
- **An organization with no SAM registration at all.** Verify `fail` on `sam_registration` with an
  actionable message, and that `uei` and `sam_expiration` do not each repeat the same failure
  three times.

**Parser regression, run every ingest:** re-parse the previous month's committed fixtures and
assert the field-level output is unchanged. When it changes, the IRS changed something and that is
exactly what you needed to know.

**Cross-check:** for twenty randomly sampled EINs, compare exempt status and the most recent filing
period against ProPublica Nonprofit Explorer. Investigate every disagreement; do not assume either
side is right. Add each resolved disagreement as a fixture.

---

## 11. Stop and ask the human

Do not decide these on your own. Stop, state the options and your recommendation, and wait.

1. ~~**SAM.gov redistribution.**~~ **Answered 2026-08-31: bundle the snapshot.** See
   `docs/program/DECISIONS.md`, D-001, for the decision, the exact field list, the reasoning, and the
   fallback. Two things it obliges you to do: publish `data/SOURCES.md` with the index in M5, and
   take nothing above the public tier. One thing it forbids permanently: a proxy endpoint on
   check.opengrants.io that the CLI depends on, which stays rejected regardless of any later
   change in the terms — an open source tool that needs our servers to function is not one, and it
   would record which EINs users check.
2. **Where the index is published.** R2 bucket name and public URL, the GitHub release mirror
   naming, and who holds the credentials. Blocking for M3.
3. **A check that could produce a false accusation.** SAM.gov exclusions and debarment is the live
   example: it is a genuine hard disqualification, and a name-only match against the exclusions
   list that hits the wrong organization is defamatory. Current position is that it is out of scope
   without a confirmed UEI. Do not add it, or anything like it, without an explicit decision.
4. **Any new required configuration.** If you conclude that a check cannot work without a key, stop
   rather than adding one. The keyless quickstart outranks any individual check.
5. **Any dependency over ten runtime packages, or any dependency with a compiled extension.** Both
   threaten `uvx` cold start on the platforms that matter.
6. **Changing the JSON `schema_version` contract**, or renaming any `check.id`. These are public
   and the hosted site depends on them.
7. **The upstream concordance is missing a schema version you need.** File the upstream issue and
   ask before working around it locally, per the contribution posture in
   `docs/research/prior-art.md`.
8. **Wording that shifts from reporting a fact toward asserting a conclusion.** The single-audit
   screen is the pressure point — the honest wording is unsatisfying and there will be a strong
   pull toward making it more definite. That is a product decision, not an implementation detail.
9. **Anything you find on the `docs/NON-GOALS.md` list that seems necessary.** The list is arguable
   but it is not yours to override mid-build.
10. **The IRS changed a file format, a URL, or a code table mid-build.** Surface it immediately with
    what changed. Do not paper over it — a silently adapted parser that guesses at a new column is
    worse than a failed ingest.

---

## 12. Definition of done

A grant consultant who has never seen this repository reads the README, runs one command, and gets
a correct, sourced, dated readiness report for a client's EIN in under a minute — on a machine with
no Python project, no keys, and no configuration. Everything else in this document exists to make
that sentence true.
