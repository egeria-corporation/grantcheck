"""Index build and client: sharding, checksum verification, caching, offline behaviour.

The client is exercised against a real index built from the real committed TEOS fixtures,
served over a stub transport. No shard bytes are fabricated: they are produced by the same
:mod:`grantcheck.ingest.build` code that produces the published artefacts.
"""

import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from grantcheck.ingest.build import (
    DatasetVintage,
    build_index,
    merge_datasets,
    plan_shards,
    write_manifest,
)
from grantcheck.ingest.teos import (
    parse_bmf,
    parse_epostcard,
    parse_pub78,
    parse_revocation,
)
from grantcheck.sources.index import (
    ChecksumMismatch,
    IndexClient,
    IndexUnavailable,
    Manifest,
)

FIXTURES = Path(__file__).parent / "fixtures" / "teos"


def load(name: str) -> str:
    return (FIXTURES / name).read_bytes().decode("utf-8")


VINTAGES = [
    DatasetVintage("bmf", date(2026, 8, 10), "https://www.irs.gov/pub/irs-soi/eo1.csv", 49),
    DatasetVintage(
        "pub78", date(2026, 8, 11), "https://apps.irs.gov/pub/epostcard/data-download-pub78.zip", 23
    ),
    DatasetVintage(
        "revocation",
        date(2026, 8, 11),
        "https://apps.irs.gov/pub/epostcard/data-download-revocation.zip",
        29,
    ),
    DatasetVintage(
        "epostcard",
        date(2026, 8, 31),
        "https://apps.irs.gov/pub/epostcard/data-download-epostcard.zip",
        11,
    ),
]


@pytest.fixture(scope="module")
def merged() -> dict:
    return merge_datasets(
        bmf=parse_bmf(load("bmf-sample.csv")),
        pub78=parse_pub78(load("pub78-sample.txt")),
        revocation=parse_revocation(load("revocation-sample.txt")),
        epostcard=parse_epostcard(load("epostcard-sample.txt")),
    )


