"""The index client: fetch a shard, verify it, cache it, query it.

This is what makes ``uvx grantcheck --ein 27-1067272`` return a real answer in seconds on a
machine that has never seen the tool. The published index is ~145 MB across 234 shards; a
user checking one organization downloads one shard, typically well under a megabyte.

Design constraints this file exists to satisfy:

- **The user never downloads the full dataset.** One shard, resolved from the EIN prefix.
- **No telemetry, ever.** Fetching a shard reveals an EIN *prefix* to whoever hosts the
  index, which covers hundreds of thousands of organizations. Querying a hosted API per
  run would reveal the exact EIN, which is why the tool does not do that.
- **A second run does no network I/O at all.** Cached shards are keyed by vintage and
  verified by checksum, so a warm cache is authoritative and offline use just works.
- **A corrupt download never lands in the cache.** Verify, then rename into place.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import platformdirs
import zstandard

DEFAULT_BASE_URL = "https://github.com/egeria-corporation/grantcheck/releases/latest/download"

# The manifest is small and changes monthly. Twelve hours keeps a long-running session from
# re-fetching it while still noticing a new vintage within a day.
MANIFEST_TTL_SECONDS = 12 * 60 * 60

# Vintages older than this many are pruned. Two means a user who has not refreshed still has
# a working previous vintage if the newest fails to download.
KEEP_VINTAGES = 2

USER_AGENT = "grantcheck (+https://github.com/egeria-corporation/grantcheck)"


class IndexUnavailable(RuntimeError):
    """The index could not be reached and no usable cached copy exists.

    Carries a message that says what to do next, because it is printed to a consultant
    rather than logged for a developer.
    """


class ChecksumMismatch(IndexUnavailable):
    """A downloaded shard did not match the checksum the manifest declared."""


class NoShardForPrefix(LookupError):
    """No shard covers this EIN's prefix, because no organization has one.

    Deliberately **not** an :class:`IndexUnavailable`. Ten of the hundred possible
    two-digit prefixes — 07, 09, 17, 18, 19, 28, 29, 49, 79, 89 — have no shard in the
    2026-08 index because the IRS has never issued an EIN starting with them. A well-formed
    EIN carrying one of those is definitively absent from the index, which is `not_found`
    and exit code 4, not a runtime failure and exit code 1.
    """


@dataclass(frozen=True)
class Shard:
    prefix: str
    file: str
    bytes: int
    sha256: str
    rows: int


@dataclass(frozen=True)
class Manifest:
    manifest_version: int
    vintage: str
    built_at: str
    datasets: list[dict[str, Any]]
    shards: list[Shard]
    from_cache: bool = False

    @classmethod
    def from_dict(cls, d: dict[str, Any], *, from_cache: bool = False) -> Manifest:
        try:
            return cls(
                manifest_version=d["manifest_version"],
                vintage=d["vintage"],
                built_at=d["built_at"],
                datasets=d["datasets"],
                shards=[Shard(**s) for s in d["shards"]],
                from_cache=from_cache,
            )
        except (KeyError, TypeError) as exc:
            raise IndexUnavailable(
                f"The index manifest is malformed ({exc}). This usually means a partial "
                "download. Run `grantcheck cache clear` and try again."
            ) from exc

    def resolve_shard(self, ein: str) -> Shard | None:
        """Return the most specific shard covering ``ein``.

        Oversized two-digit prefixes are split by the third digit, so both ``shard-23`` and
        ``shard-237`` can exist in one manifest. The longer prefix wins.
        """
        candidates = [s for s in self.shards if ein.startswith(s.prefix)]
        if not candidates:
            return None
        return max(candidates, key=lambda s: len(s.prefix))

    def vintage_of(self, dataset: str) -> dict[str, Any] | None:
        for d in self.datasets:
            if d.get("dataset") == dataset:
                return d
        return None


def cache_dir() -> Path:
    """Where shards live. Never written outside of this directory."""
    override = os.environ.get("GRANTCHECK_CACHE_DIR")
    if override:
        return Path(override)
    return Path(platformdirs.user_cache_dir("grantcheck"))


def base_url() -> str:
    return os.environ.get("GRANTCHECK_INDEX_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _atomic_write(dest: Path, data: bytes) -> None:
    """Write via a temporary file in the same directory, then rename.

    A partial write must never be visible under the final name. Rename within one
    filesystem is atomic on both POSIX and Windows.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, dest)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class IndexClient:
    """Fetches, caches, and queries the published index."""

    def __init__(
        self,
        *,
        base: str | None = None,
        cache: Path | None = None,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base = (base or base_url()).rstrip("/")
        self.cache = cache or cache_dir()
        self.timeout = timeout
        self._client = client
        self._manifest: Manifest | None = None

    # -- HTTP ---------------------------------------------------------------------------

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            )
        return self._client

    def _get(self, url: str) -> bytes:
        response = self._http().get(url)
        response.raise_for_status()
        return response.content

    # -- Manifest -----------------------------------------------------------------------

    @property
    def _manifest_cache_path(self) -> Path:
        return self.cache / "manifest.json"

    def manifest(self, *, force: bool = False) -> Manifest:
        """Return the current manifest, from cache when it is fresh enough.

        On a network failure with any cached manifest present, the cached one is used and
        marked ``from_cache`` so the report footer can say the data may be stale. Reporting
        a slightly old vintage with its date attached beats failing.
        """
        if self._manifest is not None and not force:
            return self._manifest

        path = self._manifest_cache_path
        fresh = (
            path.exists()
            and not force
            and (time.time() - path.stat().st_mtime) < MANIFEST_TTL_SECONDS
        )
        if fresh:
            try:
                self._manifest = Manifest.from_dict(
                    json.loads(path.read_text(encoding="utf-8")), from_cache=True
                )
                return self._manifest
            except (json.JSONDecodeError, IndexUnavailable):
                pass  # fall through and re-fetch

        try:
            raw = self._get(f"{self.base}/manifest.json")
            data = json.loads(raw.decode("utf-8"))
            manifest = Manifest.from_dict(data)
            _atomic_write(path, raw)
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            if path.exists():
                try:
                    manifest = Manifest.from_dict(
                        json.loads(path.read_text(encoding="utf-8")), from_cache=True
                    )
                except (json.JSONDecodeError, IndexUnavailable) as inner:
                    raise IndexUnavailable(
                        "Could not reach the index and the cached manifest is unreadable. "
                        "Run `grantcheck cache clear`, then try again with a network "
                        "connection."
                    ) from inner
            else:
                raise IndexUnavailable(
                    f"Could not reach the index at {self.base} ({exc}). "
                    "grantcheck needs to download a small data file the first time it "
                    "runs. Check your connection and try again; after that it works "
                    "offline."
                ) from exc

        self._manifest = manifest
        return manifest

    # -- Shards -------------------------------------------------------------------------

    def shard_path(self, vintage: str, prefix: str) -> Path:
        return self.cache / vintage / f"shard-{prefix}.sqlite"

    def ensure_shard(self, ein: str, *, manifest: Manifest | None = None) -> Path:
        """Return a local path to the decompressed shard covering ``ein``.

        Downloads and verifies it if the cache does not already hold it.
        """
        manifest = manifest or self.manifest()
        shard = manifest.resolve_shard(ein)
        if shard is None:
            raise NoShardForPrefix(
                f"No organization in the published index has an EIN starting {ein[:2]}."
            )

        local = self.shard_path(manifest.vintage, shard.prefix)
        if local.exists():
            return local

        url = f"{self.base}/{shard.file}"
        try:
            blob = self._get(url)
        except httpx.HTTPError as exc:
            raise IndexUnavailable(
                f"Could not download the data file for EIN prefix {shard.prefix} "
                f"({exc}). Check your connection and try again."
            ) from exc

        digest = hashlib.sha256(blob).hexdigest()
        if digest != shard.sha256:
            # Never leave a bad file where a later run would trust it.
            raise ChecksumMismatch(
                f"The data file for prefix {shard.prefix} did not match its published "
                f"checksum (expected {shard.sha256[:12]}…, got {digest[:12]}…). Nothing "
                "was written to the cache. This is usually a truncated download; try "
                "again."
            )

        try:
            raw = zstandard.ZstdDecompressor().decompress(blob, max_output_size=512 * 1024 * 1024)
        except zstandard.ZstdError as exc:
            raise IndexUnavailable(
                f"The data file for prefix {shard.prefix} could not be decompressed "
                f"({exc}). Nothing was written to the cache."
            ) from exc

        _atomic_write(local, raw)
        return local

    # -- Query --------------------------------------------------------------------------

    def lookup(self, ein: str, *, manifest: Manifest | None = None) -> dict[str, Any] | None:
        """Return the organization row for ``ein``, or None when it is not in the index.

        None means "not in the published index", which is a real and legitimate answer:
        churches, government instrumentalities, and newly recognized organizations are
        absent by design. It does not mean the organization does not exist.
        """
        manifest = manifest or self.manifest()
        try:
            path = self.ensure_shard(ein, manifest=manifest)
        except NoShardForPrefix:
            # No organization has this prefix, so the EIN is not in the index. Same answer
            # as a shard that simply has no matching row.
            return None
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM organization WHERE ein = ?", (ein,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def search_by_name(
        self, name: str, *, state: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Find candidate organizations by name within one already-cached shard.

        Deliberately narrow. A full name search would require every shard, which is the
        whole dataset — exactly what this design exists to avoid. See ``docs/NON-GOALS.md``:
        being a nonprofit directory is not the job.
        """
        results: list[dict[str, Any]] = []
        pattern = f"%{name.strip().upper()}%"
        for shard_file in sorted(self.cache.glob("*/shard-*.sqlite")):
            conn = sqlite3.connect(f"file:{shard_file}?mode=ro", uri=True)
            try:
                conn.row_factory = sqlite3.Row
                sql = "SELECT * FROM organization WHERE UPPER(name) LIKE ?"
                params: list[Any] = [pattern]
                if state:
                    sql += " AND state = ?"
                    params.append(state.upper())
                sql += " LIMIT ?"
                params.append(limit - len(results))
                results.extend(dict(r) for r in conn.execute(sql, params))
            finally:
                conn.close()
            if len(results) >= limit:
                break
        return results[:limit]

    # -- Cache management ---------------------------------------------------------------

    def cache_info(self) -> dict[str, Any]:
        """What is held locally, by vintage. Never touches the network."""
        vintages: dict[str, dict[str, Any]] = {}
        if not self.cache.exists():
            return {"cache_dir": str(self.cache), "vintages": {}, "total_bytes": 0}
        total = 0
        for shard in self.cache.glob("*/shard-*.sqlite"):
            vintage = shard.parent.name
            size = shard.stat().st_size
            total += size
            entry = vintages.setdefault(vintage, {"shards": 0, "bytes": 0, "prefixes": []})
            entry["shards"] += 1
            entry["bytes"] += size
            entry["prefixes"].append(shard.stem.removeprefix("shard-"))
        for entry in vintages.values():
            entry["prefixes"].sort()
        return {"cache_dir": str(self.cache), "vintages": vintages, "total_bytes": total}

    def cache_clear(self) -> int:
        """Remove every cached shard and manifest. Returns bytes freed."""
        freed = self.cache_info()["total_bytes"]
        if self.cache.exists():
            shutil.rmtree(self.cache)
        self._manifest = None
        return freed

    def prune(self, *, keep: int = KEEP_VINTAGES) -> list[str]:
        """Drop all but the newest ``keep`` vintages. Returns the vintages removed."""
        if not self.cache.exists():
            return []
        vintages = sorted(
            (p.name for p in self.cache.iterdir() if p.is_dir()),
            reverse=True,
        )
        removed = vintages[keep:]
        for vintage in removed:
            shutil.rmtree(self.cache / vintage)
        return removed

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
