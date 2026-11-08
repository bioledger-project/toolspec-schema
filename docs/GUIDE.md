# BioLedger ToolSpec Guide

A **ToolSpec** is a YAML file that describes how to run a bioinformatics tool inside BioLedger. This guide explains the concepts and conventions; for the exact field list on every model, see the [API Reference](reference.html) (auto-generated from `models.py`, so it's always current).

If you just want to see a working example, look at
[`examples/hello_bioledger/line_counter.bioledger.yaml`](https://github.com/bioledger-project/bioledger/blob/master/examples/hello_bioledger/line_counter.bioledger.yaml) in the main `bioledger` repo.

---

## Table of Contents

1. [File conventions](#file-conventions)
2. [Top-level structure](#top-level-structure)
3. [Command templates](#command-templates)
4. [Container execution model](#container-execution-model)
5. [Well-known formats](#well-known-formats)
6. [Validation](#validation)
7. [Spec versioning & migrations](#spec-versioning--migrations)
8. [Complete example](#complete-example)
9. [FAQ / gotchas](#faq--gotchas)

---

## File conventions

- Extension: `.bioledger.yaml` (recommended; not enforced).
- Storage: `~/.bioledger/tools/<name>.bioledger.yaml` after `bioledger tool import`.
- Encoding: UTF-8, standard YAML 1.2.
- The source of truth for the schema is [`models.py`](https://github.com/bioledger-project/toolspec-schema/blob/main/src/bioledger_toolspec_schema/models.py). Anything here that disagrees with the Pydantic models is a doc bug — the models win, and the [API Reference](reference.html) is generated directly from them.

---

## Top-level structure

```yaml
spec_version: "0.1"        # schema format version — changed by schema maintainers only
revision: "1"              # spec wrapper revision — bump when you edit the command/inputs/outputs
execution:                 # ExecutionSpec, required
  ...
interface:                 # InterfaceSpec, optional
  ...
```

`execution` is the minimum viable tool — everything BioLedger needs to run it in a container and record the result. `interface` is pure UI metadata, ignored by the executor. See the [API Reference](reference.html) for every field on `ExecutionSpec`, `ToolInput`, `ToolOutput`, `ToolParameter`, and `InterfaceSpec`.

**Three "version-like" fields:**
- `spec_version` — the YAML schema format. Only changes when the parser/validator needs a migration (e.g. new required fields).
- `revision` — the spec wrapper definition. Bump whenever you fix the command template, add an input, change an output pattern, etc. Independent of the upstream tool version.
- `execution.version` — the **upstream tool's version** (samtools, GATK, etc.). Never change this unless the Docker image upgrades to a new tool release.

---

## Command templates

Commands are rendered with [Jinja2](https://jinja.palletsprojects.com/). At render time, three namespaces are available:

| Template variable | Source | Rendered value |
|-------------------|--------|----------------|
| `{{inputs.<name>}}` | Declared input file | Absolute path **inside the container**: `/input/<name>/<filename>` |
| `{{parameters.<name>}}` | Declared parameter (or user override) | The parameter value, coerced by Jinja's default stringifier |
| `{{outputs._dir}}` | Always | `/output` — the directory in the container where output files must be written |
| `{{outputs.<name>}}` (or `{{outputs.<name>.path}}`) | Declared output | `/output/<pattern>` — the path that output is expected at |

Rules:

1. **Every `{{inputs.X}}`, `{{parameters.X}}`, and `{{outputs.X}}` must match a declared field**, or validation emits an ERROR. References with filters (`{{inputs.x | stem}}`) and attribute suffixes (`{{outputs.x.path}}`) are recognized too.
2. Write all outputs under `{{outputs._dir}}`; BioLedger discovers every file in `/output` after the run and records them. `{{outputs.X}}` refs are for tools that must name an output path explicitly (e.g. `-o {{outputs.report}}`).
3. Multi-line commands should use YAML block scalars (`>-` or `|`) so quoting stays readable.
4. The rendered string is passed through `shlex.split`; if that fails (complex shell syntax), it falls back to `sh -c "<command>"`. If you rely on pipes, redirects, or `$VAR` expansion, `sh -c` will be used automatically.

At runtime, an input is mounted read-only at `/input/<name>/` inside the container. After the container exits, every file in `/output` is hashed (SHA-256), sized, and added to the `LedgerEntry` as a `FileRef` with `role="output"`. There is no way to "hide" an output file short of not writing it.

### Jinja filters

BioLedger registers four custom Jinja2 filters for use inside command templates:

| Filter | Usage | Example | Result |
|--------|-------|---------|--------|
| `stem` | `{{ path | stem }}` | `"/input/ref.fna.gz" \| stem` | `ref.fna` |
| `stem` (all) | `{{ path | stem(true) }}` | `"/input/ref.fna.gz" \| stem(true)` | `ref` |
| `basename` | `{{ path | basename }}` | `"/input/ref.fna.gz" \| basename` | `ref.fna.gz` |
| `splitext` | `{{ path | splitext }}` | `"/input/ref.fna.gz" \| splitext` | `\["/input/ref.fna", ".gz"\]` |
| `shquote` | `{{ path | shquote }}` | `"/input/my file.bam" \| shquote` | `'my file.bam'` |

The first three are useful when a tool requires an output filename derived
from an input filename (e.g. `samtools dict -o {{outputs._dir}}/{{inputs.ref_fasta|stem(true)}}.dict {{inputs.ref_fasta}}`).

`shquote` applies `shlex.quote` — use it at CLI-argument sites where a value
might contain spaces or shell metacharacters (e.g.
`--input {{inputs.reads | shquote}}`). Do **not** pre-quote mapping values
yourself: quoting is positional — a literal quote in the value would corrupt
`| stem` / `| basename` derivations and YAML parsing.

In Python you can reuse the same rendering environment via:

```python
from bioledger_toolspec_schema import render_command, get_jinja_env

# Render a command with the canonical filters
rendered = render_command(
    "samtools dict -o {{outputs._dir}}/{{inputs.ref|stem(true)}}.dict {{inputs.ref}}",
    inputs={"ref": "/input/ref/ref.fna.gz"},
    outputs={"_dir": "/output"},
)

# Or get the Environment directly
env = get_jinja_env()
```

---

## Execution model

`execution.executors` declares how the tool may run (`['docker']` by
default). `docker` and `conda` may coexist, and either may coexist with at
most **one** engine executor (`nextflow`, `snakemake`, `galaxy`) — command
syntax is engine-specific, so two engines in one spec is an ERROR.

The environment is provided by exactly one of:

- **`container`** — a fully qualified Docker image URI. Required when
  `executors` includes `docker` and no `conda_deps` are given. Mutually
  exclusive with `conda_deps`, and disallowed for engine-only specs
  (the engine manages its own environment).
- **`conda_deps`** — conda package specs (e.g. `['samtools=1.17']`). With
  `executors: [conda]` the env is created natively; with
  `executors: [docker]` the image is auto-derived via a mulled-hash /
  BioContainers lookup.
- **neither** — for engine executors only (`nextflow`/`snakemake`/`galaxy`),
  which provide their own environment machinery.

`execution.suggested_mode` is an optional dispatch hint: set
`suggested_mode: async` for long-running tools so callers default to
submit-and-poll instead of blocking. Per-run overrides are always allowed.

`execution.inputs.<name>.collection: true` marks an input that accepts a
collection (glob / file list) rather than a single file — used for native
scatter/fan-out. Validation lints collection inputs whose command template
drops the file stem (stem preservation keeps chained runs traceable).

Optional provenance/attribution fields on `execution`: `homepage`,
`citation`, `license`, `contact`.

### Container execution model

When the tool runs in a container (`docker` executor):

```
host filesystem                  container filesystem
---------------                  --------------------
<input_file_1_dir>/   ─read-only─►   /input/<name1>/
<input_file_2_dir>/   ─read-only─►   /input/<name2>/
<output_dir>/          ─read/write─►   /output/
```

- Each input file's **parent directory** is bind-mounted, not the individual file. If you pass a file, the whole directory is visible inside the container. Do not depend on it being empty.
- The container is invoked with `docker run --rm`.
- Working directory inside the container is whatever the image sets as `WORKDIR`. Always use absolute paths (`/input/...`, `/output/...`) in your command.
- Exit code is captured. Non-zero sets `exit_code` on the ledger entry but does not stop the file-discovery sweep — partial outputs are still recorded.

---

## Well-known formats

These strings are recognized without warnings:

```
fastq  fasta  bam    sam    cram   vcf    bcf    bed
gff    gtf    bigwig html   txt    csv    tsv    json
png    pdf    h5ad   tabular  any
```

Other strings are accepted (INFO-level notice only) — use them when no standard applies, e.g. `"parquet"` or `"mzml"`.

---

## Validation

Run locally:

```bash
bioledger tool validate path/to/spec.bioledger.yaml
bioledger tool validate path/to/spec.bioledger.yaml --strict   # warnings become failures
```

Severities:

| Severity | When it fires (examples) | Effect |
|----------|--------------------------|--------|
| **ERROR** | Missing `name`/`command`; `docker` executor without `container` or `conda_deps`; `container` and `conda_deps` both set; two engine executors; `container`/`conda_deps` on an engine-only spec; command references undeclared `inputs.X`/`outputs.X`/`parameters.X`; `default` outside `[min, max]`; interface hints pointing at undeclared fields. | Always blocks; spec is marked `draft`. |
| **WARNING** | Missing `version`/`description`; no outputs declared; input has `format: any`; `spec_version` differs from current; collection input whose command drops the file stem. | Blocks only under `--strict`. |
| **INFO** | Non-well-known format string. | Never blocks. |

If validation produces no ERRORs — and no WARNINGs under `--strict` — `validate_spec` flips `status` to `valid`; otherwise `draft`.

---

## Spec versioning & migrations

Current schema version: **`0.1`** (see `SPEC_VERSION` in `models.py`).

- `load_spec()` reads `spec_version` and applies registered migrations in `load.py::_migrate`.
- If no migration path exists, loading raises `ValueError`. Add migrations as pure `dict → dict` functions keyed by source version.
- Keep `spec_version` quoted (`"0.1"`) — otherwise YAML parses it as a float and versions like `"0.10"` collide with `0.1`.

---

## Complete example

```yaml
spec_version: "0.1"

execution:
  name: fastqc
  version: "0.12.1"
  description: "Quality control for high-throughput sequence data"
  container: "quay.io/biocontainers/fastqc:0.12.1--hdfd78af_0"

  command: >-
    fastqc
    --outdir {{outputs._dir}}
    --threads {{parameters.threads}}
    {% if parameters.nogroup %}--nogroup{% endif %}
    {{inputs.reads}}

  inputs:
    reads:
      type: file
      format: fastq
      required: true
      description: "Input FASTQ (optionally gzipped)"

  outputs:
    html_report:
      type: file
      format: html
      pattern: "*_fastqc.html"
      description: "Per-file HTML report"
    zip_report:
      type: file
      format: any
      pattern: "*_fastqc.zip"
      description: "Zipped raw QC data"

  parameters:
    threads:
      type: integer
      default: 1
      min: 1
      max: 32
      description: "Worker threads"
    nogroup:
      type: boolean
      default: false
      description: "Disable base grouping for long reads"

  categories: [qc, preprocessing]

interface:
  hints:
    threads:
      label: "CPU threads"
      widget: slider
      section: performance
    nogroup:
      label: "Disable base grouping"
      widget: checkbox
      advanced: true
  sections:
    performance: "Performance"
```

---

## FAQ / gotchas

**Q: Can I depend on a shell feature like pipes or `$HOME`?**
Yes — `shlex.split` will fail on them, and BioLedger falls back to `sh -c "<rendered>"`. But remember: the container's shell is whatever the image provides (often `sh`, not `bash`).

**Q: How do I make an output optional?**
You can't declare it optional. Either always produce the file (even if empty) or use a Jinja conditional in the command so the tool skips generation. Any file found in `/output` will be recorded.

**Q: My tool writes to a hard-coded path, not `/output`.**
Use a post-step in the command: `&& mv /some/hardcoded/report.html {{outputs._dir}}/`.

**Q: How do I pass multiple files to one input?**
Set `collection: true` on the input — it accepts a glob/manifest/file list and is used for native scatter. Alternatively declare a `directory`-type input and have the tool glob inside it, or use an `interface.repeats` block to let the UI collect multiple values (the executor will still receive one file per declared input).

**Q: Where does `tool_spec_snapshot` come from?**
At run time, `run_tool` serializes `spec.execution` into the `LedgerEntry`. Even if you later edit the spec, historical runs keep the exact inputs/outputs/command used at the time.

**Q: Can I reuse a tool spec from Galaxy or Nextflow?**
Yes — `bioledger tool import` accepts `.xml` (Galaxy) and `.nf` (Nextflow) in addition to `.bioledger.yaml`. See [`examples/galaxy_tool_import/`](https://github.com/bioledger-project/bioledger/tree/master/examples/galaxy_tool_import).
