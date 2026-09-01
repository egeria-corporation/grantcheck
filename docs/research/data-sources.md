# Data Sources

Everything `grantcheck` prints comes from one of the sources below. This document is the
authoritative record of what each one contains, how often it changes, and how it lies to you.

Facts marked **VERIFY** were carried over from the program research dossier or inferred from
documentation and must be confirmed against the live source before they appear in public copy or
are relied on in code. Verification date for the rest: 2026-08-30.

A note on the whole category: the IRS publishes these files as flat text on a monthly cadence with
no changelog, no schema version, and no deprecation notice. Columns move. Code values appear that
are not in the data dictionary. A file will occasionally be reposted mid-month with different
contents under the same name. Design for that, and test against real bytes rather than assumed
shapes.

---

## 1. IRS Tax Exempt Organization Search (TEOS) bulk downloads

**Landing page:** https://www.irs.gov/charities-non-profits/tax-exempt-organization-search-bulk-data-downloads

This page is the primary dependency of the entire tool. It hosts four datasets plus a data
dictionary and the TEOS annotated forms. All four are pipe-delimited (`|`) ASCII text, distributed
inside ZIP archives, refreshed monthly.

**Do not hardcode the file URLs without a fallback.** The IRS has moved these between
`apps.irs.gov/pub/epostcard/` and `www.irs.gov/pub/irs-soi/` historically. The ingest job should
parse the landing page for the current links, compare against the pinned defaults, and fail loudly
on a mismatch rather than silently fetching a stale mirror.

### Verified against the real files, 2026-09-01

The four datasets were downloaded and parsed end to end on 2026-09-01. Where this document
previously described the formats from documentation rather than from the bytes, it was wrong in
the ways below. These are now encoded in `src/grantcheck/ingest/teos.py` and its tests.

| | delimiter | header | fields | rows |
|---|---|---|---|---|
| EO Business Master File (`eo1`–`eo4.csv`) | comma | **yes** | 28 | 1,957,340 |
| Publication 78 | pipe | **none** | 6 | 1,412,318 |
| Automatic Revocation | pipe | **none** | 12 | 1,246,171 |
| Form 990-N e-Postcard | pipe | **none** | 26 | 1,543,373 |

1. **The three pipe-delimited files have no header row at all**, and each opens with two blank
   lines. The guidance below to "read the header, map names to indices" applies only to the BMF.
   For the other three, parsing is positional and the field count is the only structural check.
2. **The BMF uses RFC 4180 quoting**, which this document did not say. Twenty-nine rows in the
   2026-08-10 vintage carry a comma inside a quoted field, for example
   `"NORTH COUNTRY HOSPITAL & HEALTH CENTER,INC"`. It must be read with a real CSV parser.
   `split(",")` shifts those rows into plausible-looking nonsense.
3. **Embedded pipes are real.** Exactly five rows in the 2026-08-31 e-Postcard file carry a
   literal pipe inside the website or officer field, e.g. `Home | Unity Foundation (...)`. There
   is no quoting convention in that format, so they cannot be recovered and are quarantined.
   Every one of them is committed as a fixture.
4. **All four files decoded as clean UTF-8** in this vintage — no Latin-1 or cp1252 bytes were
   found. Keep decoding defensively anyway, but the warning below is not currently observed.
5. **The revocation list is 1,246,171 rows, not ~800,000**, and **181,259 of them carry a
   reinstatement date** — roughly one in seven. Reading list membership as "currently revoked"
   would wrongly report every one of those as ineligible.
6. **`AFFILIATION`, not `GROUP`, distinguishes a subordinate from a central organization.** Both
   carry the group exemption number. Measured across all 1.6M subsection-03 rows against the
   2026-08-11 Publication 78 file:

   | `AFFILIATION` | meaning | count | listed in Pub 78 |
   |---|---|---|---|
   | 9 | subordinate | 237,871 | **0.0%** |
   | 7 | intermediate | 32 | **0.0%** |
   | 6 | central organization | 1,844 | 99.4% |
   | 8 | — | 716 | 99.6% |
   | *(no group)* | independent | 1,394,326 | 99.7% |

   So absence from Publication 78 is expected for `AFFILIATION` 7 and 9, and is a real signal for
   everything else. Suppressing the check on `GROUP` alone would wrongly excuse ~2,560 central
   organizations that genuinely should be listed.
