# Build Prompt: check.opengrants.io

You are building and launching the hosted companion to `grantcheck` on Cloudflare Pages +
Functions. Assume you have no context beyond this file and the files it tells you to read.

Build `prompts/01-build-core.md` first, or at least through its milestone M3. This site and the
command-line tool are fed by the same ingest and must never disagree about a fact or a vintage.

---

## 1. Mission

The command-line tool serves the consultant who already knows what they are looking for. This site
serves everyone else, and it serves the search engines and language models that people ask before
they ask a consultant.

Three jobs, in priority order:

1. **A permanent, citable page per organization** at `/ein/27-0125367` that states the federal
   readiness facts with their sources and publication dates, in server-rendered HTML that a crawler
   with no JavaScript can read completely.
2. **Answers to the questions people actually type** — "is my nonprofit eligible for federal
   grants," "check if 501c3 status was revoked," "do I need a single audit," "how do I know if my
   SAM registration is active." These are high-intent queries with no good free answer today.
3. **A zero-install path to the same report**, for the executive director who will never run a
   terminal command.

The repository does not rank. These pages do. That is the point of building them.

---

## 2. Read these first

1. `docs/program/HOSTING.md` — the platform decision, the file-count constraint that forces edge
   rendering, the caching strategy, and the SEO and GEO requirements. Binding.
2. `docs/hosted/architecture.md` — the full design for this site: routes, the D1 schema, the ingest
   pipeline, caching, SEO, privacy, DNS, and the launch checklist. **This prompt tells you how to
   build it; that document is the specification.** Where they differ, that document wins and you
   should flag the discrepancy.
3. `docs/program/CONVENTIONS.md` — the required disclosure, the OpenGrants integration rules, the
   data-honesty rules.
4. `docs/research/data-sources.md` — every dataset and the specific ways each will hand you a
   plausible wrong answer.
5. `prompts/01-build-core.md` — the check definitions, the `Report` object, and the JSON contract
   this site must match exactly.

---

## 3. Stack

- **Cloudflare Pages** with **Pages Functions** (`functions/` directory, file-based routing).
- **TypeScript, strict mode.** `pnpm`. `biome` for lint and format. `vitest` for tests.
- **Hono** for routing inside the Functions catch-all, per the program's TypeScript conventions.
- **D1** for the organization data. **R2** for sitemaps, the published CLI index shards, and the
  crosswalk CSV.
- **No client-side framework.** Server-rendered HTML, hand-written CSS under 15 KB, and the small
  amount of JavaScript needed for the EIN input and the copy button — progressively enhanced, so
  everything works with scripting off. A React bundle on a page whose entire purpose is being
  readable by crawlers is pure cost.

---

## 4. Why edge SSR and not a static site

Write this decision into `ADR-001` in the repository, because it is the one most likely to be
"optimized" later by someone who has not read the numbers.

Cloudflare Pages allows **20,000 files per deployment on the free plan and 100,000 on paid**. There
are roughly 1.4 million 501(c)(3) organizations. Pre-rendering one page per organization exceeds
the paid ceiling by more than an order of magnitude, and any meaningful fraction of it blows the
20-minute build timeout and destroys the deploy loop.

So: **render on demand at the edge from D1, and cache the result.** A cached edge render is served
from the same colo as a static asset. A cold render is one indexed D1 lookup. There is no
performance argument for static here, only a cost argument, and the cost argument is what the
20,000-file ceiling settles.

Pre-render at build time **only**: the landing page, `/methodology`, `/about`, `/data`,
`/llms.txt`, `/robots.txt`, the eleven `/checks/{check_id}` explainers, and the state and NTEE
browse indexes. Everything keyed on an EIN is edge-rendered.

---

## 5. Routes

Implement exactly the route table in `docs/hosted/architecture.md` section 2. The rules that are
easy to get wrong:

- **`/ein/{ein}` with the hyphen is canonical.** `/ein/270125367` and any slug variant 301 to it.
  Two URLs must never serve one organization.
- **`/check` never renders a result.** It resolves the input and 302s to the canonical entity URL,
  so every result lives at a shareable, cacheable, indexable address.
- **`/search` is `noindex`.** It exists to find an EIN, not to be a directory. See
  `docs/NON-GOALS.md`.
- **EIN validation happens before D1 is touched.** Nine digits after normalization or a 400 from
  the edge with no database round trip. This is the entire abuse surface of the site.
