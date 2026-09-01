# check.opengrants.io — Hosted Architecture

The hosted companion to `grantcheck`. Same checks, same data, same vintages, same disclosure, in a
browser with nothing to install — and, more importantly, a permanent citable page per EIN that
search engines and language models can read.

**Platform:** Cloudflare Pages + Pages Functions.
**Rendering:** edge server-side rendering per EIN, cached.
**Backing store:** D1, holding the Business Master File, Publication 78, the Automatic Revocation
List, the 990-N e-Postcard file, the filing index, and the SAM.gov snapshot — roughly 2 million
organization rows.

---

## 1. Why Cloudflare, and why not static

### Why Cloudflare rather than Netlify

R2 has no egress fees, and this program publishes derived public datasets that we actively want
people to pull. On a bandwidth-metered host, the program working as designed becomes a bill that
scales with exactly the adoption we are trying to create. Workers requests are cheap and R2 egress
is zero, so success here is close to free. Realistic spend for this site at launch scale is inside
the $5/month Workers Paid plan, with R2 storage at roughly $0.015/GB-month.

### Why not a static site

This is the decision most likely to be got wrong, so it is written down first.

Cloudflare Pages allows **20,000 files per deployment on the free plan and 100,000 on paid**. There
are roughly 1.4 million 501(c)(3) organizations in the Business Master File. Pre-rendering one page
per organization exceeds the paid ceiling by more than an order of magnitude, and even a fraction
of it would blow the 20-minute build timeout and destroy the deploy loop.

So: **render on demand at the edge, from D1, and cache the result.** Only these are pre-rendered at
build time:

- the landing page and the check form
- `/methodology`, `/about`, `/data`, `/llms.txt`, `/robots.txt`
- the eleven `/checks/{check_id}` explainer pages
- the state and NTEE browse indexes, which exist to give crawlers a path into the long tail

Everything keyed on an EIN is edge-rendered. This is not a performance compromise — a cached edge
render is served from the same colo as a static asset, and a cold render is a single indexed D1
lookup.

---

## 2. Routes

| Route | Rendering | Purpose |
|---|---|---|
| `/` | Static | Landing page and the EIN entry form. |
| `/ein/{ein}` | Edge SSR, cached | **The canonical entity page.** Hyphenated EIN, e.g. `/ein/27-1067272`. |
| `/ein/{ein9}` | 301 | Unhyphenated form redirects to canonical. |
| `/ein/{ein}/{slug}` | 301 | Any slug variant redirects to canonical. Never let two URLs serve one organization. |
| `/check` | Edge, no cache | Form target. Resolves name or EIN input, then 302s to the canonical `/ein/{ein}`. Never renders a result itself — results must live at a shareable URL. |
| `/search?q=` | Edge SSR, short cache | Name lookup, `noindex`. Exists to find an EIN, not to be a directory. |
| `/checks/{check_id}` | Static | Plain-English explainer per check. High-intent SEO surface: "what does automatic revocation of exemption mean." |
| `/state/{XX}` | Edge SSR, long cache | Crawl path into the long tail, paginated. |
| `/ntee/{code}` | Edge SSR, long cache | Same. |
| `/api/check/{ein}` | Edge, cached | JSON, identical schema to `grantcheck --format json`. CORS open, no key. |
| `/api/crosswalk.csv` | R2 redirect | The published EIN-to-UEI crosswalk, CC0. |
| `/sitemap.xml` | R2 | Sitemap index. |
| `/sitemaps/{n}.xml.gz` | R2 | 50,000 URLs per chunk. |
| `/llms.txt` | Static | What the dataset is, how to use it, how to cite it. |
| `/methodology` | Static | Sources, vintages, known limitations, the disclosure. |

**EIN validation happens before D1 is touched.** Anything that is not nine digits after
normalization returns 400 from the edge with no database round trip. This is the whole abuse
surface of the site.

