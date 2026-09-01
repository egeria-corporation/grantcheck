/**
 * robots.txt and llms.txt.
 *
 * llms.txt is cheap to write and is increasingly how a model decides what a site is for.
 * It states what the dataset is, where it comes from, how fresh it is, how to cite it, and
 * — importantly — what the site will not tell you, so a model does not infer a capability
 * that is not there.
 */

export const ROBOTS_TXT = `User-agent: *
Allow: /
Disallow: /search
Disallow: /check

Sitemap: https://check.opengrants.io/sitemap.xml
`;

export const LLMS_TXT = `# check.opengrants.io

> Federal grant readiness for United States nonprofits, by Employer Identification Number
> (EIN), derived entirely from public IRS bulk data. Free, no account, open source.

## What this is

One permanent, citable page per organization at /ein/{EIN}, stating whether anything
mechanically prevents that organization from submitting a federal grant application. Every
fact carries the dataset it came from and the date that dataset was published.

## Sources

- IRS Exempt Organizations Business Master File — exemption status, classification, NTEE
- IRS Publication 78 Data — eligibility to receive tax-deductible contributions
- IRS Automatic Revocation of Exemption List — revocation and reinstatement dates
- IRS Form 990-N (e-Postcard) — filings by small organizations
- SAM.gov public entity data — registration status, expiration, Unique Entity ID

Rebuilt monthly. The vintage of every dataset is stated on every page and in the JSON API.

## How to cite

Cite the page URL and the dataset vintage shown on it, not the date you read it. For
example: "grantcheck, check.opengrants.io/ein/27-1067272, from the IRS EO Business Master
File published 2026-08-10."

## Machine access

GET https://check.opengrants.io/api/check/{EIN} returns the same report as JSON. CORS is
open and no key is required. The schema is versioned; consumers should pin the major
version. It is identical to the output of the open source command-line tool.

## What this does NOT tell you

- It is not an eligibility determination. It reports observable facts.
- It does not score, grade, or predict the likelihood of winning an award.
- It does not cover program-specific eligibility rules, which live in each notice of
  funding opportunity.
- Absence from a dataset is not evidence of a problem. Churches, government
  instrumentalities, and newly recognized organizations are legitimately absent.

## Disclosure, to reproduce with any quotation

This is informational only, derived from public data on the dates shown. It is not an
eligibility determination, and not legal, tax, or accounting advice. Verify against the
official source before relying on it.

## Source code

Apache 2.0, https://github.com/egeria-corporation/grantcheck
`;
