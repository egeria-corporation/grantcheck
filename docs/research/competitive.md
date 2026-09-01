# Competitive Position

## What this replaces

`grantcheck` does not replace a product. It replaces a **feature bundled inside four different
products**, none of which sells it separately, and which together cost between $1,600 and $10,800
a year depending on which combination an organization is carrying.

The feature has a name in the sector — "grant readiness" or "pre-award compliance check" — and it
is one of the standard first-engagement deliverables a grant consultant produces. Done by hand it
is about ninety minutes: pull the IRS Tax Exempt Organization Search record, check Publication 78,
search the Automatic Revocation List, find the most recent 990 on ProPublica or Candid, log into
SAM.gov and read the registration status and expiration, confirm the UEI exists, and ask the
finance director what the government grants line looked like last year. Nothing in that list is
hard. It is tedious, it is four browser tabs, and it is skipped often enough that the failure mode
in the README is a cliché rather than a hypothetical.

---

## The verification rule

**Before any competitor price appears in public-facing copy — the README, the website, a blog
post, a conference slide — re-verify it on that vendor's own pricing page and date-stamp it in the
text.**

Stale competitor pricing is both an accuracy problem and the easiest possible thing for a
competitor to make us look bad over. A vendor whose price we quoted wrong is entitled to be
annoyed, and a screenshot of us being wrong about a rival's price does more damage than the
comparison ever earned.

Figures below carry the source and the verification date. Anything marked **VERIFY** has not been
confirmed on the vendor's own page and **must not be published anywhere outside this file** until
it has been.

---

## The parity targets

Prices as recorded in the program research dossier, verified 2026-08-30 unless noted.

| Product | Price | Source of figure | Status |
|---|---|---|---|
| **Instrumentl** | $179 / $299 / $499 / $899 per month across four tiers | Capterra listing, current at dossier verification 2026-08-30 | Re-verify on instrumentl.com pricing before publishing |
| **Candid Foundation Directory** | $1,599/year, or $219.99/month, for the full/professional level | May 2024 comparison at fundingforgood.org | **VERIFY** — a lower "essential" tier exists and the figure is over two years old |
| **Cause IQ** | $199/month or $999/year, limited free tier | Same May 2024 source | **VERIFY** |
| **Grant Gopher** | $9/month with a limited free option | Same May 2024 source | **VERIFY** |
| **Plinth** | Not public at verification | https://www.useplinth.com/ | Newest entrant; positions a 990-derived "funding graph" |

Comparison source: https://fundingforgood.org/comparing-grant-research-databases/

---

## Which specific paid feature each one bundles

### Candid — GuideStar Pro / Foundation Directory

Candid holds the nonprofit-profile franchise. A Pro subscription surfaces exempt status, Pub 78
deductibility, revocation history, and 990 financials on an organization profile, and the free
GuideStar tier shows a subset.

**What it does not do:** SAM.gov. Candid is an IRS-data company; federal registration state is
outside its model entirely. So a Candid subscriber gets three of our checks and is still exposed to
the most common disqualification of the four.

**What it does better:** everything downstream of readiness — narrative profile data, program
descriptions, demographic data, the funder side. Not a competition we are in.

### Instrumentl

Opportunity discovery and matching, priced per month per organization. Eligibility filtering is
built into matching: the platform screens opportunities against your organization's attributes.

**What it does not do:** tell you that *your organization* is not currently in a position to submit
anything. Instrumentl's eligibility logic runs on the opportunity side. It will happily surface a
perfect match for an organization whose SAM.gov registration expired last quarter.

**Overlap with us:** the optional OpenGrants enrichment at the end of a clean report is the same
category of output. That is deliberate and it is one line of the tool, not the tool.

### Cause IQ

Nonprofit market intelligence, sold mainly to vendors and consultants selling *to* nonprofits.
Rich firmographics and 990 financials with a limited free tier.

**What it does not do:** federal registration, or anything framed as pre-award readiness. Its
model is prospect research on nonprofits, not compliance posture of one nonprofit.

### The federal systems themselves

SAM.gov, IRS Tax Exempt Organization Search, and the Federal Audit Clearinghouse are all free and
all authoritative. They are also four separate logins across three agencies, and none of them will
tell you about the other two. The product here is composition, not access.

---

## Why free, and why open source

The obvious question is why give away a feature people pay for inside $2,000-a-year products.

**Because it is not the feature they are paying for.** Nobody buys Candid for revocation status or
Instrumentl for eligibility screening. They buy the database. Readiness checking is table stakes
bundled in, which means it is defensible for us to give away and expensive for them to match — a
free, better, open-source version of a feature that generates none of their revenue is not worth a
response, and building one would cannibalize the bundle logic that justifies their price.

**Because the cost of the gap is asymmetric.** A consultant paying $179/month gets these checks. A
two-person organization in a rural county does not, and it is the one that loses forty hours to an
expired registration. The population that needs this most is definitionally the population that
cannot buy it.

**Because it is a category-ownership play, not a revenue play.** "Is my nonprofit eligible for
federal grants," "check if 501c3 status was revoked," "do I need a single audit," "how do I know if
my SAM registration is active" are high-intent queries with no good free answer today. The answers
are short, factual, stable, and exactly the shape that both search engines and language models
want to cite. A tool that answers them, plus a hosted page per EIN that shows its sources and
vintages, is how OpenGrants becomes the thing that gets cited when somebody asks an assistant
whether their nonprofit can apply for federal money.

**Because the moment of maximum intent is the moment the check passes.** An organization that has
just confirmed it is clear to apply is, right then, more interested in open opportunities than at
any other point in its year. That hand-off is worth more than a subscription for a compliance
check nobody wants to buy on its own.

---

## What would actually threaten this

Worth writing down, because a competitive doc that only lists advantages is marketing.

1. **Candid or Instrumentl adds a SAM.gov panel.** Cheap for either of them and it closes the
   composition gap for their paying users. It does not close it for the unpaid majority, and it
   does not give them the per-EIN citable page, but it removes the sharpest line in our pitch.
2. **SAM.gov or the IRS ships a combined status endpoint.** Unlikely on any near horizon —
   the agencies do not share a join key, which is the whole problem — but it would end the
   category, correctly, and we should say so out loud if it happens.
3. **The public-tier SAM.gov constraint tightens.** If name-based entity search is restricted, or
   if GSA answers the clarification request in `docs/program/DECISIONS.md` D-001 by disallowing
   republication of the derived extract subset, the keyless path degrades and the tool needs a key
   to be complete. The planned fallback is that the three SAM checks report `unknown` without a
   user-supplied key — never a proxy endpoint we operate. See
   `docs/research/data-sources.md` section 3.
4. **We are wrong in public.** One confidently incorrect "your exemption was revoked" against a
   compliant organization does more reputational damage than a year of correct answers earns. This
   is a larger risk than any competitor, and it is why the reinstatement and group-exemption
   handling in `docs/research/data-sources.md` is treated as a correctness requirement rather than
   an edge case.

---

## Positioning, in one sentence

> The four federal checks that disqualify a grant application before anyone reads it, composed into
> one answer, free, in two seconds, with the source and the date on every line.

Not "a free alternative to Candid." We are not an alternative to Candid. We are the ninety minutes
of tab-switching that precedes deciding whether to subscribe to anything at all.
