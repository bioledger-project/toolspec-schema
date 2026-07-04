"""Jinja2 filters and environment shared by the BioLedger executor and spec tests."""

from __future__ import annotations

import os

from jinja2 import Environment


def _basename(path: str) -> str:
    """Get the filename from a path (like os.path.basename)."""
    return os.path.basename(path)


def _splitext(path: str) -> list[str]:
    """Split path into [root, ext] (like os.path.splitext)."""
    root, ext = os.path.splitext(path)
    return [root, ext]


def _stem(path: str, all: bool = False) -> str:
    """Get the filename without extension (like pathlib.Path.stem).

    When ``all`` is True, iteratively strip all extensions (e.g.
    ``reference.fna.gz`` → ``reference``). When False (default), only the
    last extension is removed.
    """
    basename = os.path.basename(path)
    if not all:
        return os.path.splitext(basename)[0]
    while True:
        root, ext = os.path.splitext(basename)
        if not ext or root == "":
            break
        basename = root
    return basename


# Pre-configured Jinja2 environment with BioLedger custom filters
_jinja_env = Environment()
_jinja_env.filters["basename"] = _basename
_jinja_env.filters["splitext"] = _splitext
_jinja_env.filters["stem"] = _stem


def render_command(command_template: str, **context: object) -> str:
    """Render a BioLedger command template using the canonical filter set."""
    return _jinja_env.from_string(command_template).render(context)


def get_jinja_env() -> Environment:
    """Return the pre-configured Jinja2 Environment with BioLedger filters."""
    return _jinja_env
