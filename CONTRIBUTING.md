# Contributing to grantcheck

This project has two kinds of contributors and needs both.

The first kind writes Python. The second kind knows what a group exemption ruling is, has
personally reinstated a revoked 501(c)(3), or can tell you why the government-grants line on a
Form 990 is not the same thing as federal expenditures. If you are the second kind, skip to
[good first issues](#good-first-issues-for-nonprofit-data-people-who-do-not-write-python). You do
not need to install anything to make this tool substantially better, and the changes only you can
catch are the ones that matter most.

## Getting set up

You need Python 3.11 or newer and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/egeria-corporation/grantcheck
cd grantcheck
uv sync --all-extras
```

Run the test suite:

```bash
uv run pytest
```

Run it with coverage, which is what CI does:

```bash
uv run pytest --cov=grantcheck --cov-report=term-missing
```

Lint and format. Both must be clean before a pull request will pass CI:

```bash
uv run ruff check .
uv run ruff format .
```

Run the tool from your working copy without installing it:

```bash
uv run grantcheck --ein 27-1067272
```

## The testing rule: fixtures come from real data

**Every test that touches a data format must run against a real, committed sample of that format.**
No hand-written dictionaries that describe what we think a row looks like. No mocks of the shape
of an API response. If a test would still pass after the IRS renamed a column, it is not testing
anything we care about.

The failure mode this project actually has is schema drift. The IRS reposts these files monthly
and occasionally changes a column, a code value, or a delimiter convention without announcement.
Mock-shaped tests are blind to exactly that, which makes them worse than no tests, because they
produce a green check mark while the tool silently returns wrong answers about whether a
nonprofit can legally apply for money.

How it works in practice:

- Fixtures live in `tests/fixtures/` and are small verbatim slices of the real upstream files —
  the header line plus a hand-picked set of rows, taken with `head` and `grep`, never edited by
  hand except to delete rows.
- Every fixture file has a sibling `.source.json` recording the exact URL it came from, the date
  it was downloaded, and a one-line note on why those particular rows are in it ("group exemption
  subordinate", "revoked then reinstated", "NTEE code missing", "name contains an embedded pipe").
- All of this data is public. There is nothing to redact. Do not anonymize EINs in fixtures — the
  real ones are the point, and a fake EIN cannot catch a real parsing bug.
- Keep fixtures small. If a fixture is over about 200 KB, you are testing throughput, not
  correctness, and it belongs in a separate benchmark that CI skips.
- Network calls in tests are recorded and replayed, never live. Tests must pass with the network
  unplugged.

When you add a check or fix a parser, add the row that broke it to the fixture and reference the
issue number in the `.source.json` note. That is how the suite gets better instead of just bigger.

## Pull request expectations

- **One thing per pull request.** A parser fix and a new output format are two pull requests.
- **Open an issue first** for anything that adds a check, changes the output schema, or adds a
  dependency. For a bug fix or a docs improvement, just send the pull request.
- **Read [`docs/NON-GOALS.md`](docs/NON-GOALS.md) first.** It exists so that we decline scope in
  advance rather than after you have written the code. If your idea is on that list and you think
  the list is wrong, argue with the list in an issue — that is a legitimate conversation and it
  has changed our mind before.
- **CI must be green.** `ruff check`, `ruff format --check`, and `pytest` on Python 3.11, 3.12,
  and 3.13.
- **Business logic goes in the library, never in a command handler.** `src/grantcheck/` holds the
  checks; the CLI and the MCP server are thin adapters over it. A pull request that puts a rule
  inside a Click callback will be sent back, politely, with a pointer to this line.
- **Changed behaviour needs a `CHANGELOG.md` entry** under `## Unreleased`.
- **Every new user-visible fact carries a vintage.** If a check produces output that does not say
  what dataset it came from and when that dataset was published, it is not finished.
- **No new required configuration.** The quickstart is one command with no key and no account.
  A change that breaks that will not be merged regardless of what it adds.
- **Upstream first.** If the real fix belongs in the Master Concordance File or another upstream
  project, open that pull request first and link it. Record it in
  [`docs/research/prior-art.md`](docs/research/prior-art.md).

Small, obvious fixes get merged fast. Anything that changes what the tool asserts about an
organization's legal standing gets read slowly and carefully, by more than one person, because
the cost of being confidently wrong here is somebody's grant.

## Reporting a wrong answer

This is the most valuable bug report you can file. Include:

1. The exact command you ran, including the EIN.
2. What the tool said.
3. What the official source says, with a link — the IRS Tax Exempt Organization Search page, the
   SAM.gov entity record, the actual Form 990.
4. The dataset vintages from the report footer.

Do not worry about diagnosing it. "grantcheck says this organization is revoked and the IRS
website says it is not" is a complete and excellent bug report.

## Security

Do not open a public issue for a security problem. See `SECURITY.md`.

## Code of conduct

Participation is governed by `CODE_OF_CONDUCT.md`.

---

## Good first issues for nonprofit data people who do not write Python

These are real, needed, and none of them require you to run the code. Most are pull requests
against a Markdown or a small data file, and if the GitHub editing interface is a barrier, open
an issue with the content and someone will land it for you and credit you in the commit.

**1. Review the plain-English explainers.**
`uvx grantcheck explain <check_id>` prints a paragraph for each check, and those paragraphs live
in `src/grantcheck/explanations/*.md`. They are written by people who read the regulations, not
by people who have sat across a table from a panicking executive director. If one of them is
technically correct but useless, or correct but alarming in a way the situation does not warrant,
rewrite it. Tone is a real bug here.

**2. Check our single-audit language against 2 CFR Part 200.**
We describe the $1,000,000 threshold, the change from $750,000, and the effective date of fiscal
years beginning on or after 2024-10-01. We say the check is a screen and not a determination. If
any of that is stated in a way an auditor would push back on, tell us exactly how you would word
it. `docs/research/data-sources.md` has the current wording.

**3. Send us an organization we get wrong.**
Especially: subordinates under a group exemption ruling, organizations reinstated after
revocation, churches and other organizations that are exempt without appearing in the usual
files, fiscal sponsors and their sponsored projects, and organizations whose legal name in the
IRS Business Master File does not resemble the name they registered under in SAM.gov. Each one of
these becomes a permanent test fixture. See "Reporting a wrong answer" above for the format.

**4. Audit the deductibility and foundation code tables.**
`src/grantcheck/data/codes/*.csv` maps IRS code values to the words we print — Pub 78
deductibility status codes, EO Business Master File subsection, foundation, and filing
requirement codes. These came from the IRS data dictionary and they are the kind of thing that
goes quietly stale. If a label is wrong, imprecise, or missing a value you have seen in the wild,
that is a one-line fix and a genuinely important one.

**5. Improve the NTEE display names.**
We print the IRS NTEE code and a human label. The labels are terse and some are dated. If you
work in a subsector and our label for your code reads oddly to practitioners, fix it.

**6. Write the remediation lines.**
When a check fails, the report tells the reader what to do about it — how long SAM.gov renewal
takes, which form reinstatement uses, what the retroactive reinstatement deadlines are. These
should be the words you would actually say to a client. If ours are vague, replace them. Cite the
IRS revenue procedure or the SAM.gov help article you are drawing on so we can link it.

**7. Tell us what a program officer looks at that we do not check.**
The check list is deliberately short and it is deliberately limited to hard, public,
machine-checkable disqualifications. But if there is a category of disqualification that meets
those three tests and is missing, that is the highest-value issue anyone can open on this repo.
Say what it is, where the public data lives, and describe an organization that has the problem.

## A note on Python versions and this project's CI

`requires-python` is `>=3.11` and CI runs the full test suite on 3.11, 3.12, and 3.13.
**CI is the version gate, not your laptop.** A standard-library method can gain a keyword
argument in a later release and your local run will accept it happily — `Path.read_text`
grew its `newline` parameter in 3.13, which passed locally on 3.14 and failed on 3.11 and
3.12 in CI.

If you develop on **Windows on ARM**, note that `uv python install 3.11` currently fails
there: uv's index carries `windows-x86_64` builds only, with no `windows-arm64` CPython,
so the matrix cannot be reproduced locally at all. Push and read the CI result; it takes
about two minutes.

Before reaching for a standard-library API you are not sure about, check "Changed in
version" in the CPython docs against 3.11.