An EIN that validates but is not in the index gets a real 404 page with a real explanation —
churches and government instrumentalities are often legitimately absent, and newly recognized
organizations take a cycle or two to appear. `noindex` on that page; do not generate 1.4 billion
crawlable not-found URLs.

---

## 3. D1 schema

D1 has a size ceiling per database (**VERIFY** the current limit on your plan before ingest; if the
dataset does not fit, shard across databases by EIN prefix and route in the Function — the prefix
partition is the same one the CLI index uses, so the two stay conceptually aligned).

Keep rows lean. Store codes, not expanded labels; expansion happens in the render layer from a
table shipped in the Function bundle.

```sql
-- One row per organization. The spine.
CREATE TABLE orgs (
  ein            TEXT PRIMARY KEY,        -- 9 digits, zero-padded, no hyphen
  name           TEXT NOT NULL,
  sort_name      TEXT,
  city           TEXT,
  state          TEXT,
  zip            TEXT,
  subsection     TEXT,                    -- '03' = 501(c)(3)
  classification TEXT,
  affiliation    TEXT,
  group_ex       TEXT,                    -- group exemption number; non-zero = subordinate
  ruling         TEXT,                    -- YYYYMM
  foundation     TEXT,
  status         TEXT,                    -- '01' = unconditional exemption
  filing_req     TEXT,
  pf_filing_req  TEXT,
  ntee           TEXT,
  deductibility  TEXT,
  asset_amt      INTEGER,
  revenue_amt    INTEGER,
  vintage        TEXT NOT NULL            -- BMF vintage, YYYY-MM-DD
);
CREATE INDEX idx_orgs_state_name ON orgs(state, name);
CREATE INDEX idx_orgs_ntee       ON orgs(ntee);
CREATE INDEX idx_orgs_name       ON orgs(name);

-- Publication 78 listing. Absent row = not listed, which is not the same as revoked.
CREATE TABLE pub78 (
  ein      TEXT PRIMARY KEY,
  name     TEXT,
  city     TEXT,
  state    TEXT,
  country  TEXT,
  codes    TEXT NOT NULL,                 -- raw status codes, comma separated
  vintage  TEXT NOT NULL
);

-- Automatic Revocation List. Presence does NOT mean currently revoked.
CREATE TABLE revocations (
  ein                TEXT PRIMARY KEY,
  name               TEXT,
  dba                TEXT,
  city               TEXT,
  state              TEXT,
  exemption_type     TEXT,
  revocation_date    TEXT,                -- effective, retroactive
  posting_date       TEXT,                -- when the IRS published it
  reinstatement_date TEXT,                -- populated = back in good standing
  vintage            TEXT NOT NULL
);

-- Filing recency: the UNION of the 990 e-file index and the 990-N e-Postcard file.
-- Building this from the e-file index alone makes every small filer look delinquent.
CREATE TABLE filings (
  ein             TEXT NOT NULL,
  tax_period_end  TEXT NOT NULL,          -- YYYY-MM-DD
  return_type     TEXT NOT NULL,          -- 990, 990EZ, 990PF, 990N
  filed_date      TEXT,                   -- null for 990-N
  amended         INTEGER DEFAULT 0,
  govt_grants_amt INTEGER,                -- Form 990 Part VIII line 1e, null where unavailable
  source_vintage  TEXT NOT NULL,
  PRIMARY KEY (ein, tax_period_end, return_type)
);
CREATE INDEX idx_filings_ein ON filings(ein, tax_period_end DESC);

-- SAM.gov public-tier snapshot, keyed on UEI.
CREATE TABLE sam_entities (
  uei                TEXT PRIMARY KEY,
  legal_name         TEXT NOT NULL,
  name_norm          TEXT NOT NULL,       -- normalized for matching
  city               TEXT,
  state              TEXT,
  registration_status TEXT,
  expiration_date    TEXT,
  cage               TEXT,
  purpose            TEXT,                -- assistance / contracts / both
  vintage            TEXT NOT NULL
);
CREATE INDEX idx_sam_name_state ON sam_entities(state, name_norm);

-- The hardest join in the tool. EIN cannot be looked up on the SAM public tier,
-- so this is inferred and then corrected by humans.
CREATE TABLE ein_uei_crosswalk (
  ein        TEXT NOT NULL,
  uei        TEXT NOT NULL,
  confidence REAL NOT NULL,               -- 0.0 - 1.0
  method     TEXT NOT NULL,               -- 'name_state' | 'confirmed' | 'usaspending'
  confirmed_at TEXT,
  PRIMARY KEY (ein, uei)
);
CREATE INDEX idx_crosswalk_ein ON ein_uei_crosswalk(ein, confidence DESC);

-- Prior single audit submissions from the Federal Audit Clearinghouse.
-- Absence means "no single audit on record", never "under the threshold".
CREATE TABLE fac_submissions (
  ein         TEXT NOT NULL,
  fiscal_year INTEGER NOT NULL,
  report_id   TEXT,
  vintage     TEXT NOT NULL,
  PRIMARY KEY (ein, fiscal_year)
);

-- Single source of truth for what the site is currently serving.
CREATE TABLE dataset_vintage (
  dataset     TEXT PRIMARY KEY,           -- 'bmf' | 'pub78' | 'revocation' | 'epostcard'
                                          -- | 'efile_index' | 'sam' | 'fac'
  vintage     TEXT NOT NULL,
  source_url  TEXT NOT NULL,
  row_count   INTEGER,
  ingested_at TEXT NOT NULL
);
```