7. **The BMF header carries 28 columns**, including `ACTIVITY`, `ASSET_CD`, `INCOME_CD`, and
   `ACCT_PD`, which the column table below omits.

### Cross-check against ProPublica, 2026-09-01

Twenty subsection-03 organizations sampled across eight shards of the built index and compared
against the ProPublica Nonprofit Explorer API, as section 10 of the build prompt requires.

**Subsection agreed 20 out of 20.** Every disagreement was on the tax period, and the pattern is
systematic rather than random:

- Our value is **never older** than ProPublica's.
- It is ahead by exactly **12 months in 4 cases and 24 months in 6**, plus one outlier at 156.
- The **fiscal month-of-year matches in every pair** — same year-end, a different year's return.

The two fields measure different things, which is the whole point. Ours is the BMF `TAX_PERIOD`,
the most recent return the IRS has **processed**. ProPublica's `filings_with_data` reports the most
recent return it has **parsed XML for**, and XML publication trails BMF processing by one to two
filing cycles.

This is confirmation rather than a defect, and it is why `TAX_PERIOD` is labelled a fallback, never
rendered as a filing date, and capped at a warning in `filing_recency`. Reading it as a filing date
would put us one to two years optimistic — the safe direction for a delinquency count, since it
cannot manufacture a false accusation, but wrong nonetheless.

**The 156-month outlier is trap 3 seen from the other side.** Western Forest Insect Work Conference
(EIN 93-0078709) shows 2012 at ProPublica and 2025 in the BMF. ProPublica's `filings_with_data`
covers parsed XML only, and Form 990-N e-Postcard filings are not in it. An organization that
switched to the 990-N simply stops appearing there. That is exactly why filing recency has to union
the e-Postcard file rather than trusting an XML-derived source alone.

---

### Cross-cutting gotchas for all four files

- **Delimiter is a pipe, and organization names contain pipes.** Rarely, but they do, along with
  quotes and non-ASCII bytes. There is no quoting convention. A naive `str.split("|")` produces a
  shifted row and, because the columns after the shift are still parseable, a plausible-looking
  wrong answer. Validate column count per row and quarantine rows that do not match, rather than
  discarding or best-guessing them. Count the quarantine and alert if it moves.
- **Encoding is not UTF-8.** These are ASCII files that in practice contain Latin-1 and occasional
  cp1252 bytes in organization names. Decode with `latin-1` and normalize, or decode UTF-8 with
  `errors="replace"` and accept mangled names. Do not let a decode error kill an ingest of 1.9M
  rows.
- **EINs have no hyphen and are not zero-padded consistently.** Some files carry a 9-character
  string, some drop a leading zero. Normalize every EIN to a 9-digit zero-padded string on ingest
  and format for display only at the output boundary. Every EIN accepted from a user should be
  normalized the same way, so `27-1067272`, `271067272`, and `27 0125367` are one key.
- **Fixed-width padding.** Fields are frequently space-padded to a fixed width inside the
  pipe-delimited row. Strip every field. A trailing space on a state code is a silent join failure.
- **Header rows are present but not guaranteed stable.** Read the header, map names to indices,
  and assert the expected set is present. Never index by position alone.
- **Monthly reposts are not diffs.** Each file is the complete current state. Ingest is a rebuild,
  not an update. This is a feature — it means the index is always internally consistent, and
  vintage is a single scalar.
- **Line endings vary.** CRLF and LF both appear, sometimes in the same file.

### 1.1 Exempt Organizations Business Master File (EO BMF)

The master roster of organizations recognized as exempt. This is the spine of the index.

- **Distribution:** four regional CSV files, `eo1.csv` through `eo4.csv`, plus per-state files
  (`eo_ca.csv`, `eo_ny.csv`, …) and an international file. The regional split is by state groups.
  **VERIFY** the exact current URLs; the historical pattern is
  `https://www.irs.gov/pub/irs-soi/eo1.csv` … `eo4.csv`.
- **Format:** comma-delimited CSV in the `eoN.csv` distribution, unlike the other three TEOS files
  which are pipe-delimited. This inconsistency is real and has caught people. **VERIFY** on each
  ingest by sniffing the first line.
- **Row count:** approximately 1.9 million across all regions (research dossier, 2026-08-30). Of
  those, roughly 1.4M are subsection 03 — the 501(c)(3) universe this tool cares about.
