"""Generate a static JSON index from a toolspec library directory.

Usage (CLI):
    python -m bioledger_toolspec_schema.index /path/to/specs > index.json

The index is a JSON array where each entry contains the metadata needed for
discovery and search, without the full spec body. The BioLedger core
``LibraryClient`` fetches this index from GitHub Pages to offer tools.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml


def build_index(specs_dir: Path) -> list[dict]:
    """Walk a toolspec library ``specs/`` directory and extract index entries.

    Expected layout::

        specs/<family>/<tool>/spec.yaml

    Returns a list of dicts, one per tool spec, suitable for JSON serialisation.
    """
    entries: list[dict] = []

    for spec_path in sorted(specs_dir.rglob("spec.yaml")):
        try:
            raw = yaml.safe_load(spec_path.read_text())
        except Exception:
            continue

        execution = raw.get("execution") or {}
        name = execution.get("name", spec_path.parent.name)
        # Derive family from directory structure: specs/<family>/<tool>/spec.yaml
        rel = spec_path.relative_to(specs_dir)
        parts = rel.parts  # e.g. ("samtools", "samtools-faidx", "spec.yaml")
        family = parts[0] if len(parts) >= 3 else ""

        entry = {
            "name": name,
            "family": family,
            "version": execution.get("version", ""),
            "description": execution.get("description", ""),
            "container": execution.get("container", ""),
            "categories": execution.get("categories", []),
            "inputs": list((execution.get("inputs") or {}).keys()),
            "outputs": list((execution.get("outputs") or {}).keys()),
            "path": str(rel.parent),  # relative path to spec directory
        }
        entries.append(entry)

    return entries


def write_index(specs_dir: Path, output_path: Path) -> None:
    """Build the index and write it to a JSON file."""
    entries = build_index(specs_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(entries, indent=2) + "\n")


def main() -> None:
    """CLI entry point: python -m bioledger_toolspec_schema.index <specs_dir> [output.json]"""
    if len(sys.argv) < 2:
        print("Usage: python -m bioledger_toolspec_schema.index <specs_dir> [output.json]")
        sys.exit(1)

    specs_dir = Path(sys.argv[1])
    if not specs_dir.is_dir():
        print(f"Error: {specs_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) >= 3:
        output_path = Path(sys.argv[2])
        write_index(specs_dir, output_path)
    else:
        # Write to stdout
        entries = build_index(specs_dir)
        print(json.dumps(entries, indent=2))


if __name__ == "__main__":
    main()