The **`dataset_vintage` table is the cache key source.** It is read once per isolate, cached in
memory, and its concatenated values form the `v` parameter on every cache key. A new ingest changes
those values and the entire edge cache invalidates in one step, with no purge API call and no TTL
guessing.

---

## 4. Ingest

A GitHub Actions workflow on a monthly schedule, plus manual dispatch. It runs in CI, not on
Cloudflare — this is a batch job over hundreds of megabytes and it has no business inside a Worker.

1. **Fetch.** Scrape the two IRS landing pages for current file links, compare against pinned
   defaults, fail loudly on a mismatch. Download the four TEOS files, the e-file index CSVs, the
   SAM.gov public entity extract, and the FAC submission list.
2. **Parse and normalize.** The same library the CLI uses, imported, not reimplemented. Quarantine
   malformed rows, count them, fail the run if the quarantine rate exceeds a threshold.
3. **Match.** Run the EIN-to-UEI inference over the SAM snapshot. Never overwrite a row whose
   `method` is `confirmed` — human corrections outrank inference permanently.
4. **Build.** Emit a local SQLite database, then the D1 import files.
5. **Load.** `wrangler d1 import` in chunks. Two million rows in one file will time out; chunk at
   roughly 50,000 statements. Load into a new set of tables, then swap by renaming inside a single
   transaction, so the site never serves a half-loaded table.
6. **Update `dataset_vintage` last.** This is the commit point. Until it changes, the edge is still
   serving the previous vintage from cache, consistently.
7. **Regenerate the sitemap chunks** and write them to R2.
8. **Publish the CLI index shards** to R2 and mirror them to a GitHub release, from the same build,
   so the CLI and the site can never disagree about what a vintage contains.
9. **Publish the crosswalk CSV** to R2.
10. **Smoke test.** Fetch a fixed list of known EINs from the live site and assert on the rendered
    facts. A failing smoke test rolls back by reverting `dataset_vintage`.

The ingest must be idempotent and re-runnable. It rebuilds; it never patches.

---

## 5. Caching

The underlying data changes monthly at best. Treating it as fresh-by-the-second is how the request
bill grows for no benefit.

**Cache key includes the dataset vintage**, so a new ingest invalidates everything cleanly rather
than relying on expiry:

```
https://check.opengrants.io/ein/27-1067272?v=<bmf>.<pub78>.<rev>.<epostcard>.<sam>
```