- **Cadence:** monthly, typically posted in the second week.

**Columns** (the ones `grantcheck` uses, in the order they appear):

| Column | Meaning | Notes |
|---|---|---|
| `EIN` | 9 digits, no hyphen | Primary key. Zero-pad. |
| `NAME` | IRS legal name | ALL CAPS. Frequently truncated. Rarely matches the SAM.gov legal business name exactly. |
| `ICO` | "in care of" name | Often a former treasurer. Do not display. |
| `STREET`, `CITY`, `STATE`, `ZIP` | Mailing address | Mailing, **not** principal place of business. An organization operating in Ohio can have a Delaware registered-agent address here. Do not present this as a location. |
| `GROUP` | Group exemption number (GEN) | Non-zero means this organization is a subordinate under a group ruling. Critical — see gotchas below. |
| `SUBSECTION` | 501(c) subsection | `03` is 501(c)(3). Two-character, zero-padded. |
| `AFFILIATION` | Central/subordinate/independent | Corroborates `GROUP`. |
| `CLASSIFICATION` | Sub-classification within the subsection | Multi-digit concatenation, not a single code. Parse carefully or do not use it. |
| `RULING` | Ruling date, `YYYYMM` | Six digits, no day. Month precision is all you get; print it as `2010-02`, never as a full date. |
| `DEDUCTIBILITY` | Contributions deductible code | Overlaps with but is not identical to the Pub 78 status code. Prefer Pub 78 for the deductibility check. |
| `FOUNDATION` | Foundation classification code | Distinguishes private foundations from public charities and identifies churches, schools, hospitals, and supporting organizations. **Source the code table from the published EO BMF data dictionary and commit it as a fixture. Do not hand-write it from memory — it is exactly the sort of table that is 90% right and wrong in the one row that matters.** |
| `ORGANIZATION` | Corporation / trust / association / co-operative | |
| `STATUS` | Exemption status code | `01` is unconditional exemption. Other values exist for conditional exemption and for organizations terminating private foundation status. **VERIFY** the full table against the data dictionary. |
| `TAX_PERIOD` | Latest tax period on file, `YYYYMM` | See the filing-recency section — this is *not* a filing date and using it as one is the most common mistake with this file. |
| `FILING_REQ_CD` | Which 990 the organization must file | Values distinguish full 990, 990-EZ eligibility, churches with no filing requirement, and others. **VERIFY** the table. Organizations with no filing requirement must never be flagged as delinquent. |
| `PF_FILING_REQ_CD` | 990-PF filing requirement | Corroborates private foundation status. |
| `ASSET_AMT`, `INCOME_AMT`, `REVENUE_AMT` | From the latest return on file | In whole dollars. Frequently zero or blank for small filers. Do not build the audit screen on these. |
| `NTEE_CD` | National Taxonomy of Exempt Entities code | Four characters, e.g. `K31`, `W99`. See gotchas. |
| `SORT_NAME` | Alternate/DBA name | Sometimes the name the public knows. Useful as a secondary match key for SAM.gov reconciliation. |

**Gotchas specific to the BMF:**

- **`TAX_PERIOD` is not a filing date.** It is the period of the most recent return the IRS has
  processed, at month precision, and it lags actual filing by anywhere from weeks to more than a
  year. Deriving "years since last filing" from this column will tell an organization that filed
  four months ago that it is two years delinquent. Use the Form 990 e-file index and the 990-N
  file for filing recency, and use `TAX_PERIOD` only as a fallback with the lag stated in the
  output.
- **Group exemptions.** Roughly a fifth of the rows are subordinates under a group ruling — local
  chapters of national organizations, parishes, lodges, councils, PTAs. A subordinate has a real
  EIN, real exempt status, and a non-zero `GROUP`, but its exemption flows from the central
  organization's ruling. Subordinates behave differently in Pub 78 (see below) and often have no
  independent 990 filing history because they are covered by a group return. Never report a
  subordinate as delinquent or non-deductible without checking `GROUP` and `AFFILIATION` first.
  This is the single largest source of false alarms in a tool like this.