- **A well-formed EIN that is absent gets a real 404 page** explaining that churches, government
  instrumentalities, and newly recognized organizations are legitimately absent — plus `noindex`,
  so we do not create a billion crawlable not-found URLs.
- **`/api/check/{ein}`** returns the same JSON as `grantcheck --format json`, same
  `schema_version`, same keys. CORS open, no key. **Assert this equivalence in CI**, comparing
  against a fixture generated by the Python tool.

---

## 6. D1 schema and ingest

The schema is in `docs/hosted/architecture.md` section 3. Implement it as written. Notes on
building it:

- **Verify the current D1 database size limit on the account's plan before the first full ingest.**
  If ~2M lean rows do not fit, shard across databases by EIN prefix and route in the Function. That
  is the same partition key the CLI index uses, so the two designs stay aligned. Decide this before
  M2, not after.
- **Keep rows lean.** Store codes, not expanded labels. Expansion happens in the render layer from
  a table shipped in the Function bundle.
- **The ingest runs in GitHub Actions, not in a Worker.** It is a batch job over hundreds of
  megabytes. It imports the Python parsers from the `grantcheck` package rather than
  reimplementing them in TypeScript — two parsers for one badly documented format is two sets of
  bugs and a guarantee that the site and the CLI eventually disagree.
- **Load into new tables and swap by rename inside one transaction.** The site must never serve a
  half-loaded table.
- **`wrangler d1 import` in chunks of roughly 50,000 statements.** Two million rows in one file
  will time out.
- **`dataset_vintage` is updated last and is the commit point.** Until it changes, the edge is
  still serving the previous vintage consistently from cache.
- **Never overwrite a crosswalk row whose `method` is `confirmed`.** Human corrections outrank
  inference permanently.
- **Smoke-test against the live site after the load**, on a fixed EIN list, asserting on rendered
  facts. A failure rolls back by reverting `dataset_vintage`.

The same workflow publishes the CLI index shards to R2 and mirrors them to a GitHub release, from
the same build, so the two surfaces cannot drift.

---

## 7. Caching keyed on dataset vintage

This is the piece that keeps the request bill flat and makes invalidation exact.

Read `dataset_vintage` once per isolate, hold it in module scope, and build a version string from
the concatenated vintages. Every cache key carries it:

```
https://check.opengrants.io/ein/27-0125367?v=<bmf>.<pub78>.<rev>.<epostcard>.<sam>
```

The `v` parameter is constructed server-side and stripped before rendering. **It never appears in a
link, a canonical tag, or the sitemap.** A new ingest changes the string and the entire edge cache
invalidates in one step — no purge call, no TTL guessing, no partial-invalidation window where two
pages disagree.

Headers, by page class:

| Page class | Header |
|---|---|
| Pure IRS-derived entity page | `public, max-age=0, s-maxage=604800, stale-while-revalidate=86400` |
| Entity page with OpenGrants enrichment | `public, max-age=0, s-maxage=86400, stale-while-revalidate=3600` |
| Static explainer, methodology, landing | `public, s-maxage=86400`, long browser cache on hashed assets |
| `/search` | `public, s-maxage=300` plus `noindex` |
| `/api/check/{ein}` | Same as its page class, plus `Access-Control-Allow-Origin: *` |

**Always serve stale while revalidating.** A 990 figure four hours old beats a spinner, and the
page states its vintage regardless.

Live SAM.gov lookups and OpenGrants enrichment go behind `waitUntil` and never block the first
byte. **The core report must render correctly with every optional upstream unreachable**, falling
back to the snapshot with the snapshot's date visible. Build this failure path before you build the
happy path, and test it by pointing both upstreams at a black hole.

---

## 8. SEO and GEO requirements

All of these are from `docs/program/HOSTING.md` and all of them are required, not recommended.

**Server-rendered facts in the initial HTML.** No client-side fetching for any primary content —
not the check results, not the vintages, not the organization name. `curl` the page with no
JavaScript and the complete answer must be there. This is the reason the site is edge SSR and it
is the acceptance test that matters most.

**schema.org JSON-LD on every entity page.** `NGO` with:

- `name`, `alternateName` from the BMF sort name
- `taxID` — the EIN. This is the property that makes the page machine-joinable and it is the single
  most valuable line of markup on the site.
- `identifier` — the UEI, only where a confirmed crosswalk row exists
- `address` as `PostalAddress`, labelled in the visible text as the IRS mailing address, which is
  what it is and not a location
