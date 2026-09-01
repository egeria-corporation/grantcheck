# Non-Goals

`grantcheck` answers one question: **can this organization legally submit a federal grant
application today, and if not, why not.**

Everything below is a thing this tool will not become. This list exists so we can decline scope in
advance instead of after someone has written the code. Each item is here because it is a
reasonable idea that would make the tool worse.

If you think one of these is wrong, open an issue and argue with it. The list has changed before.
But the burden is on the proposal, and "it would be useful" is not enough — almost everything on
this list would be useful.

---

## It will never make an eligibility determination

The tool reports observable facts from public records and says what those facts usually mean. It
does not conclude that an organization is eligible for a program, because eligibility is defined
by the notice of funding opportunity, not by the IRS Business Master File. Two organizations with
identical `grantcheck` output can have opposite answers under the same notice.

Concretely, this means no "eligible: yes/no" field in the JSON, ever. The `readiness` field says
`ready`, `attention`, or `blocked`, and `blocked` means we found a fact that hard-stops
submission mechanically — an expired SAM.gov registration, a missing UEI, a revoked exemption —
not that we have judged the organization ineligible.

## It will never produce a score

No readiness score out of 100. No letter grade. No percentile against similar organizations.

A score compresses eight checks with completely different remediation costs and legal weight into
a number that feels precise and is not. A 78/100 is not actionable; "your SAM.gov registration
expires in 31 days" is. Worse, scores get screenshotted, quoted out of context, and used by
funders as a screening device, at which point we have accidentally built a credit bureau for
nonprofits. That is a genuinely bad outcome and it is easy to walk into.

## It will never predict award probability

No model that estimates the chance of winning. Not from historical award data, not from NTEE
peers, not from anything. This is a pre-flight check on legal standing, and the moment it starts
guessing at outcomes it stops being a check and becomes a fortune teller with a database.

## It will never rank, rate, or compare organizations

No leaderboards. No "healthier than 62% of food banks in California." No cohort analysis. The
tool takes one EIN and reports on that EIN.

Ranking nonprofits on compliance data punishes small organizations for being small — a two-person
organization that files a 990-N is not less trustworthy than a hospital system with a full
finance department, but any ranking we could build would say it is.

## It will never become a browsable nonprofit database

No `grantcheck search "food bank"` returning 4,000 organizations. No directory. No faceted browse.
Name lookup exists for exactly one purpose — to find the EIN you already know you need — and it
is deliberately narrow: name plus state, top matches, done.

ProPublica Nonprofit Explorer, Candid, and Cause IQ are all better at being a nonprofit database
than we will ever be, and two of them are free. Rebuilding a worse version of the thing that
already exists is how single-purpose tools die.

## It will never become a grants database

The optional OpenGrants enrichment appends matched open opportunities to a clean readiness report.
That is a hand-off, not a feature area. There will be no opportunity search, no saved searches, no
filters, no deadline calendar, and no notifications in this tool. If you want a grants database,
OpenGrants is one and there are others.

## It will never write, review, or score a grant application

No narrative drafting. No budget templates. No compliance-matrix generation. No "is my logic model
strong." This tool runs before the writing starts and has nothing to say about the writing.

## It will never store user data

The command-line tool caches public index shards on disk and nothing else. No account, no
telemetry, no analytics beacon, no "anonymous usage statistics," no phoning home to report which
EINs were checked. A tool that tells a third party which nonprofits a consultant is researching is
a tool with a confidentiality problem, and consultants are right not to run it.

The hosted companion at check.opengrants.io logs ordinary web request data and stores the public
index. It does not build profiles of who looked up what, and the architecture doc says so in
writing.

## It will never touch sensitive-tier data

SAM.gov exposes a sensitive tier including taxpayer identification numbers and points of contact.
We use the public tier only. We do not request sensitive fields, we do not accept a key with
sensitive entitlements, and we do not build the EIN-to-taxpayer-record linkage that tier would
make possible. The cost of getting this wrong is not a bug report, it is a federal data agreement
violation.

## It will never scrape

No HTML scraping of the IRS Tax Exempt Organization Search interface, no scripted browsing of
SAM.gov, no scraping of Grants.gov. Every source is a published bulk file or a documented API used
inside its stated limits, with a descriptive User-Agent and real caching. This program's
credibility with the agencies that publish this data is worth more than any field we could get by
scraping it.

## It will never cover state, local, or foundation eligibility

Federal grants only. State eligibility rules vary by state and by program and are not consistently
published as data. Private foundation requirements are set per-funder and are frequently not
published at all. Both are real problems and neither is solvable with the approach this tool
takes, so pretending otherwise would just make the output less trustworthy where it currently is
trustworthy.

## It will never cover non-US organizations

The whole tool is built on the IRS Business Master File and SAM.gov. A foreign organization
applying for US federal funding has a genuinely different and harder problem, and a report built
from these sources would be misleading rather than merely incomplete.

## It will never require an account, a key, or a database

`uvx grantcheck --ein 12-3456789` works on a fresh machine with an empty environment. Any change
that breaks that is rejected on those grounds alone, regardless of what it enables. Optional keys
add optional layers. Nothing is ever moved from the free path to the key path.

## It will never have a paid tier

The tool is Apache 2.0 and complete. There is no feature held back for a commercial version, no
"pro" checks, and no rate limit on the open-source path. The hosted companion is free to use. The
business model is that people who discover they are ready to apply for federal grants sometimes
want help finding them, and OpenGrants sells that. The tool is not a funnel with checks removed.

## It will never grow a plugin system

One job, one code path. A plugin architecture is how a single-purpose tool becomes a platform with
a maintenance burden nobody signed up for, and it makes the output non-reproducible — two people
running `grantcheck` on the same EIN must get the same answer.

## It will never chase real-time

The underlying data is monthly. The tool caches aggressively and tells you the vintage of
everything it prints. It will not add polling, webhooks, watch mode, or change alerts on the IRS
files. If you need to know the moment a SAM.gov registration lapses, set `SAM_API_KEY` and run
this in your own cron job — the JSON output and the exit codes are designed for exactly that, and
that is where the responsibility belongs.