- **NTEE codes are stale and incomplete.** The IRS assigns NTEE at recognition and rarely updates
  it. A meaningful share of rows have no NTEE code at all, and among those that do, the code often
  describes what the organization said it would do in its Form 1023 rather than what it does now.
  Present it as "the classification the IRS has on file," which is what it is. NCCS maintains an
  improved taxonomy (NTEEV2) worth tracking as a future enrichment.
- **Churches.** Churches, their integrated auxiliaries, and conventions of churches are exempt
  without applying and without filing. Many are absent from the BMF entirely, and those present
  often have no filing requirement. An absent church is not a revoked church. If `grantcheck`
  cannot find an EIN at all, the "not found" message must say this.
- **Delay to recognition.** A newly recognized organization can take one to two monthly cycles to
  appear. A determination letter dated three weeks ago will not be in the file. Say so on the
  not-found path.
- **Government entities and instrumentalities** are frequently eligible applicants for federal
  programs and are largely absent from the BMF. Same treatment as churches on the not-found path.

### 1.2 Publication 78 Data

The list of organizations eligible to receive tax-deductible charitable contributions.

- **URL pattern:** `https://apps.irs.gov/pub/epostcard/data-download-pub78.zip` **VERIFY**
- **Archive contents:** a single pipe-delimited text file. **VERIFY** the inner filename each
  ingest rather than assuming it.
- **Row count:** approximately 1.3 million. **VERIFY**
- **Last updated at dossier verification:** 2026-04-14. **Cadence:** monthly.

**Columns:** `EIN | Legal Name | City | State | Country | Deductibility Status Codes`

The status codes are short strings, and multiple codes can appear separated by a comma for a
single organization. Expected values include `PC` (public charity), `POF` (private operating
foundation), `PF` (private foundation), `EO` (a listing for which deductibility is limited),
`LODGE` (domestic fraternal societies), `FORGN` (foreign organization), `SO` / `SONFI` / `SOUNK`
(supporting organizations of various types), `GROUP` (a group ruling listing), and `UNKWN`.
**VERIFY the full set and the exact meanings against the TEOS data dictionary and commit that
table as a fixture.** Print the expansion, never the raw code.

**Gotchas:**

- **Group rulings appear as one row, not thousands.** An organization covered by a group exemption
  is generally *not* individually listed in Pub 78; the central organization is listed with a
  `GROUP` code and the subordinates are covered by it. So a real, fully compliant local chapter
  will come back "not listed in Pub 78." This is the highest-severity false positive in the tool.
  **Rule: never report Pub 78 absence as a problem when the BMF row has a non-zero `GROUP`.**
  Report it as "covered by group exemption ruling GEN 1234; individual Pub 78 listing not
  expected."
- **Pub 78 and the BMF disagree.** They are generated from the same underlying system on different
  schedules and it is normal for an organization to be current in one and absent from the other
  for a cycle. Report both, with both vintages, rather than reconciling them into a single verdict.
- **Only the address city and state are present**, no street. Name-and-state is the only join key
  available beyond the EIN.
- **Absence is not evidence of revocation.** Check the revocation list explicitly. There are
  several ways to be off Pub 78 without having been revoked.

### 1.3 Automatic Revocation of Exemption List

Organizations whose exemption was revoked under section 6033(j) for three consecutive years of
failing to file a required annual return or notice.

- **URL pattern:** `https://apps.irs.gov/pub/epostcard/data-download-revocation.zip` **VERIFY**
- **Format:** pipe-delimited text inside the archive.
- **Row count:** on the order of 800,000 and monotonically growing, since revoked organizations
  are never removed from the list — reinstatement is recorded as an additional date on the same
  row. **VERIFY**
- **Last updated at dossier verification:** 2026-04-14. **Cadence:** monthly.

**Columns:** `EIN | Legal Name | Doing Business As | Address | City | State | ZIP | Country |
Exemption Type | Revocation Date | Revocation Posting Date | Exemption Reinstatement Date`
**VERIFY** the exact header text and order.

**Gotchas — this is the check most likely to produce a wrong and alarming answer:**

- **Presence on the list does not mean currently revoked.** If `Exemption Reinstatement Date` is
  populated and is on or after the revocation date, the organization has been reinstated and is in
  good standing. `grantcheck` must state this as "revoked 2019-05-15, reinstated 2020-11-15,
  currently in good standing" — a full history, not a red X. Getting this wrong tells a compliant
  organization that it cannot apply for federal money, which is the worst thing this tool could do.
