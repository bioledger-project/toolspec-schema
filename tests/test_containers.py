import asyncio

import httpx
import pytest

import bioledger_toolspec_schema.containers as containers
from bioledger_toolspec_schema.containers import (
    _fetch_active_tags,
    _most_recent_specific_tag,
    _version_sort_key,
    biocontainers_url,
    has_macro,
    lookup_biocontainers_tag,
    lookup_biocontainers_tag_sync,
    resolve_most_recent_version,
)


@pytest.fixture(autouse=True)
def _clear_lookup_cache():
    """lookup_biocontainers_tag_sync is lru_cached — clear between tests so
    monkeypatched fetchers actually get called."""
    lookup_biocontainers_tag_sync.cache_clear()
    yield
    lookup_biocontainers_tag_sync.cache_clear()


class TestHasMacro:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("@TOOL_VERSION@", True),
            ("@mixed_Case9@", True),
            ("version @X@ suffix", True),
            ("1.2.3", False),
            ("@", False),
            ("@1DIGIT@", False),  # must start with letter/underscore
            ("", False),
            ("@@", False),
        ],
    )
    def test_macro_detection(self, value, expected):
        assert has_macro(value) == expected


def test_biocontainers_url():
    assert (
        biocontainers_url("samtools", "1.20--h50ea8bc_1")
        == "quay.io/biocontainers/samtools:1.20--h50ea8bc_1"
    )


class TestVersionSortKey:
    def test_semver_ordering(self):
        tags = ["1.2--b", "1.10--b", "1.9--b"]
        assert sorted(tags, key=_version_sort_key) == [
            "1.2--b",
            "1.9--b",
            "1.10--b",
        ]

    def test_nonnumeric_falls_back(self):
        # Unparseable versions sort after parseable ones without crashing
        tags = ["abc--x", "1.0--x"]
        assert sorted(tags, key=_version_sort_key)[-1] == "abc--x"

    def test_build_suffix_ignored_in_key(self):
        # Only the part before "--" determines version ordering
        assert _version_sort_key("2.0--z") == _version_sort_key("2.0--a")


class TestMostRecentSpecificTag:
    def test_ignores_latest(self):
        tags = ["latest", "1.0--b"]
        assert _most_recent_specific_tag(tags) == "1.0--b"

    def test_picks_highest_version(self):
        tags = ["1.2--b", "1.10--b", "latest"]
        assert _most_recent_specific_tag(tags) == "1.10--b"

    def test_ignores_tags_without_build_separator(self):
        tags = ["latest", "1.5", "1.2--b"]
        assert _most_recent_specific_tag(tags) == "1.2--b"

    def test_returns_none_when_no_specific_tags(self):
        assert _most_recent_specific_tag(["latest"]) is None
        assert _most_recent_specific_tag([]) is None


class _FakeResponse:
    def __init__(self, payload=None, status=200, raises=None):
        self._payload = payload
        self.status_code = status
        self._raises = raises

    def json(self):
        if self._raises:
            raise self._raises
        return self._payload


class _FakeClient:
    """Stands in for httpx.Client; yields queued responses per URL substring."""

    def __init__(self, responses, recorder):
        self._responses = responses
        self._recorder = recorder

    def __call__(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url):
        self._recorder.append(url)
        for needle, resp in self._responses.items():
            if needle in url:
                if isinstance(resp, Exception):
                    raise resp
                return resp
        return _FakeResponse(status=404)


def _patch_client(monkeypatch, responses, recorder):
    monkeypatch.setattr(
        containers.httpx,
        "Client",
        _FakeClient(responses, recorder),
    )


class TestFetchActiveTags:
    def test_returns_tag_names(self, monkeypatch):
        recorder = []
        _patch_client(
            monkeypatch,
            {"tag/": _FakeResponse(
                {"tags": [{"name": "1.0--a"}, {"name": "2.0--b"}]}
            )},
            recorder,
        )
        assert _fetch_active_tags("pkg") == {"1.0--a", "2.0--b"}
        assert "onlyActiveTags=true" in recorder[0]

    def test_non_200_returns_empty(self, monkeypatch):
        _patch_client(monkeypatch, {}, [])
        assert _fetch_active_tags("pkg") == set()

    def test_skips_non_dict_tag_entries(self, monkeypatch):
        _patch_client(
            monkeypatch,
            {"tag/": _FakeResponse(
                {"tags": [{"name": "1.0--a"}, "stray", None]}
            )},
            [],
        )
        assert _fetch_active_tags("pkg") == {"1.0--a"}

    def test_http_error_returns_empty(self, monkeypatch):
        _patch_client(
            monkeypatch,
            {"tag/": httpx.ConnectError("down")},
            [],
        )
        assert _fetch_active_tags("pkg") == set()

    def test_malformed_json_returns_empty(self, monkeypatch):
        _patch_client(
            monkeypatch,
            {"tag/": _FakeResponse(raises=ValueError("bad json"))},
            [],
        )
        assert _fetch_active_tags("pkg") == set()


