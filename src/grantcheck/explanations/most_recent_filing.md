# Most recent Form 990

**What it checks.** The most recent annual return on record for this organization, and how
firmly that is known.

**Why the source matters.** Most exempt organizations file the Form 990-N e-Postcard, which
does **not** appear in the IRS Form 990 electronic-filing index at all. A tool that builds
filing history from that index alone would report roughly 1.5 million small nonprofits as
having never filed anything. This check draws on the e-Postcard file as well.

**About the fallback.** Where no filing record is available, the check falls back to the
`TAX_PERIOD` field in the Business Master File and says so explicitly. That field is the
period of the most recent return the IRS has **processed**, at month precision — it is not
a filing date, and it lags actual filing by weeks to more than a year.

**"Not applicable" is a real answer.** 433,337 organizations, including 287,356 churches,
are not required to file an annual return at all. For them an absent filing history is
expected, not a gap.

**What to do.** If a return you filed is not showing, it may simply not be processed yet —
the Business Master File lags. If returns are genuinely outstanding, file them: the
three-year counter that triggers automatic revocation does not pause, and reinstatement is
considerably more work than filing late.