- `nonprofitStatus`: `NonprofitType501c3` where applicable
- `url` set to the canonical
- `sameAs` linking the IRS Tax Exempt Organization Search record and the sibling portfolio pages

Plus a `Dataset` block on `/data` and `FAQPage` markup on every `/checks/{check_id}` page, since
those pages exist to answer one question verbatim.

**One canonical URL per entity**, hyphenated EIN, `<link rel="canonical">` on every render
including those reached through a redirect.

**Sitemap index chunked at 50,000 URLs per file**, generated at ingest time, gzipped, served from
R2. Roughly 1.4M entity URLs, so about 28 chunks, plus the static and browse pages. `<lastmod>`
comes from the organization's own data vintage, not the build date, so recrawls are targeted rather
than uniform.

**`llms.txt` at the root.** What the dataset is, which federal sources it derives from, the vintage
policy, the disclosure, the citation format we want used, and pointers to the JSON API and the CC0
crosswalk. Cheap to write and increasingly how models decide what a site is for.

**Every page states its source and vintage inline, in visible body text.** "Exempt status from the
IRS Exempt Organizations Business Master File published 2026-08-11." Not a tooltip, not a meta tag.
Wrap dates in `<time datetime="...">`. Pages that show their work get cited; pages that assert bare
numbers do not.

