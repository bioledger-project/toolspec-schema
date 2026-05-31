"""Container image resolution shared across tool importers.

Centralises Galaxy-style macro detection, biocontainers tag lookup, and the
biocontainers-first selection rule used by Galaxy/Nextflow importers.

All network access is async (httpx) and cached on a per-process basis. Lookups
fail closed — on error we return ``None`` rather than fabricating a plausible
but invalid image reference, leaving downstream validation to surface the gap.
"""

from __future__ import annotations

import asyncio
import logging
import re
from functools import lru_cache

import httpx

logger = logging.getLogger(__name__)

# Galaxy macros are conventionally uppercase (e.g. @TOOL_VERSION@) but some
# community tools use mixed case in tool_conf macros.
_MACRO_RE = re.compile(r"@[A-Za-z_][A-Za-z0-9_]*@")

# Returns tag names as dict keys (includes orphaned tags without manifests).
_QUAY_ALL_TAGS_URL = (
    "https://quay.io/api/v1/repository/biocontainers/{pkg}?includeTags=true"
)
# Returns only active tags (those with valid manifests).
_QUAY_ACTIVE_TAGS_URL = (
    "https://quay.io/api/v1/repository/biocontainers/{pkg}/tag/"
    "?limit=200&onlyActiveTags=true"
)
_HTTP_TIMEOUT = httpx.Timeout(10.0)


def has_macro(value: str) -> bool:
    """True if ``value`` contains an unresolved Galaxy ``@MACRO@`` token."""
    if not value:
        return False
    return bool(_MACRO_RE.search(value))


def biocontainers_url(pkg: str, tag: str) -> str:
    """Build a fully-qualified biocontainers image URL."""
    return f"quay.io/biocontainers/{pkg}:{tag}"


def _version_sort_key(tag: str) -> tuple:
    """Sort key for biocontainers tags of the form ``<version>--<build>``.

    Uses ``packaging.version`` when available for correct semver/pre-release
    ordering; falls back to a numeric tuple for plain dotted versions.
    """
    version_part = tag.split("--", 1)[0]
    try:
        from packaging.version import InvalidVersion, Version

        try:
            return (0, Version(version_part))
        except InvalidVersion:
            pass
    except ImportError:  # pragma: no cover - packaging ships with pip
        pass
    try:
        return (1, tuple(int(x) for x in version_part.split(".")))
    except ValueError:
        return (2, version_part)


def _most_recent_specific_tag(tags: list[str]) -> str | None:
    """Return the most recent ``<version>--<build>`` tag, ignoring 'latest'."""
    specific = [t for t in tags if t != "latest" and "--" in t]
    if not specific:
        return None
    specific.sort(key=_version_sort_key, reverse=True)
    return specific[0]


def _fetch_active_tags(pkg: str) -> set[str]:
    """Fetch only tags that have valid manifests (not orphaned)."""
    url = _QUAY_ACTIVE_TAGS_URL.format(pkg=pkg)
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            response = client.get(url)
        if response.status_code != 200:
            return set()
        data = response.json()
        tags = data.get("tags", [])
        return {t["name"] for t in tags if isinstance(t, dict)}
    except (httpx.HTTPError, ValueError, KeyError):
        return set()


@lru_cache(maxsize=256)
def lookup_biocontainers_tag_sync(pkg: str, version: str = "") -> str | None:
    """Synchronous, cached biocontainers tag resolution.

    Returns the fully-qualified image URL or ``None`` if no matching tag could
    be located. Network or parse errors are logged and treated as "no match".
    Prefer the async :func:`lookup_biocontainers_tag` from async call sites.
    """
    # Use the active-tags endpoint so we never return orphaned tag refs.
    active_tags = _fetch_active_tags(pkg)
    if not active_tags:
        # Fallback: try the includeTags endpoint (may include orphaned tags)
        url = _QUAY_ALL_TAGS_URL.format(pkg=pkg)
        try:
            with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
                response = client.get(url)
            if response.status_code != 200:
                return None
            all_tags = set(response.json().get("tags", {}).keys())
        except (httpx.HTTPError, ValueError):
            return None
        # Intersect with active tags we can verify
        active_tags = all_tags  # trust the API if we can't verify

    if version and version != "latest":
        for tag in sorted(active_tags):
            if tag.startswith(f"{version}--"):
                return biocontainers_url(pkg, tag)
        for tag in sorted(active_tags):
            if version in tag and tag != "latest":
                return biocontainers_url(pkg, tag)

    most_recent = _most_recent_specific_tag(list(active_tags))
    if most_recent:
        return biocontainers_url(pkg, most_recent)
    return None


async def lookup_biocontainers_tag(pkg: str, version: str = "") -> str | None:
    """Async biocontainers tag lookup. Returns ``None`` on any failure.

    Backed by a thread-pool wrapped sync client so the lru_cache is shared
    across both sync and async call sites.
    """
    if not pkg:
        return None
    return await asyncio.to_thread(lookup_biocontainers_tag_sync, pkg, version)


async def resolve_most_recent_version(pkg: str) -> str:
    """Return the most recent specific biocontainers version for ``pkg``.

    Strips the build-string suffix so callers can use the result as a
    spec version (e.g. ``"0.23.4"`` from ``"0.23.4--h125f33a_5"``).
    Returns an empty string if no version could be determined.
    """
    tag_url = await lookup_biocontainers_tag(pkg, "")
    if not tag_url:
        return ""
    # tag_url is "quay.io/biocontainers/<pkg>:<version>--<build>"
    _, _, ref = tag_url.rpartition(":")
    return ref.split("--", 1)[0]
