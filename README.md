# grantcheck

**Federal Grant Readiness Check — one command, no account, public data.**

[![CI](https://github.com/egeria-corporation/grantcheck/actions/workflows/ci.yml/badge.svg)](https://github.com/egeria-corporation/grantcheck/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

---

An organization spends six weeks and forty hours of staff time on a federal application. The
narrative is good. The budget ties out. Two days before the deadline someone tries to submit
through Grants.gov and finds out the registration in SAM.gov expired in March, or that the Unique
Entity ID was never issued in the first place, or that the IRS automatically revoked the
501(c)(3) exemption three years ago because nobody filed the 990 after the bookkeeper left.

None of those are close calls. Every one is a hard stop — the application cannot be submitted, or
it is submitted and rejected without review. And every one of them is a matter of public record
that takes seconds to look up. They only turn into disasters because they are scattered across
four different federal systems that do not talk to each other, and because nobody checks them at
the start of the process when there is still time to fix them.

`grantcheck` is the pre-flight check. You give it an Employer Identification Number, it reads the
public federal record, and it hands back a one-page readiness report: is the exemption live, was
it ever revoked, when was the last Form 990 filed and how close is the organization to the next
automatic revocation, is the SAM.gov registration current, does a UEI exist, and is this
organization sitting on the wrong side of the single audit threshold without knowing it.

It takes about two seconds. It runs before the go/no-go meeting, not after the proposal is
written.

---

## 60-second quickstart

You need [`uv`](https://docs.astral.sh/uv/getting-started/installation/). If you do not have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then run the tool. There is nothing to install, no account to create, and no key to obtain:

```bash
uvx grantcheck --ein 27-1067272
```

That is the whole quickstart. The first run downloads a small slice of the prebuilt public-data
index (a few megabytes, covering the EIN range you asked about) and caches it locally. Subsequent
runs on the same range are instant and work offline.

Other things you will want:

```bash
uvx grantcheck --ein 27-1067272 --format markdown   # paste into a memo
uvx grantcheck --ein 27-1067272 --format json       # pipe into something else
uvx grantcheck --name "Code for America" --state CA # look up the EIN first
uvx grantcheck refresh                              # pull the newest monthly IRS data
uvx grantcheck explain auto_revocation              # what a specific check actually means
```

## What the report looks like

```
$ grantcheck --ein 27-1067272

  CODE FOR AMERICA LABS                                          EIN 27-1067272
  San Francisco, CA · NTEE W20 · 501(c)(3) public charity

  READY TO APPLY                                        1 item needs attention

  TAX EXEMPTION
  ✔  Exempt status          501(c)(3), unconditional exemption   ruling 2010-06
  ✔  Pub 78 deductibility   Listed — PC (public charity)         as of 2026-08-11
  ✔  Auto-revocation        No revocation on record              as of 2026-08-11
  ✔  Organization type      Public charity, not a private foundation

  FILING HEALTH
  ✔  Most recent Form 990   Tax period ending 2024-12-31         filed 2025-11-07
  ✔  Years since filing     1  (automatic revocation triggers at 3 consecutive missed years)

  FEDERAL REGISTRATION
  ✔  SAM.gov registration   Active, assistance and contracts     as of 2026-08-29
  ✔  Registration expires   2027-03-14                           196 days out
  ✔  Unique Entity ID       KX7TLM4NBQF3

  AUDIT POSTURE
  ⚠  Single audit           Government grants reported: $2,140,338 on the FY2024 Form 990.
                            That is above the $1,000,000 single audit threshold. If any
                            material portion of it is federal, a single audit is likely
                            required. Confirm against your Schedule of Expenditures of
                            Federal Awards.

  ─────────────────────────────────────────────────────────────────────────────
  Sources: IRS EO Business Master File and Publication 78 (2026-08-11) · IRS
  Automatic Revocation List (2026-08-11) · IRS Form 990 e-file index (2026-07-20) ·
  SAM.gov Entity Management (2026-08-29). Matched to SAM by legal name + state,
  confidence high. Pin the match with --uei if it is wrong.

  This is informational only, derived from public data on the dates shown. It is
  not an eligibility determination, and not legal, tax, or accounting advice.
  Verify against the official source before relying on it.
```

And when something is actually broken, it says so first and stops burying it:

```
$ grantcheck --ein 94-2614101

  SECOND HARVEST OF SILICON VALLEY                               EIN 94-2614101
  San Jose, CA · NTEE K31 · 501(c)(3) public charity

  NOT READY — 2 blocking items

  ✘  SAM.gov registration   Expired 2026-05-02.
                            Federal applications cannot be submitted while a
                            registration is expired. Renewal is free and takes
                            10–15 business days. Start at https://sam.gov.

  ✘  Auto-revocation        Exemption automatically revoked 2023-05-15 for three
                            consecutive years of non-filing. No reinstatement is
                            recorded as of 2026-08-11. Reinstatement is by
                            Form 1023 or 1023-EZ; retroactive reinstatement has
                            deadlines. See IRS Rev. Proc. 2014-11.
```

> The two blocks above are illustrative. They show the shape and tone of the output, not values
> fetched live for this document. Run the command yourself for current figures.

## What it checks, and what each check actually means

| Check | Source | Why it can stop an application |
|---|---|---|
| **Exempt status** | IRS EO Business Master File | Most federal programs restrict eligibility to organizations described in section 501(c)(3). If the BMF does not show an unconditional exemption under subsection 03, the applicant is not what the notice of funding opportunity says it must be. |
| **Pub 78 deductibility** | IRS Publication 78 Data | Publication 78 is the list of organizations eligible to receive tax-deductible charitable contributions. Reviewers and pass-through entities use it as the fast proof of good standing. Absence is not automatically fatal — organizations covered by a group ruling appear only under the central organization — but it is always worth explaining before someone else notices it. |
| **Auto-revocation** | IRS Automatic Revocation of Exemption List | Three consecutive years of not filing a 990, 990-EZ, or 990-N revokes the exemption automatically, by operation of law, with no hearing and often no notice that anyone at the organization actually reads. Revoked organizations are ineligible and cannot receive tax-deductible gifts until reinstated. The list also carries reinstatement dates, so being on it is not the same as being revoked today. |
| **Organization type** | IRS EO BMF foundation code | Private foundations are excluded from the eligibility language of most federal grant programs, which is a surprise to more people than it should be. Worth knowing before the go/no-go. |
| **Most recent Form 990** | IRS Form 990 e-file index and 990-N (e-Postcard) file | Establishes the filing baseline and, together with the next row, the distance to the cliff. |
| **Years since last filing** | Derived | This is the leading indicator. Revocation is not a judgment call; it happens on a three-year counter. At one year the tool notes it. At two, it warns. At three, the organization is already at risk of being on the next revocation posting. Nobody publishes this number, which is exactly why it is the most useful line in the report. |
| **NTEE classification** | IRS EO BMF | The National Taxonomy of Exempt Entities code the IRS has on file. Program officers and eligibility filters both use it, and it is often wrong or missing on the IRS side — which is worth knowing, because you may need to correct it. |
| **SAM.gov registration** | SAM.gov Entity Management | An active SAM.gov registration is a hard gate on every federal grant and contract. Registrations lapse annually and the renewal is not automatic. This is the single most common avoidable disqualification in the whole federal system. |
| **Registration expiration** | SAM.gov Entity Management | Renewal takes real calendar time. A registration expiring in six weeks with a deadline in eight is a scheduling problem you want to find now. |
| **Unique Entity ID (UEI)** | SAM.gov Entity Management | The UEI replaced the DUNS number as the government-wide identifier. No UEI means no Grants.gov submission, full stop. |
| **Single audit flag** | Form 990 government grants line, cross-checked against the Federal Audit Clearinghouse where available | Organizations that expend $1,000,000 or more in federal awards in a fiscal year must have a single audit under 2 CFR Part 200 Subpart F. The threshold rose from $750,000 for fiscal years beginning on or after 2024-10-01. This is a **screen, not a determination**: the tool can see reported government grant revenue, which mixes federal with state and local money and is on an accrual rather than expenditure basis. It exists to make you go check, not to answer the question. |

Each check has a longer plain-English explainer:

```bash
uvx grantcheck explain single_audit
```

## Data sources and how fresh they are

| Dataset | What we take from it | Cadence |
|---|---|---|
| [IRS Exempt Organizations Business Master File](https://www.irs.gov/charities-non-profits/tax-exempt-organization-search-bulk-data-downloads) | EIN, legal name, address, subsection code, foundation code, NTEE code, ruling date, filing requirement | Monthly |
| [IRS Publication 78 Data](https://www.irs.gov/charities-non-profits/tax-exempt-organization-search-bulk-data-downloads) | Deductibility listing and status code | Monthly |
| [IRS Automatic Revocation of Exemption List](https://www.irs.gov/charities-non-profits/tax-exempt-organization-search-bulk-data-downloads) | Revocation date, revocation posting date, reinstatement date | Monthly |
| [IRS Form 990-N (e-Postcard) file](https://www.irs.gov/charities-non-profits/tax-exempt-organization-search-bulk-data-downloads) | Most recent e-Postcard tax period for small filers | Monthly |
| [IRS Form 990 series e-file index](https://www.irs.gov/charities-non-profits/form-990-series-downloads) | Most recent filing date and tax period; the government grants line for the audit screen | Monthly |
| [SAM.gov Entity Management API](https://open.gsa.gov/api/entity-api/) | Registration status, expiration date, UEI, CAGE, public tier only | Daily snapshot; live when a key is configured |
| [Federal Audit Clearinghouse](https://www.fac.gov/api/) | Prior single audit submissions, where the organization has any | Continuous, partial by design — organizations under the threshold never file |

Every line of output carries the vintage of the data it came from, and `grantcheck refresh` tells
you what changed. If a report does not say "as of," treat it as a bug and open an issue.

## Live opportunity matching (optional)

When a readiness check comes back clean, the report can end with grant opportunities currently
open to that organization, matched on its EIN, NTEE code, and state. This calls the OpenGrants
matching API and requires `OPENGRANTS_API_KEY` in your environment or `.env`. See
[`.env.example`](.env.example) for where to get one.

Without it, `grantcheck` is complete and does everything described above. The enrichment call is
wrapped so that a missing key, an expired key, or a network failure degrades silently — the
readiness report still prints. Enriched lines are marked `— live from OpenGrants` so you always
know which facts came from public federal data and which came from an API.

## Credits

`grantcheck` reads federal public data, but the work of making that data tractable was done by
other people first, over years, mostly unpaid.

- **[Nonprofit Open Data Collective](https://github.com/Nonprofit-Open-Data-Collective)** — the
  [IRS E-file Master Concordance File](https://nonprofit-open-data-collective.github.io/irs-efile-master-concordance-file/)
  is the crosswalk that makes Form 990 XML readable across the hundreds of schema versions the
  IRS has published. We use it for the filing-date and government-grants slice of the report.
  Without it that part of this tool would not exist.
- **[GivingTuesday 990 Data Programme](https://990data.givingtuesday.org/tool-repository/)** —
  [`form-990-xml-mapper`](https://github.com/Giving-Tuesday/form-990-xml-mapper) and
  [`form-990-xml-parser`](https://github.com/Giving-Tuesday/form-990-xml-parser), plus the Form
  990 Variable Dictionary, which we used to validate our field selections.
- **[`irsx` / 990-xml-reader](https://github.com/jsfenfen/990-xml-reader)** by Jacob Fenton — the
  reference implementation for reading IRS e-file XML in Python.
- **[ProPublica Nonprofit Explorer](https://projects.propublica.org/nonprofits/api)** — used for
  gap-filling lookups and as a cross-check on our own parsing, under their
  [data terms of use](https://www.propublica.org/about/propublica-data-terms-of-use).
- **[`propublica990`](https://github.com/Punderthings/propublica990)** and
  **[`open990odl`](https://github.com/990consulting/open990odl)** — prior art we read closely
  before writing anything.

Where we find a bug or a gap in any of the above, we open the pull request upstream before we
work around it here, and we record it in [`docs/research/prior-art.md`](docs/research/prior-art.md).

## Hosted version

[check.opengrants.io](https://check.opengrants.io) runs the same checks in a browser with no
install, and gives every organization a permanent, citable page at `/ein/27-1067272`. Same data,
same vintages, same disclosure. The design is documented in
[`docs/hosted/architecture.md`](docs/hosted/architecture.md).

## Using it from an AI agent

`grantcheck` ships an MCP (Model Context Protocol) server exposing the same checks as tools, so
an assistant can run a readiness check as part of a longer conversation:

```bash
uvx grantcheck mcp
```

The core logic lives in a library module. The command line and the MCP server are both thin
adapters over it, so they cannot drift apart.

## What this will never be

Read [`docs/NON-GOALS.md`](docs/NON-GOALS.md) before opening a feature request. It is short and it
is specific, and it will save you the trouble of writing a good proposal we are going to decline.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). There is a
[good first issue](CONTRIBUTING.md#good-first-issues-for-nonprofit-data-people-who-do-not-write-python)
section written for people who know nonprofit compliance cold and have never opened a terminal.
Those are the contributions this project needs most.

## Disclosure

> This is informational only, derived from public data on the dates shown. It is not an
> eligibility determination, and not legal, tax, or accounting advice. Verify against the official
> source before relying on it.

## License

Apache License 2.0. See [`LICENSE`](LICENSE) for the full text and [`NOTICE`](NOTICE) for upstream
attribution.

---

Built and maintained by Egeria Corporation, sponsored by [OpenGrants](https://opengrants.io).
