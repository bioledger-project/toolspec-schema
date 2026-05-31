# bioledger-toolspec-schema

Pydantic models, YAML loader, and validator for the **BioLedger tool spec** format.

This package defines the contract that every tool spec YAML in
[`bioledger-toolspec-library`](../bioledger-toolspec-library) must satisfy, and
that every tool execution in [`bioledger`](../bioledger) itself relies on at
load time.

## Status

**Pre-alpha — not yet extracted.** The schema code currently still lives at
`bioledger/src/bioledger/toolspec/`. This repo exists to receive that code so
that `bioledger`, `bioledger-toolspec-library`, and any future consumer can
share a single source of truth without duplicating the schema or pulling in
the rest of the BioLedger application stack.

## Why a separate repo

- The current `bioledger.toolspec` subpackage has no `from bioledger.*`
  imports, so it can be lifted out cleanly.
- Asset repos (e.g. `bioledger-toolspec-library`) only need pydantic + pyyaml
  to validate specs — they should not have to install all of BioLedger's
  application dependencies (pydantic-ai, httpx, isatools, rich, etc.).
- A standalone package gives the schema its own version cadence, changelog,
  and PyPI identity.

## Migration plan (out of bioledger)

1. Move these files from `bioledger/src/bioledger/toolspec/` into
   `src/bioledger_toolspec_schema/` here:
   - `models.py`, `validate.py`, `load.py`, `__init__.py`
   - The richer reference doc currently at
     `bioledger/src/bioledger/toolspec/README.md` should move here too and
     become the canonical YAML-format reference.
   - **Open question:** `containers.py`, `sources.py`, `store.py` may belong
     here (schema-adjacent) or stay in `bioledger` (application-layer).
     Decide during extraction.
2. Add `pyproject.toml` with deps: `pydantic`, `pyyaml`. Target Python
   matches `bioledger`'s minimum.
3. In `bioledger`, replace `bioledger.toolspec` with re-export shims:
   ```python
   # bioledger/src/bioledger/toolspec/__init__.py
   from bioledger_toolspec_schema import *  # noqa: F401,F403
   ```
   so existing callsites keep working without churn.
4. Wire local development with editable installs:
   ```bash
   pip install -e ../bioledger-toolspec-schema
   ```
   from both `bioledger` and `bioledger-toolspec-library`.
5. Once stable, publish to PyPI as `bioledger-toolspec-schema` and have
   consumers switch from editable to versioned deps.

## Target public API

```python
from bioledger_toolspec_schema import (
    ToolSpec, ExecutionSpec, InterfaceSpec,
    ToolInput, ToolOutput, ToolParameter,
    SpecStatus, ParamType,
    validate_spec, validate_execution, validate_interface,
    Severity, ValidationIssue, ValidationResult,
    load_spec, dump_spec_yaml, save_spec,
    SPEC_VERSION,
)
```

Today's authoritative spec reference:
[`bioledger/src/bioledger/toolspec/README.md`](../bioledger/src/bioledger/toolspec/README.md).

## Consumers

| Consumer | Why it depends on this |
|---|---|
| `bioledger` | Loads & validates tool specs at runtime. |
| `bioledger-toolspec-library` | CI validates every committed `spec.yaml`. |

## Related repos

- **[`bioledger-toolspec-library`](../bioledger-toolspec-library)** — the
  curated collection of tool spec YAMLs (instances of this schema).
- **[`bioledger-isatab-schema`](../bioledger-isatab-schema)** — sibling
  schema package for ISA-Tab assets. Independent versioning.
- **[`bioledger`](../bioledger)** — the application that consumes both.