The `v` parameter is constructed server-side from `dataset_vintage` and stripped before rendering.
It never appears in a link, in the canonical tag, or in the sitemap.

| Page class | Header |
|---|---|
| Pure IRS-derived entity page | `Cache-Control: public, max-age=0, s-maxage=604800, stale-while-revalidate=86400` (7 days) |
| Entity page with OpenGrants enrichment | `s-maxage=86400, stale-while-revalidate=3600` (24 hours) |
| Static explainer, methodology, landing | `s-maxage=86400`, long browser cache on hashed assets |
| `/search` | `s-maxage=300`, `noindex` |
| `/api/check/{ein}` | Same as its page class, plus `Access-Control-Allow-Origin: *` |

**Serve stale while revalidating, always.** A 990 figure four hours out of date is better than a
spinner, and every page states its vintage anyway.

Live SAM.gov lookups and OpenGrants enrichment happen behind `waitUntil` where possible and are
never allowed to block the first byte. If either is slow or failing, the page renders from the
snapshot with the snapshot's date on it. **The core report must render with every optional
upstream down.**

---

## 6. SEO and GEO

This is where the category-ownership objective actually gets served. The repository does not rank.
These pages do.

**Server-rendered facts in the initial HTML response.** No client-side fetching for primary
content — not for the check results, not for the vintages, not for the organization name. A
crawler that runs no JavaScript must see the complete answer. This is non-negotiable and it is the
reason the whole site is edge SSR.

**schema.org structured data on every entity page.** JSON-LD, `NGO` (a subtype of `Organization`)
with:

- `name`, `alternateName` from the BMF sort name
- `taxID` — the EIN, the property that makes the page machine-joinable
- `identifier` — the UEI where a confirmed crosswalk row exists
- `address` as `PostalAddress` (labelled as the IRS mailing address, which is what it is)
- `nonprofitStatus` — `NonprofitType501c3` where applicable
- `url` set to the canonical
- `sameAs` linking the IRS Tax Exempt Organization Search record and the sibling portfolio pages

Plus a `Dataset` block on `/data` and `FAQPage` markup on each `/checks/{check_id}` explainer,
because those pages exist to answer a question verbatim.

**One canonical URL per entity, keyed on the hyphenated EIN.** `/ein/27-1067272`. Every variant
301s. `<link rel="canonical">` on every render, including the ones reached by redirect.

**Sitemap index, chunked at 50,000 URLs per file**, generated at ingest time, gzipped, served from
R2. Roughly 1.4M 501(c)(3) URLs, so about 28 chunks, plus the static and browse pages. Include
`<lastmod>` from the organization's own data vintage rather than the build date, so recrawls are
targeted.

**`llms.txt` at the root.** What the dataset is, which federal sources it derives from, the vintage
policy, the disclosure, the citation format we would like used, and a pointer to the JSON API and
the CC0 crosswalk. Cheap to write and increasingly how models decide what a site is for.

**Every page states its source and vintage inline**, in visible text, not only in a tooltip or a
meta tag: "Exempt status from the IRS Exempt Organizations Business Master File published
2026-08-11." Pages that show their work get cited. Pages that assert bare numbers do not. Use
`<time datetime="...">` so the dates are machine-readable.

