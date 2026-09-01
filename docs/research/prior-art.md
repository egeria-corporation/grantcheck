# Prior Art

The IRS publishes the raw material for this tool. It does not publish anything usable. The gap
between those two facts has been closed, over about fifteen years, mostly by unpaid people working
in public. This document names them, records precisely what `grantcheck` takes from each, and
commits to what we send back.

The posture, in one line: **contribute upstream first, credit loudly, and never re-implement
something a community project already does well just to own the code.** This community's
endorsement is a distribution channel for the whole program, and burning it to control a codebase
would be a bad trade at any price.

---

## Nonprofit Open Data Collective

https://github.com/Nonprofit-Open-Data-Collective ·
overview: https://nonprofit-open-data-collective.github.io/overview/

The center of gravity for open nonprofit data tooling.

### IRS E-file Master Concordance File — the most important upstream asset in the program

https://nonprofit-open-data-collective.github.io/irs-efile-master-concordance-file/

The IRS has published hundreds of Form 990 e-file schema versions since 2009. The same
conceptual field — say, government grants on Part VIII — sits at a different XPath depending on
the year and the return variant, with no stable field naming and no official crosswalk. The
concordance is that crosswalk. It is the reason reading 990 XML is a tractable engineering problem
instead of a multi-year data-cleaning project, and it is the actual moat of every commercial
product in this category, published for free.

**What we use:** the XPath mappings for a deliberately tiny set of fields — filing date, tax
period, return type, and the government grants line used by the single-audit screen. We vendor a
pinned subset covering only those fields into `src/grantcheck/data/concordance/`, with the upstream
commit SHA recorded in a sibling file and in `NOTICE`.

**What we do not do:** fork it, vendor the whole thing silently, or maintain a divergent copy. If a
schema version we need is missing or an XPath is wrong, that is an upstream issue and an upstream
pull request, filed before we work around it here.

### IRS-Efile-Database

https://nonprofit-open-data-collective.github.io/IRS-Efile-Database/

Reviewed during design. `grantcheck` reads only the e-file *index* CSVs plus one field from the XML
for a handful of organizations at a time, so a full database build is out of scope for us — but
this project is the right answer for anyone who needs the whole corpus, and the README should send
people there rather than pretending our narrow path generalizes.

---

## GivingTuesday 990 Data Programme

https://990data.givingtuesday.org/tool-repository/