- **Three distinct dates, and they mean different things.** The *revocation date* is the effective
  date, which is the filing due date of the third missed year and is therefore retroactive. The
  *revocation posting date* is when the IRS published it, typically several months later. The
  *reinstatement date* is the effective date of reinstatement, which may itself be retroactive to
  the revocation date under Rev. Proc. 2014-11. Print the effective dates and note the posting
  date, because the gap between them is where organizations discover they have been revoked for
  months.
- **Reinstated organizations receive a new determination letter but keep the same EIN.** Do not
  treat a reinstated organization as a different entity.
- **The revocation list and Pub 78 lag each other.** A recently reinstated organization may be on
  the revocation list and absent from Pub 78 in the same vintage. Report both facts and their
  dates rather than forcing a resolution.
- **Exemption type is not always 501(c)(3).** The list covers all revoked exempt organizations.
  Filter or label accordingly.

### 1.4 Form 990-N (e-Postcard) file

Most recent e-Postcard submissions from small organizations with gross receipts normally at or
under $50,000.

- **URL pattern:** `https://apps.irs.gov/pub/epostcard/data-download-epostcard.zip` **VERIFY**
- **Format:** pipe-delimited text.
- **Posted at dossier verification:** 2026-04-27. **Cadence:** monthly.

**Columns:** `EIN | Tax Year | Organization Name | Gross receipts under $50,000 indicator |
Terminated indicator | Tax Period Begin Date | Tax Period End Date` **VERIFY** exact header text.

**Why this file is load-bearing:** the majority of exempt organizations file the 990-N, and a
990-N filing is not in the Form 990 e-file XML index. If you build filing recency only from the
e-file index, every small organization in the country appears to have never filed anything, and
`grantcheck` will tell hundreds of thousands of compliant small nonprofits that they are about to
be auto-revoked. **The filing-recency check must union the 990-N file with the e-file index.** This
is the second-highest-severity correctness requirement in the tool.

**Gotchas:**

- The file contains the *most recent* submission per organization, not full history.
- The terminated indicator marks organizations that filed a final return. A terminated
  organization should be reported as terminated, not as delinquent.
- Tax year and tax period end date can disagree for fiscal-year filers. Use the period end date.

---

## 2. IRS Form 990 series e-file downloads

**Page:** https://www.irs.gov/charities-non-profits/form-990-series-downloads

- **Base URL pattern:** `https://apps.irs.gov/pub/epostcard/990/xml/{YEAR}/`
- **Naming:** `{YEAR}_TEOS_XML_##X.zip` for 2023–2026; `download990xml_{YEAR}_#.zip` for 2019–2020.
- **Coverage:** 2019 through 2026, with 2026 shipping monthly files. Each year ships an index CSV.
- **Cadence:** monthly. Latest posting noted by the IRS at dossier verification: 2026-04-20.

`grantcheck` needs two things from this source and deliberately nothing else:

1. **The index CSV per year**, which gives EIN, tax period, return type, and filing date without
   opening a single XML file. This is what powers the "most recent Form 990 on file" and "years
   since last filing" rows, unioned with the 990-N file. The index is small and cheap. Parse it and
   stop.
2. **One financial field** — the government grants amount, Form 990 Part VIII line 1e — for the
   single-audit screen. This does require reading XML.

