"""Parsers for the four IRS Tax Exempt Organization Search bulk datasets.

Everything here was written against the real files, not against the documentation. Where
the two disagree, this module follows the bytes and says so in a comment.

What the 2026-08 vintage actually looks like:

======================  ==========  =======  ======  =========================
dataset                 delimiter   header   fields  rows
======================  ==========  =======  ======  =========================
EO Business Master File comma        yes      28     1,957,340 across eo1-eo4
Publication 78          pipe         **no**    6     1,412,318
Automatic Revocation    pipe         **no**   12     1,246,171
Form 990-N e-Postcard   pipe         **no**   26     1,543,373
======================  ==========  =======  ======  =========================

Three things that will produce a plausible wrong answer if ignored:

1. **The three pipe-delimited files have no header row and open with two blank lines.**
   The research notes said to read a header and map names to indices. There is no header.
   Parsing is positional, and the field count is the only structural check available.

2. **The pipe files have no quoting convention, and real rows contain literal pipes.** In
   the 2026-08-31 e-Postcard file exactly five rows carry a pipe inside the website or
   officer field. ``split("|")`` shifts them, and because the columns after the shift are
   still parseable the result looks fine and is wrong. Those rows are quarantined and
   counted, never repaired by guessing.

3. **The Business Master File is the opposite: it DOES use RFC 4180 quoting.** Twenty-nine
   rows carry a comma inside a quoted field. It must go through :mod:`csv`, never through
   ``split(",")``.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date

# --- Field counts. The only structural check the pipe files allow, since they carry no header.
PUB78_FIELDS = 6
REVOCATION_FIELDS = 12
EPOSTCARD_FIELDS = 26
BMF_FIELDS = 28

BMF_COLUMNS = [
    "EIN",
    "NAME",
    "ICO",
    "STREET",
    "CITY",
    "STATE",
    "ZIP",
    "GROUP",
    "SUBSECTION",
    "AFFILIATION",
    "CLASSIFICATION",
    "RULING",
    "DEDUCTIBILITY",
    "FOUNDATION",
    "ACTIVITY",
    "ORGANIZATION",
    "STATUS",
    "TAX_PERIOD",
    "ASSET_CD",
    "INCOME_CD",
    "FILING_REQ_CD",
    "PF_FILING_REQ_CD",
    "ACCT_PD",
    "ASSET_AMT",
    "INCOME_AMT",
    "REVENUE_AMT",
    "NTEE_CD",
    "SORT_NAME",
]

_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}  # fmt: skip


class QuarantinedRow(Exception):
    """A row whose structure does not match the format. Counted, never guessed at."""


@dataclass
class ParseResult:
    """Rows that parsed, plus an honest accounting of the ones that did not.

    ``quarantined`` is not an error log to be ignored. A jump in its size between two
    monthly vintages means the IRS changed something, which is exactly what an ingest
    needs to notice before it publishes.
    """

    rows: list[dict] = field(default_factory=list)
    quarantined: list[tuple[int, str, str]] = field(default_factory=list)  # (line_no, reason, raw)

    # A malformed value in an otherwise well-formed row. The field is nulled and the row is
    # kept, because discarding a whole organization over one cosmetic field loses more than
    # it protects. Counted separately from quarantine so a jump is still visible.
    field_warnings: list[tuple[int, str, str]] = field(default_factory=list)  # (line, field, why)

    @property
    def ok(self) -> int:
        return len(self.rows)

    @property
    def rejected(self) -> int:
        return len(self.quarantined)

    @property
    def warned(self) -> int:
        return len(self.field_warnings)

    def quarantine_rate(self) -> float:
        total = self.ok + self.rejected
        return self.rejected / total if total else 0.0


def normalize_ein(raw: str) -> str:
    """Zero-pad to nine digits. Some files drop a leading zero; all of them must key alike."""
    return raw.strip().replace("-", "").zfill(9)


def parse_irs_date(raw: str) -> date | None:
    """Parse the ``DD-MON-YYYY`` form the revocation file uses, e.g. ``15-NOV-2017``.

    Returns ``None`` for an empty field rather than raising. An absent reinstatement date
    is the normal case and carries meaning; it is not a parse failure.
    """
    raw = raw.strip()
    if not raw:
        return None
    parts = raw.split("-")
    if len(parts) != 3:
        raise ValueError(f"expected DD-MON-YYYY, got {raw!r}")
    day, mon, year = parts
    month = _MONTHS.get(mon.upper())
    if month is None:
        raise ValueError(f"unknown month abbreviation {mon!r} in {raw!r}")
    return date(int(year), month, int(day))


def parse_mmddyyyy(raw: str) -> date | None:
    """Parse the ``MM-DD-YYYY`` form the e-Postcard file uses for tax periods."""
    raw = raw.strip()
    if not raw:
        return None
    parts = raw.split("-")
    if len(parts) != 3:
        raise ValueError(f"expected MM-DD-YYYY, got {raw!r}")
    month, day, year = parts
    return date(int(year), int(month), int(day))


def parse_yyyymm(raw: str) -> str | None:
    """Return ``YYYY-MM`` from the BMF's six-digit month-precision fields.

    The BMF gives ``RULING`` and ``TAX_PERIOD`` at month precision. Rendering either as a
    full date invents a day that the source never claimed.
    """
    raw = raw.strip()
    if not raw or raw == "0" or set(raw) == {"0"}:
        return None
    if len(raw) != 6 or not raw.isascii() or not raw.isdigit():
        raise ValueError(f"expected YYYYMM, got {raw!r}")
    year, month = raw[:4], raw[4:]
    if not 1 <= int(month) <= 12:
        raise ValueError(f"month out of range in {raw!r}")
    return f"{year}-{month}"


def _iter_pipe_lines(text: str) -> Iterator[tuple[int, str]]:
    """Yield (line_number, line) for non-blank lines.

    The real files open with two blank lines and carry a couple more at the end. Line
    numbers are 1-based and count from the true start of the file, so a quarantine report
    points at something a human can find.
    """
    for i, line in enumerate(text.split("\n"), start=1):
        line = line.rstrip("\r")
        if line.strip():
            yield i, line


def _parse_pipe(text: str, *, expected: int, build: object, label: str) -> ParseResult:
    result = ParseResult()
    for line_no, line in _iter_pipe_lines(text):
        fields = line.split("|")
        if len(fields) != expected:
            # No quoting convention exists in this format, so a field containing a literal
            # pipe cannot be recovered. Guessing would produce a shifted row that still
            # parses and is wrong.
            result.quarantined.append(
                (line_no, f"expected {expected} fields, found {len(fields)}", line)
            )
            continue
        try:
            result.rows.append(build(fields))  # type: ignore[operator]
        except (ValueError, IndexError) as exc:
            result.quarantined.append((line_no, f"{label}: {exc}", line))
    return result


def parse_pub78(text: str) -> ParseResult:
    """Publication 78 Data: organizations eligible for tax-deductible contributions.

    Six pipe-delimited fields, no header: EIN, name, city, state, country, deductibility
    code. Codes observed in the 2026-08 vintage include ``PC`` (public charity), ``PF``
    (private foundation), ``POF``, ``SO``, ``SOUNK``, ``EO``, ``GROUP``, and comma-joined
    combinations such as ``EO,LODGE``. Do not treat the code as a single token.
    """

    def build(f: list[str]) -> dict:
        return {
            "ein": normalize_ein(f[0]),
            "name": f[1].strip(),
            "city": f[2].strip(),
            "state": f[3].strip(),
            "country": f[4].strip(),
            "deductibility_code": f[5].strip(),
        }

    return _parse_pipe(text, expected=PUB78_FIELDS, build=build, label="pub78")


def parse_revocation(text: str) -> ParseResult:
    """Automatic Revocation of Exemption List.

    Twelve pipe-delimited fields, no header. The last one is the reinstatement date, and
    it is populated for 181,259 of the 1,246,171 rows in the 2026-08-11 vintage.

    **Presence on this list does not mean currently revoked.** Reinstated organizations
    stay on it permanently with a reinstatement date filled in. Reading membership alone
    as "revoked" would wrongly report roughly one in seven listed organizations as
    ineligible for federal money. The caller decides status from the dates; this parser
    only reports them.
    """

    def build(f: list[str]) -> dict:
        return {
            "ein": normalize_ein(f[0]),
            "name": f[1].strip(),
            "dba": f[2].strip(),
            "street": f[3].strip(),
            "city": f[4].strip(),
            "state": f[5].strip(),
            "zip": f[6].strip(),
            "country": f[7].strip(),
            "exemption_type": f[8].strip(),
            "revocation_date": parse_irs_date(f[9]),
            "revocation_posting_date": parse_irs_date(f[10]),
            "reinstatement_date": parse_irs_date(f[11]),
        }

    return _parse_pipe(text, expected=REVOCATION_FIELDS, build=build, label="revocation")


def parse_epostcard(text: str) -> ParseResult:
    """Form 990-N (e-Postcard) filings, one row per EIN — the most recent filing.

    Twenty-six pipe-delimited fields, no header. This file is the reason filing recency
    cannot be computed from the e-file index alone: most small exempt organizations file
    the 990-N and never appear in the XML index at all.

    Five rows in the 2026-08-31 vintage carry a literal pipe inside the website or officer
    field and are quarantined. See ``tests/fixtures/teos/epostcard-embedded-pipes.txt``.
    """

    def build(f: list[str]) -> dict:
        return {
            "ein": normalize_ein(f[0]),
            "tax_year": f[1].strip(),
            "name": f[2].strip(),
            "gross_receipts_under_50k": f[3].strip().upper() == "T",
            "terminated": f[4].strip().upper() == "T",
            "tax_period_begin": parse_mmddyyyy(f[5]),
            "tax_period_end": parse_mmddyyyy(f[6]),
            "website": f[7].strip(),
            "officer_name": f[8].strip(),
            "city": f[18].strip(),
            "state": f[20].strip(),
        }

    return _parse_pipe(text, expected=EPOSTCARD_FIELDS, build=build, label="epostcard")


def parse_bmf(text: str) -> ParseResult:
    """Exempt Organizations Business Master File — the roster the whole index is built on.

    Comma-delimited **with a header**, unlike the other three, and **with RFC 4180
    quoting**: twenty-nine rows in the 2026-08-10 vintage carry a comma inside a quoted
    field. This goes through :mod:`csv`, never through ``split(",")``.

    The header is read and mapped by name rather than by position, and the expected column
    set is asserted, so a column inserted upstream fails loudly instead of shifting every
    field silently.
    """
    result = ParseResult()
    reader = csv.reader(io.StringIO(text, newline=""))

    try:
        header = next(reader)
    except StopIteration:
        return result

    header = [h.strip() for h in header]
    if header != BMF_COLUMNS:
        missing = [c for c in BMF_COLUMNS if c not in header]
        extra = [c for c in header if c not in BMF_COLUMNS]
        raise ValueError(
            f"BMF header changed. missing={missing} unexpected={extra}. "
            "Refusing to parse positionally against an unknown layout."
        )

    index = {name: i for i, name in enumerate(header)}

    for line_no, row in enumerate(reader, start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) != BMF_FIELDS:
            result.quarantined.append(
                (line_no, f"expected {BMF_FIELDS} fields, found {len(row)}", ",".join(row))
            )
            continue

        def cell(name: str, r: list[str] = row) -> str:
            return r[index[name]].strip()

        def month_field(name: str, line: int = line_no, cell=cell) -> str | None:
            """Parse a YYYYMM field, nulling it rather than losing the organization.

            The real file contains rows like ``RULING=190900`` — a year with month ``00``.
            Quarantining the whole row would drop a live organization with a perfectly good
            EIN, name, subsection, and status over a field used only for display.
            """
            try:
                return parse_yyyymm(cell(name))
            except ValueError as exc:
                result.field_warnings.append((line, name, str(exc)))
                return None

        try:
            result.rows.append(
                {
                    "ein": normalize_ein(cell("EIN")),
                    "name": cell("NAME"),
                    "ico": cell("ICO"),
                    "street": cell("STREET"),
                    "city": cell("CITY"),
                    "state": cell("STATE"),
                    "zip": cell("ZIP"),
                    # Non-zero means a subordinate under a group ruling. Critical: such an
                    # organization is legitimately absent from Publication 78 and often has
                    # no filings of its own, because both are covered by the central
                    # organization. Flagging either as a problem is a false accusation.
                    "group_exemption": cell("GROUP"),
                    "subsection": cell("SUBSECTION"),
                    "affiliation": cell("AFFILIATION"),
                    "classification": cell("CLASSIFICATION"),
                    "ruling": month_field("RULING"),
                    "deductibility": cell("DEDUCTIBILITY"),
                    "foundation": cell("FOUNDATION"),
                    "organization": cell("ORGANIZATION"),
                    "status": cell("STATUS"),
                    # NOT a filing date. It is the period of the most recent processed
                    # return, at month precision, lagging actual filing by weeks to over a
                    # year. Only ever a labelled fallback for recency.
                    "tax_period": month_field("TAX_PERIOD"),
                    "filing_req_cd": cell("FILING_REQ_CD"),
                    "pf_filing_req_cd": cell("PF_FILING_REQ_CD"),
                    "asset_amt": cell("ASSET_AMT"),
                    "income_amt": cell("INCOME_AMT"),
                    "revenue_amt": cell("REVENUE_AMT"),
                    "ntee_cd": cell("NTEE_CD"),
                    "sort_name": cell("SORT_NAME"),
                }
            )
        except ValueError as exc:
            result.quarantined.append((line_no, f"bmf: {exc}", ",".join(row)))

    return result


# AFFILIATION codes that mean "covered by ANOTHER organization's group ruling", and so
# legitimately absent from Publication 78.
#
# A non-zero GROUP alone is not enough, because a central organization carries the group
# exemption number too. Measured across all 1.6M subsection-03 rows in the 2026-08-10
# vintage, against the 2026-08-11 Publication 78 file:
#
#     AFFILIATION 9 (subordinate)  237,871 orgs    0.0% listed in Pub 78
#     AFFILIATION 7 (intermediate)      32 orgs    0.0% listed
#     AFFILIATION 6 (central)        1,844 orgs   99.4% listed
#     AFFILIATION 8                    716 orgs   99.6% listed
#     no group exemption         1,394,326 orgs   99.7% listed
#
# So 7 and 9 are covered by someone else's ruling; 6 and 8 are listed in their own right.
_COVERED_BY_ANOTHERS_RULING = frozenset({"7", "9"})


def is_group_subordinate(bmf_row: dict) -> bool:
    """True when this organization is covered by another organization's group ruling.

    Such an organization is legitimately absent from Publication 78 and often has no
    filings of its own, because the central organization covers both. Reporting either as
    a problem tells a compliant organization it cannot receive tax-deductible
    contributions, which is the single most damaging false accusation this tool could make
    about a small nonprofit.

    Requires **both** a non-zero group exemption number and a subordinate ``AFFILIATION``.
    Checking ``GROUP`` alone would sweep in central organizations, which carry the same
    number and are listed in Publication 78 normally.
    """
    group = (bmf_row.get("group_exemption") or "").strip()
    if not group or set(group) == {"0"}:
        return False
    return (bmf_row.get("affiliation") or "").strip() in _COVERED_BY_ANOTHERS_RULING