@pytest.fixture(scope="module")
def published(tmp_path_factory: pytest.TempPathFactory, merged: dict) -> Path:
    """A real published index, built by the real build code."""
    out = tmp_path_factory.mktemp("published")
    manifest = build_index(
        merged=merged,
        vintages=VINTAGES,
        out_dir=out,
        vintage="2026-08",
        built_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    write_manifest(manifest, out)
    return out / "2026-08"


class CountingTransport(httpx.BaseTransport):
    """Serves the published directory and counts every request.

    Counting is the point: the acceptance criterion is that a second run does no network
    I/O at all, and the only honest way to assert that is to count.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.requests: list[str] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        self.requests.append(name)
        path = self.root / name
        if not path.exists():
            return httpx.Response(404, content=b"not found")
        return httpx.Response(200, content=path.read_bytes())


@pytest.fixture
def client(published: Path, tmp_path: Path) -> IndexClient:
    transport = CountingTransport(published)
    http = httpx.Client(transport=transport, base_url="https://index.test")
    c = IndexClient(base="https://index.test", cache=tmp_path / "cache", client=http)
    c.transport = transport  # type: ignore[attr-defined]
    return c


class TestSharding:
    def test_groups_by_two_digit_prefix(self) -> None:
        plan = plan_shards(["270125367", "271067272", "530196605"])
        assert set(plan) == {"27", "53"}
        assert len(plan["27"]) == 2

    def test_oversized_prefix_splits_to_three_digits(self) -> None:
        # 60,001 EINs sharing a two-digit prefix must not land in one shard.
        eins = [f"23{i:07d}" for i in range(60_001)]
        plan = plan_shards(eins)
        assert "23" not in plan
        assert all(len(p) == 3 for p in plan)
        assert sum(len(v) for v in plan.values()) == 60_001

    def test_every_ein_lands_in_exactly_one_shard(self, merged: dict) -> None:
        plan = plan_shards(merged.keys())
        placed = [e for members in plan.values() for e in members]
        assert sorted(placed) == sorted(merged)


class TestBuild:
    def test_manifest_shape(self, published: Path) -> None:
        manifest = json.loads((published / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["manifest_version"] == 1
        assert manifest["vintage"] == "2026-08"
        assert {d["dataset"] for d in manifest["datasets"]} == {
            "bmf",
            "pub78",
            "revocation",
            "epostcard",
        }
        for shard in manifest["shards"]:
            assert len(shard["sha256"]) == 64
            assert shard["bytes"] > 0
            assert (published / shard["file"]).exists()

    def test_declared_checksums_match_the_files(self, published: Path) -> None:
        import hashlib

        manifest = json.loads((published / "manifest.json").read_text(encoding="utf-8"))
        for shard in manifest["shards"]:
            blob = (published / shard["file"]).read_bytes()
            assert hashlib.sha256(blob).hexdigest() == shard["sha256"]
            assert len(blob) == shard["bytes"]

    def test_vintages_are_in_the_shard_itself(self, published: Path, tmp_path: Path) -> None:
        # A shard must be self-describing: a cached file has to state its own vintage
        # without the manifest, or an offline run cannot say how fresh its answer is.
        import zstandard

        manifest = json.loads((published / "manifest.json").read_text(encoding="utf-8"))
        blob = (published / manifest["shards"][0]["file"]).read_bytes()
        raw = zstandard.ZstdDecompressor().decompress(blob, max_output_size=64 * 1024 * 1024)
        db = tmp_path / "s.sqlite"
        db.write_bytes(raw)
        conn = sqlite3.connect(db)
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
        conn.close()
        assert meta["vintage.bmf"] == "2026-08-10"
        assert meta["vintage.epostcard"] == "2026-08-31"


class TestMerge:
    def test_union_not_intersection(self, merged: dict) -> None:
        # An organization on the revocation list but absent from the BMF still needs a row.
        # Reporting it as not-found would be wrong in the most consequential direction.
        only_revocation = [r for r in merged.values() if r["in_revocation"] and not r["in_bmf"]]
        assert only_revocation

    def test_presence_flags_are_independent(self, merged: dict) -> None:
        row = merged["271067272"]
        assert row["in_bmf"] == 1
        assert row["name"] == "CODE FOR AMERICA LABS"

    def test_bmf_absence_is_null_not_empty(self, merged: dict) -> None:
        row = next(r for r in merged.values() if not r["in_bmf"])
        assert row["subsection"] is None  # "not in the BMF", not "in it with no value"

    def test_revocation_dates_survive_the_merge(self, merged: dict) -> None:
        row = merged["001037180"]
        assert row["revocation_date"] == "2013-06-15"
        assert row["reinstatement_date"] == "2013-06-15"


class TestClientHappyPath:
    def test_lookup_downloads_verifies_and_answers(self, client: IndexClient) -> None:
        row = client.lookup("271067272")
        assert row is not None
        assert row["name"] == "CODE FOR AMERICA LABS"
        assert row["state"] == "CA"
        assert row["ntee_cd"] == "W20"

    def test_absent_ein_returns_none_not_an_error(self, client: IndexClient) -> None:
        # Churches, government instrumentalities, and newly recognized organizations are
        # legitimately absent. That is a real answer, not a failure.
        assert client.lookup("999999999") is None

    def test_resolves_the_most_specific_shard(self) -> None:
        manifest = Manifest.from_dict(
            {
                "manifest_version": 1,
                "vintage": "2026-08",
                "built_at": "x",
                "datasets": [],
                "shards": [
                    {"prefix": "23", "file": "a", "bytes": 1, "sha256": "x", "rows": 1},
                    {"prefix": "237", "file": "b", "bytes": 1, "sha256": "x", "rows": 1},
                ],
            }
        )
        assert manifest.resolve_shard("237525622").prefix == "237"
        assert manifest.resolve_shard("231111111").prefix == "23"


class TestSecondRunDoesNoNetworkIO:
    """The acceptance criterion, asserted by counting requests rather than by timing."""

    def test_warm_cache_makes_no_requests(self, client: IndexClient) -> None:
        client.lookup("271067272")
        first = list(client.transport.requests)  # type: ignore[attr-defined]
        assert first, "the first run must fetch something"

        client._manifest = None  # force it to consult the cache rather than memory
        client.transport.requests.clear()  # type: ignore[attr-defined]
        row = client.lookup("271067272")

        assert row is not None
        assert client.transport.requests == []  # type: ignore[attr-defined]

    def test_a_second_ein_in_the_same_shard_makes_no_requests(self, client: IndexClient) -> None:
        client.lookup("271067272")
        client._manifest = None
        client.transport.requests.clear()  # type: ignore[attr-defined]
        client.lookup("270000000")
        assert client.transport.requests == []  # type: ignore[attr-defined]


class TestCorruptDownloadsNeverLand:
    def test_checksum_mismatch_raises_and_writes_nothing(
        self, published: Path, tmp_path: Path
    ) -> None:
        manifest = json.loads((published / "manifest.json").read_text(encoding="utf-8"))
        target = next(s for s in manifest["shards"] if s["prefix"] == "27")

        class Corrupting(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                name = request.url.path.rsplit("/", 1)[-1]
                if name == "manifest.json":
                    return httpx.Response(200, content=(published / name).read_bytes())
                return httpx.Response(200, content=b"this is not the shard you asked for")

        cache = tmp_path / "cache"
        client = IndexClient(
            base="https://index.test",
            cache=cache,
            client=httpx.Client(transport=Corrupting(), base_url="https://index.test"),
        )
        with pytest.raises(ChecksumMismatch, match="did not match its published checksum"):
            client.lookup("271067272")

        assert not (cache / "2026-08" / f"shard-{target['prefix']}.sqlite").exists()
        assert list(cache.glob("**/*.part")) == []

    def test_truncated_shard_leaves_no_partial_file(self, published: Path, tmp_path: Path) -> None:
        manifest = json.loads((published / "manifest.json").read_text(encoding="utf-8"))
        shard = next(s for s in manifest["shards"] if s["prefix"] == "27")
        full = (published / shard["file"]).read_bytes()

        class Truncating(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                name = request.url.path.rsplit("/", 1)[-1]
                if name == "manifest.json":
                    return httpx.Response(200, content=(published / name).read_bytes())
                return httpx.Response(200, content=full[: len(full) // 2])

        cache = tmp_path / "cache"
        client = IndexClient(
            base="https://index.test",
            cache=cache,
            client=httpx.Client(transport=Truncating(), base_url="https://index.test"),
        )
        with pytest.raises(IndexUnavailable):
            client.lookup("271067272")
        assert list(cache.glob("**/shard-*.sqlite")) == []


class TestOfflineBehaviour:
    def test_cold_cache_and_no_network_gives_an_actionable_error(self, tmp_path: Path) -> None:
        class Dead(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                raise httpx.ConnectError("no route to host")

        client = IndexClient(
            base="https://index.test",
            cache=tmp_path / "cache",
            client=httpx.Client(transport=Dead(), base_url="https://index.test"),
        )
        with pytest.raises(IndexUnavailable) as excinfo:
            client.lookup("271067272")
        message = str(excinfo.value)
        assert "Check your connection" in message
        assert "Traceback" not in message

    def test_warm_cache_survives_the_network_going_away(
        self, published: Path, tmp_path: Path
    ) -> None:
        cache = tmp_path / "cache"
        warm = IndexClient(
            base="https://index.test",
            cache=cache,
            client=httpx.Client(
                transport=CountingTransport(published), base_url="https://index.test"
            ),
        )
        warm.lookup("271067272")

        class Dead(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                raise httpx.ConnectError("no route to host")

        offline = IndexClient(
            base="https://index.test",
            cache=cache,
            client=httpx.Client(transport=Dead(), base_url="https://index.test"),
        )
        row = offline.lookup("271067272")
        assert row is not None
        assert row["name"] == "CODE FOR AMERICA LABS"

    def test_cached_manifest_is_marked_as_such(self, published: Path, tmp_path: Path) -> None:
        cache = tmp_path / "cache"
        warm = IndexClient(
            base="https://index.test",
            cache=cache,
            client=httpx.Client(
                transport=CountingTransport(published), base_url="https://index.test"
            ),
        )
        warm.manifest()

        class Dead(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                raise httpx.ConnectError("down")

        offline = IndexClient(
            base="https://index.test",
            cache=cache,
            client=httpx.Client(transport=Dead(), base_url="https://index.test"),
        )
        # The footer has to be able to say the vintage may be stale.
        assert offline.manifest().from_cache is True


class TestMalformedManifest:
    def test_malformed_manifest_is_actionable(self, tmp_path: Path) -> None:
        class Garbage(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                return httpx.Response(200, content=b'{"nope": true}')

        client = IndexClient(
            base="https://index.test",
            cache=tmp_path / "cache",
            client=httpx.Client(transport=Garbage(), base_url="https://index.test"),
        )
        with pytest.raises(IndexUnavailable, match="malformed"):
            client.manifest()


class TestCacheManagement:
    def test_cache_info_reports_what_is_held(self, client: IndexClient) -> None:
        client.lookup("271067272")
        info = client.cache_info()
        assert info["total_bytes"] > 0
        assert "2026-08" in info["vintages"]
        assert info["vintages"]["2026-08"]["shards"] >= 1

    def test_cache_info_on_an_empty_cache(self, tmp_path: Path) -> None:
        client = IndexClient(base="https://index.test", cache=tmp_path / "nothing")
        info = client.cache_info()
        assert info["total_bytes"] == 0
        assert info["vintages"] == {}

    def test_clear_removes_everything(self, client: IndexClient) -> None:
        client.lookup("271067272")
        freed = client.cache_clear()
        assert freed > 0
        assert client.cache_info()["total_bytes"] == 0

    def test_prune_keeps_the_newest_vintages(self, client: IndexClient) -> None:
        client.lookup("271067272")
        for old in ("2026-05", "2026-06", "2026-07"):
            (client.cache / old).mkdir(parents=True, exist_ok=True)
            (client.cache / old / "shard-27.sqlite").write_bytes(b"x")
        removed = client.prune(keep=2)
        assert set(removed) == {"2026-05", "2026-06"}
        assert (client.cache / "2026-08").exists()
        assert (client.cache / "2026-07").exists()


class TestPrivacy:
    def test_only_a_prefix_is_ever_requested(self, client: IndexClient) -> None:
        # The URL must never carry the full EIN. Fetching shard-27 reveals a prefix that
        # covers hundreds of thousands of organizations; requesting the EIN itself would
        # tell whoever hosts the index exactly who is being researched.
        client.lookup("271067272")
        for name in client.transport.requests:  # type: ignore[attr-defined]
            assert "271067272" not in name
            assert "1067272" not in name


class TestRepeatRevocation:
    """An organization can be revoked, reinstated, and revoked again.

    19,136 EINs carry more than one row on the 2026-08-11 Automatic Revocation List.
    Current status must come from the row with the latest revocation date. Taking the last
    row by file position happens to be right while the file is chronologically sorted, and
    would silently invert the answer for all 19,136 if upstream ever re-sorted it.

    The fixture stores its rows in reverse chronological order precisely so that a
    file-order merge fails here rather than passing by luck.
    """

    @pytest.fixture(scope="class")
    @classmethod
    def repeat(cls) -> dict:
        return merge_datasets(
            bmf=parse_bmf(load("bmf-sample.csv")),
            pub78=parse_pub78(load("pub78-sample.txt")),
            revocation=parse_revocation(load("revocation-multi.txt")),
            epostcard=parse_epostcard(load("epostcard-sample.txt")),
        )

    def test_fixture_is_stored_in_reverse_order(self) -> None:
        rows = parse_revocation(load("revocation-multi.txt")).rows
        first = next(r for r in rows if r["ein"] == "001037180")
        assert first["revocation_date"].year == 2017, (
            "the fixture must lead with the LATER revocation, so a file-order merge fails"
        )

    @pytest.mark.parametrize(
        ("ein", "year"),
        [("001037180", 2017), ("003754390", 2019), ("010275502", 2017)],
    )
    def test_latest_revocation_wins(self, repeat: dict, ein: str, year: int) -> None:
        row = repeat[ein]
        assert row["revocation_date"].startswith(str(year))

    @pytest.mark.parametrize("ein", ["001037180", "003754390", "010275502"])
    def test_currently_revoked_not_masked_by_an_old_reinstatement(
        self, repeat: dict, ein: str
    ) -> None:
        # Each of these was reinstated once, then revoked again and never reinstated.
        # Carrying the old reinstatement date forward would report them as in good standing.
        assert repeat[ein]["reinstatement_date"] is None

    def test_every_ein_appears_once_after_the_merge(self, repeat: dict) -> None:
        rows = parse_revocation(load("revocation-multi.txt")).rows
        assert len(rows) == 6
        assert len({r["ein"] for r in rows}) == 3
        for ein in ("001037180", "003754390", "010275502"):
            assert ein in repeat


class TestUserAgentIsLoadBearing:
    """The descriptive User-Agent is required, not politeness.

    Cloudflare, which fronts the published index, returns 403 to the default
    ``Python-urllib`` agent. This was found when the ingest workflow's own verification
    step got a 403 fetching what it had just successfully uploaded. The client works
    because it sets a descriptive agent; drop that header and every user gets 403.
    """

    def test_the_client_sends_a_descriptive_agent(self, published: Path, tmp_path: Path) -> None:
        seen: list[str] = []

        class Recording(httpx.BaseTransport):
            def __init__(self, root: Path) -> None:
                self.root = root

            def handle_request(self, request: httpx.Request) -> httpx.Response:
                seen.append(request.headers.get("user-agent", ""))
                path = self.root / request.url.path.rsplit("/", 1)[-1]
                if not path.exists():
                    return httpx.Response(404, content=b"missing")
                return httpx.Response(200, content=path.read_bytes())

        from grantcheck.sources.index import USER_AGENT

        client = IndexClient(base="https://index.test", cache=tmp_path / "cache")
        client._client = httpx.Client(
            transport=Recording(published),
            base_url="https://index.test",
            headers={"User-Agent": USER_AGENT},
        )
        client.lookup("271067272")

        assert seen, "no requests were made"
        for agent in seen:
            assert "grantcheck" in agent
            assert "python-urllib" not in agent.lower()

    def test_the_agent_names_the_project_and_a_contact_url(self) -> None:
        from grantcheck.sources.index import USER_AGENT

        # A bare token tells an operator nothing about who to contact when traffic looks
        # odd. Being identifiable is what keeps free public infrastructure usable.
        assert "grantcheck" in USER_AGENT
        assert "github.com/egeria-corporation" in USER_AGENT