**Answer-shaped structure for generative engines.** Each entity page opens with an H1 naming the
organization and the EIN, then a single self-contained paragraph that states the readiness
conclusion, the reason, and the vintage — written so it can be lifted whole and still be correct
and attributed. The check explainer pages use the question as the H1 verbatim ("What does automatic
revocation of exemption mean?") and answer it in the first forty words.

**Cross-link the portfolio.** Every entity page links to the same EIN on `funders.opengrants.io`,
`awards.opengrants.io`, and `desk.opengrants.io` where a record exists. Five sites that reference
each other read as one authoritative body of work rather than five orphans.

**The disclosure appears on every page that reports on an organization**, in the body, not in a
footer nobody reads:

> This is informational only, derived from public data on the dates shown. It is not an eligibility determination, and not legal, tax, or accounting advice. Verify against the official source before relying on it.

---

## 7. Privacy

All of this data is already public. That is not a reason to be careless with it.

- No account, no login, no cookie for the core experience.
- No profile of who looked up which EIN. Request logs are ordinary web logs with standard
  retention; nothing joins an IP or session to an EIN in any durable store.
- Analytics is Cloudflare Web Analytics — no cookie, no cross-site identifier — or nothing.
- Only SAM.gov public-tier data is ever fetched or stored. No sensitive-tier fields, ever.
- The UEI confirmation flow stores the confirmed pair and a timestamp. It does not store who
  submitted it.
- Organizations can request removal of their page. There is no legal obligation to honour it for
  public federal records, and we honour it anyway, with a `noindex` and a tombstone that still
  links the official IRS record.

---

## 8. DNS

`check.opengrants.io` is a subdomain of `opengrants.io`, whose DNS is managed externally rather
than at the registrar's default.

1. **Confirm who holds the `opengrants.io` zone before starting.** This is the step most likely to
   sit blocked for a day, and it is the only step in the whole launch that cannot be unblocked by
   working harder.
2. Create the Pages project and note its `*.pages.dev` hostname.
3. Add the custom domain `check.opengrants.io` in the Pages project. Cloudflare issues a
   validation record.
4. In the zone, add the `CNAME` for `check` pointing at the `pages.dev` hostname, plus the
   validation record.
5. Wait for the certificate. Verify HTTPS resolves and that `http://` 301s to `https://`.
6. Verify the apex and `www` are untouched.

---

## 9. Launch checklist

Everything must be true before the site is linked from the README.

**Correctness**

- [ ] Ten known EINs render correct facts, verified by hand against the IRS Tax Exempt Organization
      Search and SAM.gov. Include at least one revoked-then-reinstated organization, one group
      exemption subordinate, one private foundation, one 990-N-only small filer, and one
      organization with no SAM registration.
- [ ] A group exemption subordinate is **not** reported as a Pub 78 problem.
- [ ] A reinstated organization is **not** reported as currently revoked.
- [ ] Every fact on the page carries a visible source and vintage.
- [ ] The disclosure is present on every entity page.
- [ ] `/api/check/{ein}` returns byte-identical facts to `grantcheck --format json` at the same
      vintage, verified in CI.

**Infrastructure**

- [ ] `dataset_vintage` populated and matching what is rendered.
- [ ] Cache keys include vintage; a vintage bump demonstrably invalidates.
- [ ] Rendering succeeds with the SAM.gov API and the OpenGrants API both unreachable.
- [ ] Cold render under 400 ms at the edge; cached under 50 ms.
- [ ] EIN validation rejects malformed input before any D1 query.
- [ ] Ingest smoke test wired to roll back on failure.

**SEO and GEO**

- [ ] `curl` on an entity page shows all facts in the HTML with JavaScript never executed.
- [ ] JSON-LD validates and includes `taxID`.
- [ ] Canonical tag correct on both direct and redirected requests.
- [ ] Sitemap index reachable, chunks under 50,000 URLs, gzipped, correct `lastmod`.
- [ ] `robots.txt` allows the entity pages and disallows `/search` and `/check`.
- [ ] `llms.txt` live at the root.
- [ ] The eleven check explainer pages are live with `FAQPage` markup.
- [ ] Cross-links to the sibling portfolio sites resolve or are omitted, never dead.
- [ ] Google Search Console and Bing Webmaster verified; sitemap submitted.

**Launch**

- [ ] DNS live, HTTPS valid, `http` redirects.
- [ ] README links to the site; the site links to the repository.
- [ ] `/methodology` names every source with its cadence and its known limitations.
- [ ] The CC0 crosswalk CSV is published and linked.
- [ ] A rollback is a `dataset_vintage` revert plus a Pages rollback, and someone has done it once
      in staging.