def _patch_active(monkeypatch, tags):
    monkeypatch.setattr(containers, "_fetch_active_tags", lambda pkg: tags)


class TestLookupSync:
    def test_exact_version_prefix_match(self, monkeypatch):
        _patch_active(monkeypatch, {"1.20--h50ea8bc_1", "1.19--x"})
        assert lookup_biocontainers_tag_sync("samtools", "1.20") == (
            "quay.io/biocontainers/samtools:1.20--h50ea8bc_1"
        )

    def test_version_substring_fallback(self, monkeypatch):
        # No tag starts with "1.2--", but one contains the string
        _patch_active(monkeypatch, {"v1.2.3--b"})
        assert lookup_biocontainers_tag_sync("pkg", "1.2") == (
            "quay.io/biocontainers/pkg:v1.2.3--b"
        )

    def test_latest_version_falls_through_to_most_recent(self, monkeypatch):
        _patch_active(monkeypatch, {"2.0--b", "1.0--a"})
        assert lookup_biocontainers_tag_sync("pkg", "latest") == (
            "quay.io/biocontainers/pkg:2.0--b"
        )

    def test_no_version_returns_most_recent(self, monkeypatch):
        _patch_active(monkeypatch, {"2.0--b", "1.0--a", "latest"})
        assert lookup_biocontainers_tag_sync("pkg") == (
            "quay.io/biocontainers/pkg:2.0--b"
        )

    def test_no_matching_version_returns_most_recent(self, monkeypatch):
        _patch_active(monkeypatch, {"2.0--b", "1.0--a"})
        assert lookup_biocontainers_tag_sync("pkg", "9.9") == (
            "quay.io/biocontainers/pkg:2.0--b"
        )

    def test_empty_active_tags_falls_back_to_all_tags(self, monkeypatch):
        _patch_active(monkeypatch, set())
        recorder = []
        _patch_client(
            monkeypatch,
            {"includeTags": _FakeResponse(
                {"tags": {"3.0--c": {}, "latest": {}}}
            )},
            recorder,
        )
        assert lookup_biocontainers_tag_sync("pkg") == (
            "quay.io/biocontainers/pkg:3.0--c"
        )
        assert any("includeTags" in u for u in recorder)

    def test_fallback_non_200_returns_none(self, monkeypatch):
        _patch_active(monkeypatch, set())
        _patch_client(monkeypatch, {}, [])
        assert lookup_biocontainers_tag_sync("pkg") is None

    def test_fallback_http_error_returns_none(self, monkeypatch):
        _patch_active(monkeypatch, set())
        _patch_client(
            monkeypatch,
            {"includeTags": httpx.ConnectError("down")},
            [],
        )
        assert lookup_biocontainers_tag_sync("pkg") is None

    def test_only_latest_tag_returns_none(self, monkeypatch):
        _patch_active(monkeypatch, {"latest"})
        assert lookup_biocontainers_tag_sync("pkg") is None

    def test_result_is_cached(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            containers,
            "_fetch_active_tags",
            lambda pkg: (calls.append(pkg), {"1.0--a"})[1],
        )
        lookup_biocontainers_tag_sync("pkg")
        lookup_biocontainers_tag_sync("pkg")
        assert len(calls) == 1


class TestAsyncLookup:
    def test_empty_pkg_returns_none(self):
        assert asyncio.run(lookup_biocontainers_tag("")) is None

    def test_delegates_to_sync_lookup(self, monkeypatch):
        monkeypatch.setattr(
            containers,
            "lookup_biocontainers_tag_sync",
            lambda pkg, version="": f"quay.io/x/{pkg}:{version or 'r'}",
        )
        result = asyncio.run(lookup_biocontainers_tag("pkg", "1.0"))
        assert result == "quay.io/x/pkg:1.0"


class TestResolveMostRecentVersion:
    def test_strips_build_suffix(self, monkeypatch):
        async def fake(pkg, version=""):
            return "quay.io/biocontainers/pkg:0.23.4--h125f33a_5"

        monkeypatch.setattr(containers, "lookup_biocontainers_tag", fake)
        assert asyncio.run(resolve_most_recent_version("pkg")) == "0.23.4"

    def test_no_match_returns_empty(self, monkeypatch):
        async def fake(pkg, version=""):
            return None

        monkeypatch.setattr(containers, "lookup_biocontainers_tag", fake)
        assert asyncio.run(resolve_most_recent_version("pkg")) == ""