- **[`form-990-xml-mapper`](https://github.com/Giving-Tuesday/form-990-xml-mapper)** — turns any
  990 XML schema into a CSV of every possible XPath. We used it to enumerate the XPath surface
  during design and to confirm that the fields we picked are stable across the versions we need.
- **[`form-990-xml-parser`](https://github.com/Giving-Tuesday/form-990-xml-parser)** — processes
  990 XML into MongoDB. Read closely as a reference implementation; not used at runtime, since our
  needs are far narrower and we do not want a database dependency.
- **Form 990 Variable Dictionary** and the **GivingTuesday 990 Data Mart Dictionary** — used to
  validate our field naming and to make sure the words we print for a financial line match the
  words practitioners already use.

No code vendored. Credit in `NOTICE` and in the README Credits section.

---

## irsx / 990-xml-reader — Jacob Fenton

https://github.com/jsfenfen/990-xml-reader

The reference implementation for reading IRS e-file XML in Python, and the project that
established the basic approach most later work follows. We consulted it for XML handling patterns
and for its treatment of schema versioning. Not a runtime dependency, because `grantcheck` reads
one field from a small number of filings and taking a full 990 parser as a dependency would be
disproportionate — but anyone who needs more than one field should use this rather than extend us.

---

## ProPublica Nonprofit Explorer

https://projects.propublica.org/nonprofits/api ·
terms: https://www.propublica.org/about/propublica-data-terms-of-use

1.8M+ filings from 2001 onward, no authentication, no documented rate limit. Two uses:

1. **Development cross-check.** When our parse of the IRS source disagrees with Nonprofit Explorer
   on a given EIN, one of us is wrong and it is worth finding out which. Several of our fixtures
   exist because of a disagreement found this way.
2. **Optional runtime gap-filling** for organizations where the IRS bulk files are incomplete.

We do not redistribute their data and we do not use the API as a substitute for parsing the IRS
source ourselves — a tool whose facts come from another aggregator inherits that aggregator's
errors and its availability. Requests carry a descriptive User-Agent identifying `grantcheck` with
a link to the repository, and responses are cached hard.

---

## propublica990 — Punderthings / Shane Curcuru

https://github.com/Punderthings/propublica990

Ruby tooling over the ProPublica API. Reviewed during design, particularly for its handling of the
response shapes and its pragmatic caching. No code vendored; different language.

## open990odl — 990 Consulting

https://github.com/990consulting/open990odl

Reviewed during design. Useful prior thinking on normalizing the open data layer.

## NBER Form 990 data

https://www.nber.org/research/data/irs-form-990-data

Used as an independent cross-check on historical filing coverage when validating the
filing-recency logic.

---

## What is genuinely new here, and what is not

Being honest about this matters, because overclaiming in front of the people who built the
foundations is the fastest way to lose them.

**Not new.** Parsing the TEOS bulk files. Reading 990 XML. Looking up an organization by EIN.
Publishing a nonprofit dataset. All of that has been done, in several languages, by the projects
above, and in some cases done better than we will do it.

**New, as far as we can find.** Three things:

1. **Composing IRS exempt-status data with SAM.gov registration state in one answer.** These are
   two different agencies, two different data models, and no public join key — the taxpayer
   identification number is sensitive-tier on the SAM.gov side, so the EIN-to-UEI link has to be
   inferred rather than looked up. Nobody free does this, and it is the reason the tool exists:
   the two most common hard disqualifications live on opposite sides of that gap.
2. **Filing recency as a forward-looking risk signal.** Everyone reports the auto-revocation list,
   which is a record of organizations that have already been revoked. Almost nobody reports
   "years since last filing" against the three-year counter, which is the only version of that
   fact that arrives while there is still time to act. This required unioning the 990-N e-Postcard
   file with the Form 990 e-file index, without which every small filer in the country looks
   delinquent.
3. **A packaging decision, not a data one.** `uvx grantcheck --ein 12-3456789` with no account, no
   key, and no 2-million-row download, because the index is sharded by EIN prefix and the tool
   fetches only the shard it needs. The data work is upstream's. The 60-second path is ours.

---

## What we contribute back

Commitments, with owners, not aspirations.

### 1. A tested parser for the four TEOS bulk files

The pipe-delimited TEOS files have real and undocumented failure modes: embedded pipes in
organization names, Latin-1 bytes in an ASCII file, inconsistent EIN zero-padding, fixed-width
space padding inside delimited fields, mixed line endings, and a CSV/pipe inconsistency between
the BMF distribution and the other three. Every project that touches these files rediscovers this
list.

We will factor our parser and its fixture suite into a standalone, separately installable package
and offer it to the Nonprofit Open Data Collective, under their governance if they want it. The
value is not the code, it is the fixture corpus of rows that have historically broken parsers.

**Status:** planned for the release after 1.0, once the fixture corpus has survived three monthly
ingests.

### 2. The EIN-to-UEI crosswalk, published under CC0

The hardest join in this tool is IRS EIN to SAM.gov Unique Entity ID, and it cannot be done by
lookup on public data. We infer it by name and state matching with a confidence score, and the
hosted companion at check.opengrants.io lets visitors confirm or correct their own organization's
match.

Confirmed pairs are worth more than our inference. We will publish the confirmed crosswalk as a
plain CSV under CC0, refreshed monthly, with no attribution requirement and no registration — and
we will publish it whether or not anyone uses our tool, because a public EIN-to-UEI crosswalk is
straightforwardly a public good and its absence is a small ongoing tax on the entire sector.

**Status:** ships with the hosted companion. This is the single most valuable thing this repo can
give back.

### 3. Upstream issues and pull requests

- Concordance gaps: any schema version or XPath we need and cannot resolve goes upstream as an
  issue with the offending filing attached, before we work around it.
- Data dictionary discrepancies: code values we observe in the live TEOS files that are not in the
  published IRS data dictionary get reported to the IRS TEOS contact and documented in
  `docs/research/data-sources.md` in the meantime.
- Where a bug we hit is really in an upstream project, the fix goes there first and we depend on
  the release. We do not carry local patches quietly.

### 4. Documentation the sector can use without the tool

`docs/research/data-sources.md` is written to be useful to somebody who never runs `grantcheck` —
it is a field guide to four badly documented federal datasets and the specific ways they mislead.
It is Apache 2.0 like the rest of the repo. Copy it.

---

## Contribution log

Upstream issues and pull requests filed by this project, newest first. Every entry links the
upstream item and the local commit that depends on it.

| Date | Upstream project | Item | Status |
|---|---|---|---|
| — | — | *No entries yet. First entries expected during the initial ingest build.* | — |
