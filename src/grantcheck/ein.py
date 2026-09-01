"""Employer Identification Number handling.

One normalized representation is used everywhere internally: nine ASCII digits, no
separator, zero-padded. Formatting for display happens only at the output boundary.

The IRS bulk files disagree with each other about EIN formatting — some carry nine
characters, some drop a leading zero, some pad with spaces inside a pipe-delimited row.
Normalizing on the way in means ``27-0125367``, ``270125367``, and ``27 0125367`` are one
key, and so is whatever the file handed us. See ``docs/research/data-sources.md``.
"""

from __future__ import annotations

# The nine ASCII digits, explicitly. Do NOT use str.isdigit() or int() for validation:
# both accept Unicode decimal digits, so Arabic-Indic (U+0660..U+0669) and full-width
# (U+FF10..U+FF19) numerals would pass validation and then silently mismatch every lookup
# in the index. That is a wrong answer rather than an error message, and it is a real
# input — those codepoints arrive when someone pastes an EIN out of a PDF. See
# tests/test_ein.py::TestUnicodeDigits.
_ASCII_DIGITS = frozenset("0123456789")

EIN_LENGTH = 9
PREFIX_LENGTH = 2

# Separators accepted anywhere in the input: the canonical hyphen, plus the en dash and em
# dash that word processors substitute for it automatically. Built with chr() rather than
# written as glyphs so the codepoint is unambiguous in source and the file stays ASCII.
_SEPARATORS = ("-", chr(0x2013), chr(0x2014))

_EXPECTED = "Expected nine digits, for example 27-0125367 or 270125367."


class InvalidEIN(ValueError):
    """Raised when a string cannot be a valid EIN.

    The message always states what was wrong and what the expected form is, because it is
    printed directly to a consultant who is not a developer.
    """


def normalize(raw: str) -> str:
    """Return the canonical nine-digit form of ``raw``.

    Accepts hyphen, space, and no separator, with surrounding whitespace. Raises
    :class:`InvalidEIN` with an actionable message for anything else.
    """
    if raw is None:
        raise InvalidEIN(f"No EIN given. {_EXPECTED}")

    if not isinstance(raw, str):
        raise InvalidEIN(f"EIN must be text, got {type(raw).__name__}. {_EXPECTED}")

    # Strip every kind of whitespace, including the non-breaking space that arrives when
    # someone copies out of a web page or a PDF.
    stripped = "".join(raw.split())

    if not stripped:
        raise InvalidEIN(f"No EIN given. {_EXPECTED}")

    for separator in _SEPARATORS:
        stripped = stripped.replace(separator, "")
    digits = stripped

    if not digits:
        raise InvalidEIN(f"{raw!r} contains no digits. {_EXPECTED}")

    non_digits = sorted({c for c in digits if c not in _ASCII_DIGITS})
    if non_digits:
        shown = " ".join(repr(c) for c in non_digits)
        raise InvalidEIN(f"{raw!r} contains characters that are not digits: {shown}. {_EXPECTED}")

    if len(digits) != EIN_LENGTH:
        raise InvalidEIN(
            f"{raw!r} has {len(digits)} digits, but an EIN has {EIN_LENGTH}. {_EXPECTED}"
        )

    # All zeros is a placeholder, not an EIN, and rejecting it here keeps a typo or an empty
    # database field from reaching the network — which is what section 10 of the build
    # prompt asks for in naming 00-0000000.
    #
    # Note the narrowness. An earlier version rejected the whole 00 prefix, on the stated
    # grounds that the IRS never issues it. That is false, and the IRS's own published files
    # disprove it: the August 2026 index carries 136 organizations with prefix 00 — 19 in the
    # Business Master File, 14 listed in Publication 78, and 90 on the automatic revocation
    # list. Rejecting the prefix meant this tool answered "not a valid EIN" for 90
    # organizations whose exemption is actually revoked, which is the most dangerous answer
    # it could give: the caller reads it as a typo and moves on. Reject the placeholder, not
    # the prefix.
    if set(digits) == {"0"}:
        raise InvalidEIN(f"{raw!r} is all zeros, which is a placeholder, not an EIN. {_EXPECTED}")

    return digits


def is_valid(raw: str) -> bool:
    """True when :func:`normalize` would succeed. Never raises."""
    try:
        normalize(raw)
    except InvalidEIN:
        return False
    return True


def format_ein(ein: str) -> str:
    """Return the display form, ``NN-NNNNNNN``. Accepts any form :func:`normalize` does."""
    digits = normalize(ein)
    return f"{digits[:PREFIX_LENGTH]}-{digits[PREFIX_LENGTH:]}"


def prefix(ein: str) -> str:
    """Return the two-digit index shard key.

    The first two digits are a stable, well-distributed partition key. They originally
    encoded the issuing IRS district and no longer map to geography, since EINs are now
    issued by campus and online — which does not matter, because all the index needs is
    stability and spread. See ``prompts/01-build-core.md`` section 6.
    """
    return normalize(ein)[:PREFIX_LENGTH]
