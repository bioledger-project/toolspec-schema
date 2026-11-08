# bioledger-toolspec-schema

Pydantic models, YAML loader, and validator for the **BioLedger tool spec** format.

This package defines the contract that every tool spec YAML in
[`bioledger-toolspec-library`](../bioledger-toolspec-library) must satisfy, and
that every tool execution in [`bioledger`](../bioledger) itself relies on at
load time.

## Status

**Extracted and in use (v0.1.0).** The schema code lives here; `bioledger`'s
`bioledger.toolspec` subpackage is a set of thin re-export shims pointing at
this package, so all consumers share a single source of truth without pulling
in the rest of the BioLedger application stack.

## Why a separate repo

- Asset repos (e.g. `bioledger-toolspec-library`) only need pydantic + pyyaml +
  jinja2 + httpx to validate and render specs — they should not have to install
  all of BioLedger's application dependencies (pydantic-ai, isatools, rich, etc.).
- A standalone package gives the schema its own version cadence, changelog,
  and PyPI identity.

## Public API

```python
from bioledger_toolspec_schema import (
    ToolSpec, ExecutionSpec, ExecutionSpecDraft, InterfaceSpec,
    ToolInput, ToolOutput, ToolParameter,
    SpecStatus, ParamType, ExecutionMode, ExecutorType, FileFormat,
    validate_spec,
    Severity, ValidationIssue, ValidationResult,
    load_spec, dump_spec_yaml, save_spec,
    render_command, get_jinja_env,
    build_toolspec_index, write_toolspec_index,
)
```

`ExecutionSpecDraft` is the LLM-friendly authoring shape (used by ToolForge's
parse/fix agents) and converts to `ExecutionSpec` via `to_execution_spec()`.

Additional modules importable from the package (not re-exported at top level):
`validate_execution`, `validate_interface` (finer-grained validators),
`filters` (Jinja `basename`/`splitext`/`stem`/`shquote`), `store` (local
ToolStore), `containers` (BioContainers tag resolution), `sources` (tool
source abstraction), `index` (library index generation).

## Spec reference

The canonical YAML-format reference is [`docs/GUIDE.md`](docs/GUIDE.md).
Field-level details — command templates, the four Jinja filters, executor
rules (`docker`/`conda`/`nextflow`/`snakemake`/`galaxy`), `conda_deps`,
container requirements, validation rules — are all documented there.

## Consumers

| Consumer | Why it depends on this |
|---|---|
| `bioledger` | Loads & validates tool specs at runtime. |
| `bioledger-toolspec-library` | CI validates every committed `spec.yaml`. |

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v          # 178 tests, ~99% coverage
```

## Related repos

- **[`bioledger-toolspec-library`](../bioledger-toolspec-library)** — the
  curated collection of tool spec YAMLs (instances of this schema).
- **[`bioledger-isatab-schema`](../bioledger-isatab-schema)** — sibling
  schema package for ISA-Tab assets. Independent versioning.
- **[`bioledger`](../bioledger)** — the application that consumes both.