**Answer-shaped structure for generative engines.** Each entity page opens with an H1 naming the
organization and its EIN, then **one self-contained paragraph** stating the readiness conclusion,
the reason, and the vintage — written so a model can lift it whole and still be correct and
attributable. Check explainer pages use the question as the H1 verbatim ("What does automatic
revocation of exemption mean?") and answer it inside the first forty words.

**Cross-link the portfolio.** Every entity page links to the same EIN on `funders.opengrants.io`,
`awards.opengrants.io`, and `desk.opengrants.io` where a record exists, and omits the link
otherwise. Never a dead cross-link. Five sites that reference each other read as one authoritative
body of work rather than five orphans.

**The disclosure on every page that reports on an organization**, verbatim, in the body:

> This is informational only, derived from public data on the dates shown. It is not an eligibility determination, and not legal, tax, or accounting advice. Verify against the official source before relying on it.

**Core Web Vitals.** No web fonts, or one subset and self-hosted. System font stack is fine and
loads instantly. Inline the critical CSS. No layout shift — the page is fully formed at first
paint because everything on it is server-rendered.

---

## 9. The UEI confirmation flow

The EIN-to-UEI join is inferred by name and state matching because the taxpayer identification
number is sensitive-tier on the SAM.gov side and cannot be searched. See
`docs/research/data-sources.md` section 3.

On each entity page, where a match was inferred, show the matched SAM.gov entity, the confidence,
and a control: "Is this the right SAM.gov registration?" with confirm and correct actions. A
correction takes a UEI, validates it against the SAM snapshot, and writes an
`ein_uei_crosswalk` row with `method = 'confirmed'`.

- Rate-limit it and require a lightweight bot check. Do not require an account — an account would
  destroy the flow, and the flow is the asset.
- Store the pair and a timestamp. **Do not store who submitted it.**
- Publish the confirmed crosswalk as a CC0 CSV at `/api/crosswalk.csv`, refreshed monthly.

This is the most valuable thing the site produces. A public EIN-to-UEI crosswalk does not exist,
its absence is a small ongoing tax on the entire sector, and every confirmation makes both the site
and the command-line tool permanently better.

---

## 10. Milestones

**H0 — Project skeleton.** Pages project, TypeScript strict, Hono in the Functions catch-all,
biome, vitest, local development against a seeded D1. `ADR-001` recording the edge-SSR decision.
*Demo: a hello route renders at the edge locally.*

**H1 — D1 schema and a seeded subset.** Schema applied, 10,000 organizations loaded from a local
index build, `dataset_vintage` populated.
*Demo: query an EIN in D1 and get a complete row set.*

**H2 — The entity page.** `/ein/{ein}` edge-rendered from D1 with all checks, all sources, all
vintages, and the disclosure. Canonical, redirects, 400 on malformed input, real 404 on absent.
*Demo: `curl https://…/ein/27-0125367 | grep -c "2026-08-11"` finds the vintages in raw HTML.*

**H3 — Caching.** Vintage-keyed cache keys, the header matrix, stale-while-revalidate.
*Demo: bump `dataset_vintage` and observe the whole cache invalidate; confirm the second request
to an unchanged page is a cache hit.*

**H4 — SAM and enrichment, with their failure paths built first.** Live SAM behind `waitUntil`,
OpenGrants matching on a clean report, snapshot fallback.
*Demo: with both upstreams black-holed, the page renders complete and correct from the snapshot,
with the snapshot dates visible.*

**H5 — Static pages.** Landing, `/methodology`, `/about`, `/data`, the eleven `/checks/{id}`
explainers with `FAQPage` markup, `robots.txt`, `llms.txt`.
*Demo: every explainer answers its question in the first forty words.*

**H6 — SEO surface.** JSON-LD, canonical tags, sitemap index and chunks generated at ingest and
served from R2, browse pages for state and NTEE, portfolio cross-links.
*Demo: JSON-LD validates and contains `taxID`; the sitemap index resolves and every chunk is under
50,000 URLs.*

**H7 — Full ingest.** The complete monthly GitHub Actions pipeline: fetch, parse, match, build,
chunked D1 import, table swap, vintage commit, sitemap regeneration, CLI shard publication,
crosswalk publication, smoke test with rollback.
*Demo: a full ingest runs end to end and the site serves the new vintage with no downtime.*

**H8 — UEI confirmation and the crosswalk.** The confirmation flow, rate limiting, the CC0 CSV.
*Demo: a confirmation is recorded, survives the next ingest, and appears in the published CSV.*

**H9 — API parity.** `/api/check/{ein}` byte-equivalent to the Python tool's JSON at the same
vintage, asserted in CI.
*Demo: the CI job diffs the two and passes.*

**H10 — DNS and launch.** Section 11, then the launch checklist in
`docs/hosted/architecture.md` section 9.

---

## 11. DNS

`check.opengrants.io` is a subdomain of `opengrants.io`, whose DNS is managed externally rather
than at the registrar's default.

1. **Confirm who holds the `opengrants.io` zone before you start building.** This is the step most
   likely to sit blocked for a day and the only one in the whole launch that cannot be unblocked by
   working harder. Ask on day one, not at H10.
2. Create the Pages project; note its `*.pages.dev` hostname.
3. Add the custom domain `check.opengrants.io` in the Pages project. Cloudflare issues a validation
   record.
4. In the zone, add a `CNAME` for `check` pointing at the `pages.dev` hostname, plus the validation
   record.
5. Wait for certificate issuance. Verify HTTPS resolves and `http://` 301s to `https://`.
6. Verify the apex and `www` records are untouched.

---

## 12. Launch checklist

The authoritative list is `docs/hosted/architecture.md` section 9. Work it item by item. Nothing
ships until every box is ticked. The five that will actually bite:

- [ ] `curl` an entity page with JavaScript never executed and confirm **every** fact is in the
      HTML.
- [ ] A revoked-then-reinstated organization renders as in good standing with its full history.
      Verify by hand against the IRS Tax Exempt Organization Search.
- [ ] A group exemption subordinate does not render a Publication 78 problem.
- [ ] A vintage bump demonstrably invalidates the whole edge cache, and someone has done the
      `dataset_vintage` rollback once in staging.
- [ ] The disclosure is on every entity page, verbatim, in the body.

---

## 13. Stop and ask the human

1. **The `opengrants.io` zone.** Who holds it, and who can add the CNAME. Ask on day one.
2. **Cloudflare account, plan, D1 database name, R2 bucket names, and who holds the API token.**
   Blocking for H0.
3. **The D1 size limit versus the dataset.** If ~2M lean rows do not fit on the current plan, the
   choice between upgrading and sharding across databases is a cost decision, not yours.
4. ~~**SAM.gov redistribution.**~~ **Answered 2026-08-31: bundle the snapshot**, same as the core
   build. See `docs/program/DECISIONS.md`, D-001. The site reads the same snapshot the CLI does, from the
   same ingest, so H4's snapshot fallback path is now fully specified rather than provisional.
5. **The rate limit and abuse posture on the UEI confirmation flow**, since it writes to a
   published public dataset.
6. **Anything that would add a client-side data fetch for primary content.** That would silently
   void the entire SEO and GEO rationale for the site, and it is the kind of change that looks like
   a performance improvement.
7. **Any page that would present a conclusion rather than a fact.** The pull toward a headline
   "ELIGIBLE / NOT ELIGIBLE" badge will be strong because it converts better. It is on the
   non-goals list for good reasons and overriding it is a product decision.
8. **Analytics beyond Cloudflare Web Analytics**, or anything that would let the site join a
   visitor to the EINs they looked up. See the privacy section of the architecture document.
