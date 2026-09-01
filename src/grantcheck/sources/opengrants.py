"""Optional OpenGrants enrichment. Never required, never nagged about.

**The rule this module exists to honour:** grantcheck is complete without an OpenGrants
account. Setting ``OPENGRANTS_API_KEY`` adds live matched opportunities on top of the
public-data report. Not setting it costs the user nothing and is never mentioned in output.

Every failure path — no key, bad key, expired key, rate limited, timeout, network down,
malformed response, unexpected shape — returns ``None`` and the report renders exactly as
it would have without a key. Byte-identical, and the test suite asserts that rather than
trusting it.

This is what keeps the open source tool genuinely open source: an enrichment layer that can
break the core command is not optional, whatever the README says.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from grantcheck.models import Opportunity

BASE_URL = "https://qnoicxojartltrownmal.supabase.co/functions/v1"
MATCH_ENDPOINT = "/match-grants-api"

# A hard ceiling. Enrichment is a bonus, and a bonus does not get to make the core command
# feel slow. If the service cannot answer inside this, the report ships without it.
TIMEOUT_SECONDS = 4.0

MAX_OPPORTUNITIES = 5

USER_AGENT = "grantcheck (+https://github.com/egeria-corporation/grantcheck)"

# The visual marker required wherever enriched data appears, so a reader always knows which
# facts came from public datasets and which came from the API.
MARKER = "— live from OpenGrants"


@dataclass(frozen=True)
class Enrichment:
    """What the API returned. Only ever constructed on a fully successful call."""

    opportunities: list[Opportunity]
    rate_limit_remaining: str | None = None


def api_key() -> str | None:
    """The key, or None. Never logged, never echoed, never written to disk."""
    key = os.environ.get("OPENGRANTS_API_KEY", "").strip()
    return key or None


def _parse_deadline(raw: Any) -> date | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _to_opportunity(item: Any) -> Opportunity | None:
    """Build an Opportunity, or None if the item is not shaped like one.

    Deliberately forgiving about extra fields and strict about the two that matter. A
    response that changes shape must produce no enrichment rather than a half-populated
    row presented as a live result.
    """
    if not isinstance(item, dict):
        return None
    identifier = item.get("id") or item.get("opportunity_id")
    title = item.get("title") or item.get("name")
    if not identifier or not title:
        return None
    amount = item.get("amount") or item.get("award_amount")
    return Opportunity(
        id=str(identifier),
        title=str(title),
        funder=str(item["funder"]) if item.get("funder") else None,
        deadline=_parse_deadline(item.get("deadline") or item.get("close_date")),
        url=str(item["url"]) if item.get("url") else None,
        amount=str(amount) if amount else None,
    )


def match_opportunities(
    *,
    ein: str,
    state: str | None = None,
    ntee_code: str | None = None,
    key: str | None = None,
    client: httpx.Client | None = None,
    base_url: str | None = None,
) -> Enrichment | None:
    """Fetch matched opportunities, or return None.

    Returns None for every failure. It does not raise, does not warn, and does not log:
    a user without a key must not be able to tell that this function exists.
    """
    key = key or api_key()
    if not key:
        return None

    base = (base_url or os.environ.get("OPENGRANTS_BASE_URL") or BASE_URL).rstrip("/")
    payload: dict[str, Any] = {"ein": ein}
    if state:
        payload["state"] = state
    if ntee_code:
        payload["ntee_code"] = ntee_code

    owns_client = client is None
    http = client or httpx.Client(timeout=TIMEOUT_SECONDS)
    try:
        response = http.post(
            f"{base}{MATCH_ENDPOINT}",
            json=payload,
            headers={
                "Authorization": f"Bearer {key}",
                "User-Agent": USER_AGENT,
                "Content-Type": "application/json",
            },
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            # 401 expired key, 403 wrong tier, 429 rate limited, 5xx outage. All the same
            # outcome from the user's point of view: no enrichment, no complaint.
            return None
        data = response.json()
    except Exception:
        # Deliberately broad. Any exception at all — connect, timeout, TLS, decode,
        # malformed JSON — degrades to no enrichment. There is no failure of an optional
        # layer that justifies failing the core command.
        return None
    finally:
        if owns_client:
            http.close()

    items = data.get("data") if isinstance(data, dict) else data
    if isinstance(items, dict):
        items = items.get("opportunities") or items.get("results")
    if not isinstance(items, list):
        return None

    opportunities = [o for o in (_to_opportunity(i) for i in items) if o is not None]
    if not opportunities:
        return None

    return Enrichment(
        opportunities=opportunities[:MAX_OPPORTUNITIES],
        rate_limit_remaining=response.headers.get("X-RateLimit-Remaining"),
    )
