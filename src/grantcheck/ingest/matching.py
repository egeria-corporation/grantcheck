"""Inferring the EIN-to-UEI link, with a confidence score that gets printed.

**Why this exists.** You cannot look up a SAM.gov entity by EIN. Taxpayer identification
number is a sensitive-tier field, so it is neither a search parameter nor present in the
public response — verified against the Entity Management API documentation on 2026-08-31.
The public search keys are UEI, CAGE code, legal business name, and address.

So the join has to be inferred from name and state, and an inferred match is **never**
presented as a lookup. Every match carries a tier and a score, both of which appear in the
output, and below the floor the SAM checks report ``unknown`` rather than guessing.

The failure mode this is guarding against is specific: matching an organization to the
wrong SAM.gov registration and then reporting that registration's expiry as theirs. A
consultant would act on it.

``--uei`` pins the match and skips inference entirely. That is the escape hatch for every
mismatch and it is documented prominently, because no scoring function is going to be right
about every one of 1.9 million organizations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

# Below this, we do not claim a match. The three SAM checks report `unknown` with an
# instruction to re-run with --uei, which is a different thing from reporting a failure:
# "we could not identify you" must never read as "your registration is missing".
CONFIDENCE_FLOOR = 0.85

# Legal-form suffixes carry no distinguishing information and vary freely between the IRS
# legal name and the SAM.gov legal business name. "FOUNDATION" is deliberately NOT in this
# list even though it is a common trailing word: it is part of an organization's identity
# rather than a legal form, and dropping it collapses distinct names together for no gain.
LEGAL_SUFFIXES = {
    "INC",
    "INCORPORATED",
    "CORP",
    "CORPORATION",
    "LLC",
    "L L C",
    "LTD",
    "LIMITED",
    "CO",
    "COMPANY",
    "LP",
    "LLP",
    "PC",
    "PA",
    "PLLC",
}

# Expansions applied to both sides, so the two spellings of the same word compare equal.
ABBREVIATIONS = {
    "ASSN": "ASSOCIATION",
    "ASSOC": "ASSOCIATION",
    "FDN": "FOUNDATION",
    "FOUND": "FOUNDATION",
    "INTL": "INTERNATIONAL",
    "INTERNATL": "INTERNATIONAL",
    "NATL": "NATIONAL",
    "NATIONALE": "NATIONAL",
    "UNIV": "UNIVERSITY",
    "CTR": "CENTER",
    "CENTRE": "CENTER",
    "SVCS": "SERVICES",
    "SVC": "SERVICE",
    "INST": "INSTITUTE",
    "DEPT": "DEPARTMENT",
    "MT": "MOUNT",
    "ST": "SAINT",
    "AMER": "AMERICAN",
    "DEV": "DEVELOPMENT",
    "EDUC": "EDUCATION",
    "&": "AND",
}

# Deliberately NOT expanded, because the real data contradicts the obvious reading:
#
#   ORG   The IRS legal name for the Wikimedia Foundation is "WIKIMEDIA FOUNDATION ORG",
#         where ORG is the .org domain rather than an abbreviation of "organization".
#         Expanding it invents a token that the SAM.gov side does not have.
#   COMM  Community, Commission, and Committee are all common in this sector and all
#         abbreviate to COMM. Picking one is a coin flip.
#   SOC   Society and Social, likewise.
#
# An expansion is only safe when it is applied to both sides AND has one plausible reading.

_PUNCTUATION = re.compile(r"[^\w\s&]")
_WHITESPACE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Reduce a legal name to a comparable form.

    The IRS says ``SECOND HARVEST OF SILICON VALLEY``. SAM.gov may say
    ``Second Harvest Food Bank of Silicon Valley, Inc.`` Neither is wrong; they are
    different registrations of the same organization, recorded years apart by different
    people.
    """
    if not name:
        return ""

    text = name.upper()
    text = text.replace("&", " AND ")
    text = _PUNCTUATION.sub(" ", text)
    tokens = [ABBREVIATIONS.get(t, t) for t in _WHITESPACE.split(text) if t]

    # A leading "THE" is noise; a medial one is not ("FRIENDS OF THE LIBRARY").
    if tokens and tokens[0] == "THE":
        tokens = tokens[1:]

    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()

    return " ".join(tokens)