**The hard part, and why we do not solve it ourselves:** the IRS has published hundreds of schema
versions since 2009 with inconsistent XPaths and no stable field naming. This is the entire moat of
the commercial products in this category. Use the
[IRS E-file Master Concordance File](https://nonprofit-open-data-collective.github.io/irs-efile-master-concordance-file/)
from the Nonprofit Open Data Collective to resolve the XPath for a given field across versions.
Vendor a pinned subset of the concordance covering only the fields we read, record the upstream
commit SHA next to it, and open an issue upstream if a version is missing rather than patching
around it locally.

**Gotchas:**

- Amended returns appear as additional filings for the same tax period. Take the latest filing
  date per (EIN, tax period), and surface that a return was amended rather than hiding it.
- Group returns filed by a central organization cover subordinates that will show no filings of
  their own. Same treatment as elsewhere: check `GROUP` before calling anything delinquent.
- The index CSV column names have changed across years. Map by header, assert presence, fail loudly.
- Paper filers exist and are not in the e-file data at all, though the population is now small.

---

## 3. SAM.gov Entity Management API

**Docs:** https://open.gsa.gov/api/entity-api/ · **Bulk extracts:**
https://open.gsa.gov/api/sam-entity-extracts-api/

Provides registration status, registration expiration date, Unique Entity ID, CAGE code, and
physical address. An active registration is a hard gate on every federal grant and contract, and an
expired one is the single most common avoidable disqualification in the federal system.

- **Auth:** an api.data.gov key, free from https://api.data.gov/signup/.
- **Tiers:** public and sensitive. **We use public only, always.** Sensitive-tier fields include
  taxpayer identification number and points of contact and are out of scope permanently — see
  `docs/NON-GOALS.md`.

**The structural problem, and the design consequence:**

> **You cannot look up a SAM.gov entity by EIN on the public tier.** The taxpayer identification
> number is a sensitive-tier field, so it is not available as a search parameter or in the public
> response. The public search keys are UEI, CAGE code, and legal business name. **VERIFY** against
> the current Entity Management API documentation before building, because this constraint shapes
> the whole SAM half of the tool.

This means the EIN-to-UEI link must be *inferred*, not looked up. The design:

1. Take the legal name and state from the IRS Business Master File, and the `SORT_NAME` alternate
   name where present.
2. Search SAM.gov by legal business name, filtered to that state.
3. Score candidates on normalized name similarity plus state and city agreement. Normalize
   aggressively — the BMF says `SECOND HARVEST OF SILICON VALLEY`, SAM.gov may say
   `Second Harvest Food Bank of Silicon Valley, Inc.`
4. Emit a match confidence as a first-class field in the output, and print it. Never present an
   inferred match as a certainty.
5. Let the user pin the match with `--uei`, which skips inference entirely.
6. On the hosted companion, let a visitor confirm or correct the match, and persist confirmed
   EIN-to-UEI pairs into a crosswalk that the CLI index picks up on the next build. This crowdsources
   the hardest join in the tool, and the resulting crosswalk should be published openly.

**Keyless operation.** The quickstart must work with no key, so the index carries a snapshot of
public-tier registration status, expiration, and UEI, labelled with the snapshot date. With
`SAM_API_KEY` set, the three SAM checks go live and are labelled as of the moment of the run.

> **Decided 2026-08-31 — bundle the snapshot. See `docs/program/DECISIONS.md`, D-001.** The index carries
> a derived subset of the SAM.gov Public Entity Extract: UEI, legal business name, state, city,
> registration status, registration expiration date, and registration purpose. Nothing above the
> public tier, ever. The extract is FOIA-releasable federal data and neither GSA API documents a
> redistribution restriction; a written clarification request to GSA runs in parallel with the
> build. `data/SOURCES.md` ships with the index naming the fields taken and the extract date.
>
> The rate limits are why. GSA gives a non-federal user with no SAM.gov role **ten Entity Management
> API requests per day** (1,000 with a role or a system account), verified at
> https://open.gsa.gov/api/entity-api/ on 2026-08-31. Ten lookups a day cannot support a client
> roster, so a live-only keyless path was never viable. A proxy endpoint holding our key was
> rejected outright and stays rejected: it would make an open source tool depend on our servers and
> would record which EINs users research.
>
> If GSA reopens this, the fallback is to degrade the three SAM checks to `unknown` without a
> user-supplied `SAM_API_KEY` — **not** a proxy.

**Gotchas:**

- Registration expiration is annual and renewal is not automatic. A registration in "Active"
  status expiring in 30 days is a warning, not a pass. Threshold the warning at 60 days.
- Entities can be registered for financial assistance only, for contracts only, or both. A
  grant-seeking organization needs the assistance purpose. Check it and say so.
- "Registration expired" and "registration not found" are different failures with different
  remedies. Never collapse them.
- The exclusions (debarment) dataset is separate from entity registration. Debarment is a genuine
  hard disqualification but the false-positive cost of a name-only match against the exclusions
  list is very high — accusing the wrong organization of being debarred is defamatory. **Do not
  check exclusions on an inferred name match. Only on a confirmed UEI, and even then, phrase it as
  a pointer to the official record.**
- API rate limits apply per key via api.data.gov. Cache and back off.

---

## 4. Federal Audit Clearinghouse

**API:** https://www.fac.gov/api/ · **Signup:** https://www.fac.gov/api/signup/ (free, by email)
· **Terms:** https://www.fac.gov/api/terms/

Built on PostgREST, so standard PostgREST filtering, pagination, and ordering apply. Contains
single audit submissions including the Schedule of Expenditures of Federal Awards (SEFA).

`grantcheck` uses FAC for one narrow purpose: **has this organization filed a single audit before,
and for which fiscal years.** An organization with a filing history is one that already knows it is
over the threshold; an organization with none that is showing large government grant revenue is
exactly the case the screen exists to catch.

**Gotchas:**

- **Coverage is partial by design.** Organizations below the threshold never file, so absence from
  FAC means "no single audit on record," never "under the threshold." Say the former.
- FAC records are keyed on EIN and UEI, and historical records may carry a DUNS number instead.
- The threshold changed. **$1,000,000 in federal awards expended per fiscal year, for fiscal years
  beginning on or after 2024-10-01, under the 2024 Uniform Guidance revision (2 CFR Part 200
  Subpart F). It was $750,000 previously.** Any historical comparison must apply the threshold in
  effect for that fiscal year, not today's.

---

## 5. The single-audit screen — what it actually measures

This deserves its own section because it is the check most likely to be misread.

The regulation is about **federal awards expended** in a fiscal year. `grantcheck` cannot see that
number. What it can see:

- **Form 990 Part VIII line 1e, "Government grants (contributions)"** — from the e-file XML. This
  mixes federal, state, and local money; it is contributions only, so government *contracts* and
  fee-for-service revenue are elsewhere on the return; and it is revenue recognized on an accrual
  basis, which is not the same thing as awards expended.
- **Form 990 Part XII lines 3a and 3b**, where the organization states whether it was required to
  undergo a single audit and whether it did. Self-reported, and it is answered wrong often enough
  that it is corroboration rather than truth. **VERIFY** the current part and line references
  against the Form 990 for the relevant tax year before wiring the XPaths, since the IRS renumbers.
- **FAC filing history**, above.
- **Direct federal awards from USAspending** (`POST /api/v2/search/spending_by_award`, no key
  required, https://api.usaspending.gov/) where a confirmed UEI exists. This is a floor, not a
  total, because pass-through subawards do not appear in the recipient's record — and pass-through
  is how most small nonprofits actually receive federal money.

So the check is a screen with four inputs, none of which is the regulated quantity. The output must
say so in the report itself, not only in the documentation. The wording currently used:

> Government grants reported: $X on the FY20NN Form 990. That is above the $1,000,000 single audit
> threshold. If any material portion of it is federal, a single audit is likely required. Confirm
> against your Schedule of Expenditures of Federal Awards.

The purpose of this check is to make a finance director go look. It is not to answer the question.
If the wording ever drifts toward answering the question, that is a bug — see
`docs/NON-GOALS.md`.

---

## 6. Sources deliberately not used

- **ProPublica Nonprofit Explorer** (https://projects.propublica.org/nonprofits/api) — excellent,
  no auth, and we use it for development cross-checks and optional gap-filling lookups only, never
  as a substitute for parsing the IRS source. Their
  [data terms](https://www.propublica.org/about/propublica-data-terms-of-use) govern
  redistribution; we redistribute nothing from it. Requests carry a descriptive User-Agent and are
  cached aggressively.
- **Grants.gov `search2`** — no auth required, but opportunity search is explicitly out of scope.
- **State charity registration databases** — not federal, not consistently published as data.
- **Scraped TEOS web interface** — never. See `docs/NON-GOALS.md`.

---

## 7. Vintage handling

Every dataset above has a vintage, and every printed fact carries the vintage of the dataset it
came from. The rules:

- Vintage is the publication date the source itself declares, not the date we downloaded it.
- The index manifest records a vintage per dataset, and the tool prints them all in the footer.
- The cache key for any derived artifact — local shard, hosted page, JSON response — includes the
  vintage set, so a new ingest invalidates cleanly rather than by TTL expiry.
- Where two datasets in the same report have different vintages, print both. Do not average them
  into a single "as of" date, and do not print the newest one as if it covered everything.
- `grantcheck refresh` reports what moved: which datasets changed vintage and how many rows
  differ. A dataset that has not moved in more than 45 days is a warning worth printing, because it
  usually means the IRS changed a URL.