def name_similarity(left: str, right: str) -> float:
    """Blend sequence similarity with token overlap. Returns 0.0 to 1.0.

    Sequence ratio alone punishes an inserted word heavily — "Second Harvest of Silicon
    Valley" against "Second Harvest Food Bank of Silicon Valley" scores poorly despite
    obviously being the same organization. Token overlap alone rewards short generic names
    that share a couple of common words. Taking the higher of the two, with the token score
    slightly discounted, handles both without being generous to junk.
    """
    a, b = normalize_name(left), normalize_name(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    sequence = SequenceMatcher(None, a, b).ratio()

    ta, tb = set(a.split()), set(b.split())
    overlap = len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0
    # Containment: one name being a superset of the other is a strong signal, and it is the
    # common shape here because SAM registrations tend to be more verbose than IRS names.
    containment = len(ta & tb) / min(len(ta), len(tb)) if ta and tb else 0.0

    token_score = max(overlap, containment * 0.95)
    return max(sequence, token_score * 0.97)


@dataclass(frozen=True)
class Candidate:
    """One SAM.gov entity being considered as the match for an organization."""

    uei: str
    legal_name: str
    state: str | None = None
    city: str | None = None
    registration_status: str | None = None
    expiration_date: str | None = None
    purpose: str | None = None


@dataclass(frozen=True)
class MatchResult:
    """The outcome of inference. ``candidate`` is None below the floor."""

    candidate: Candidate | None
    score: float
    method: str  # 'pinned' | 'name_state' | 'none'
    tier: str  # 'pinned' | 'exact' | 'strong' | 'probable' | 'none'
    note: str
    runner_up: float = 0.0

    @property
    def confident(self) -> bool:
        return self.candidate is not None and self.score >= CONFIDENCE_FLOOR


def _tier_for(score: float) -> str:
    if score >= 0.98:
        return "exact"
    if score >= 0.92:
        return "strong"
    if score >= CONFIDENCE_FLOOR:
        return "probable"
    return "none"


def pin(candidate: Candidate) -> MatchResult:
    """A user-supplied UEI. No inference, no score to doubt."""
    return MatchResult(
        candidate=candidate,
        score=1.0,
        method="pinned",
        tier="pinned",
        note=f"SAM.gov entity pinned by the Unique Entity ID you supplied ({candidate.uei}).",
    )


def match(
    *,
    irs_name: str,
    irs_sort_name: str | None,
    state: str | None,
    city: str | None,
    candidates: list[Candidate],
) -> MatchResult:
    """Score candidates and return the best, or a no-match result.

    State is a hard filter rather than a scoring input: an organization in California is
    not registered in Ohio, and letting a high name score override a state mismatch is how
    a tool matches "Community Health Center" to the wrong one of forty.
    """
    if not candidates:
        return MatchResult(
            None, 0.0, "name_state", "none", "No SAM.gov entity was found to compare against."
        )

    pool = candidates
    if state:
        same_state = [c for c in candidates if (c.state or "").upper() == state.upper()]
        # If nothing shares the state, do not silently fall back to a nationwide comparison.
        # Report no match instead, and let --uei resolve it.
        pool = same_state

    if not pool:
        return MatchResult(
            None,
            0.0,
            "name_state",
            "none",
            f"No SAM.gov entity registered in {state} matched this organization's name.",
        )

    scored: list[tuple[float, Candidate]] = []
    for candidate in pool:
        best = name_similarity(irs_name, candidate.legal_name)
        if irs_sort_name:
            # The BMF sort name is often the name the public knows, and is sometimes what
            # the organization used when registering with SAM.
            best = max(best, name_similarity(irs_sort_name, candidate.legal_name))
        if city and candidate.city and city.upper() == candidate.city.upper():
            # Agreeing city is corroboration, not proof. A small bump, capped so it can
            # never lift a weak name match over the floor on its own.
            best = min(1.0, best + 0.03)
        scored.append((best, candidate))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    top_score, top = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else 0.0

    if top_score < CONFIDENCE_FLOOR:
        return MatchResult(
            None,
            top_score,
            "name_state",
            "none",
            (
                "Could not confidently match this EIN to a SAM.gov entity by name and "
                "state. Re-run with --uei to pin the registration."
            ),
            runner_up=runner_up,
        )

    # Two candidates that score nearly the same is not a confident match, whatever the top
    # score is. Chapters of a national organization in one state look exactly like this.
    if runner_up and (top_score - runner_up) < 0.05:
        return MatchResult(
            None,
            top_score,
            "name_state",
            "none",
            (
                f"Two or more SAM.gov entities in {state} match this name about equally "
                f"well ({top_score:.2f} and {runner_up:.2f}), so the match is ambiguous. "
                "Re-run with --uei to pin the right registration."
            ),
            runner_up=runner_up,
        )

    tier = _tier_for(top_score)
    return MatchResult(
        candidate=top,
        score=round(top_score, 3),
        method="name_state",
        tier=tier,
        note=(
            f"Matched to the SAM.gov entity {top.legal_name!r} by legal name and state, "
            f"confidence {top_score:.2f}. This is an inference, not a lookup — the IRS and "
            f"SAM.gov do not share a key. Pin it with --uei if it is wrong."
        ),
        runner_up=runner_up,
    )
