from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

SPEC_VERSION = "0.1"


class ParamType(str, Enum):
    FILE = "file"
    DIRECTORY = "directory"
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    SELECT = "select"


class FileFormat:
    """Well-known format constants. NOT an enum — any string is valid.
    Validation can warn on unknown formats without blocking them."""

    FASTQ = "fastq"
    FASTA = "fasta"
    BAM = "bam"
    SAM = "sam"
    CRAM = "cram"
    VCF = "vcf"
    BCF = "bcf"
    BED = "bed"
    GFF = "gff"
    GTF = "gtf"
    BIGWIG = "bigwig"
    HTML = "html"
    TXT = "txt"
    CSV = "csv"
    TSV = "tsv"
    JSON = "json"
    PNG = "png"
    PDF = "pdf"
    H5AD = "h5ad"
    TABULAR = "tabular"
    ANY = "any"

    KNOWN: set[str] = {
        "fastq", "fasta", "bam", "sam", "cram", "vcf", "bcf", "bed",
        "gff", "gtf", "bigwig", "html", "txt", "csv", "tsv", "json",
        "png", "pdf", "h5ad", "tabular", "any",
    }


class ToolInput(BaseModel):
    """A typed input to a tool (file or directory)."""

    name: str = Field(
        default="",
        description="Identifier for this input (used as the dict key internally).",
    )
    type: ParamType = Field(
        default=ParamType.FILE,
        description="`file` or `directory`.",
    )
    format: str = Field(
        default="any",
        description=(
            "Free-form string, not an enum. `any` is accepted but triggers a "
            "validation warning because it makes tool chaining harder."
        ),
    )
    required: bool = Field(
        default=True,
        description=(
            "If false, BioLedger may omit this input from the command; the "
            "template must handle that (usually via Jinja conditionals)."
        ),
    )
    description: str = Field(
        default="", description="Shown to the LLM and in the UI."
    )


class ToolParameter(BaseModel):
    """A configurable parameter (not a file)."""

    name: str = Field(
        default="",
        description="Identifier for this parameter (used as the dict key internally).",
    )
    type: ParamType = Field(
        description=(
            "One of `string`, `integer`, `float`, `boolean`, `select`. "
            "`file`/`directory` belong under `inputs`, not `parameters`."
        )
    )
    default: str | int | float | bool | None = Field(
        default=None, description="Value used when the caller does not override."
    )
    required: bool = Field(
        default=False,
        description="If true and no default, the CLI/LLM must supply a value.",
    )
    description: str = Field(default="", description="Shown to the LLM and in the UI.")
    min: int | float | None = Field(
        default=None,
        description="For `integer`/`float`. The default value is validated against this.",
    )
    max: int | float | None = Field(
        default=None,
        description="For `integer`/`float`. The default value is validated against this.",
    )
    options: list[str] | None = Field(
        default=None, description="Required when `type: select`; the allowed choices."
    )


class ToolOutput(BaseModel):
    """A typed output from a tool."""

    name: str = Field(
        default="",
        description="Identifier for this output (used as the dict key internally).",
    )
    type: ParamType = Field(default=ParamType.FILE, description="`file` or `directory`.")
    format: str = Field(default="any", description="Free-form string, not an enum.")
    pattern: str = Field(
        default="",
        description=(
            'Glob used for documentation/chaining hints (e.g. "*.html"). BioLedger '
            "records every file produced in `/output`, so this is advisory only."
        ),
    )
    description: str = Field(default="", description="Shown to the LLM and in the UI.")


class SpecStatus(str, Enum):
    """Validation tier for progressive refinement."""

    DRAFT = "draft"  # LLM-generated, may be incomplete
    VALID = "valid"  # passes execution-layer validation
    ENRICHED = "enriched"  # has UI layer + tested


def _fill_names_from_keys(value: Any) -> Any:
    """Allow YAML/JSON authors to omit redundant ``name`` fields when the
    collection key already names the item. ``{reads: {format: fastq}}`` becomes
    equivalent to ``{reads: {name: reads, format: fastq}}``.
    """
    if not isinstance(value, dict):
        return value
    out: dict[str, Any] = {}
    for k, v in value.items():
        if isinstance(v, dict) and not v.get("name"):
            v = {**v, "name": k}
        out[k] = v
    return out


class ExecutionSpec(BaseModel):
    """Layer 1: the minimal, portable execution contract.

    Internal representation uses ``dict[str, T]`` keyed by name for O(1) lookup
    and tight contracts. For LLM-facing schema generation (which must avoid
    ``additionalProperties``), use :class:`ExecutionSpecDraft` and convert
    via :meth:`ExecutionSpecDraft.to_execution_spec`.
    """

    name: str = Field(
        description=(
            "Unique tool identifier. Used on the CLI (`bioledger tool show <name>`) "
            "and as the filename."
        )
    )
    version: str = Field(
        default="",
        description="Free-form version label. Does not need to match the container tag.",
    )
    description: str = Field(
        default="",
        description="One-sentence summary. Shown to the LLM when it picks tools.",
    )
    container: str = Field(
        description=(
            "Fully qualified Docker image URI "
            "(e.g. `quay.io/biocontainers/fastqc:0.12.1--hdfd78af_0`)."
        )
    )
    command: str = Field(description="Jinja2 command template. See the Guide for variables.")
    inputs: dict[str, ToolInput] = Field(
        default_factory=dict, description="Declared input files/directories, keyed by name."
    )
    outputs: dict[str, ToolOutput] = Field(
        default_factory=dict, description="Declared outputs, keyed by name."
    )
    parameters: dict[str, ToolParameter] = Field(
        default_factory=dict,
        description="Non-file parameters (threads, flags, options), keyed by name.",
    )
    categories: list[str] = Field(
        default_factory=list,
        description=(
            "Free-form tags used for grouping and LLM hints "
            "(e.g. `alignment`, `qc`, `variant_calling`)."
        ),
    )
    status: SpecStatus = Field(
        default=SpecStatus.DRAFT,
        description="Set automatically by `validate_spec`; do not hand-set.",
    )
    # Provenance / attribution (optional)
    homepage: str = Field(default="", description="Tool homepage or docs URL.")
    citation: str = Field(default="", description="How to cite (DOI / paper reference).")
    license: str = Field(
        default="", description='SPDX identifier, e.g. "MIT", "GPL-3.0-or-later".'
    )
    contact: str = Field(default="", description="Maintainer contact.")

    _v_inputs = field_validator("inputs", mode="before")(
        classmethod(lambda cls, v: _fill_names_from_keys(v))
    )
    _v_outputs = field_validator("outputs", mode="before")(
        classmethod(lambda cls, v: _fill_names_from_keys(v))
    )
    _v_parameters = field_validator("parameters", mode="before")(
        classmethod(lambda cls, v: _fill_names_from_keys(v))
    )

    def get_input(self, name: str) -> ToolInput | None:
        return self.inputs.get(name)

    def get_output(self, name: str) -> ToolOutput | None:
        return self.outputs.get(name)

    def get_parameter(self, name: str) -> ToolParameter | None:
        return self.parameters.get(name)


class ExecutionSpecDraft(BaseModel):
    """LLM-facing variant of ExecutionSpec using list-shaped collections.

    Google Gemini rejects JSON schemas containing ``additionalProperties``,
    which pydantic generates for ``dict[str, SomeModel]`` fields. Using
    ``list[SomeModel]`` produces an ``array`` schema instead, which Gemini
    accepts. Use :meth:`to_execution_spec` to convert to the internal model.
    """

    name: str
    version: str = ""
    description: str = ""
    container: str
    command: str
    inputs: list[ToolInput] = []
    outputs: list[ToolOutput] = []
    parameters: list[ToolParameter] = []
    categories: list[str] = []
    status: SpecStatus = SpecStatus.DRAFT
    # Provenance / attribution (optional)
    homepage: str = ""
    citation: str = ""
    license: str = ""
    contact: str = ""

    def to_execution_spec(self) -> ExecutionSpec:
        return ExecutionSpec(
            name=self.name,
            version=self.version,
            description=self.description,
            container=self.container,
            command=self.command,
            inputs={i.name: i for i in self.inputs},
            outputs={o.name: o for o in self.outputs},
            parameters={p.name: p for p in self.parameters},
            categories=list(self.categories),
            status=self.status,
            homepage=self.homepage,
            citation=self.citation,
            license=self.license,
            contact=self.contact,
        )

    @classmethod
    def from_execution_spec(cls, spec: ExecutionSpec) -> ExecutionSpecDraft:
        return cls(
            name=spec.name,
            version=spec.version,
            description=spec.description,
            container=spec.container,
            command=spec.command,
            inputs=list(spec.inputs.values()),
            outputs=list(spec.outputs.values()),
            parameters=list(spec.parameters.values()),
            categories=list(spec.categories),
            status=spec.status,
            homepage=spec.homepage,
            citation=spec.citation,
            license=spec.license,
            contact=spec.contact,
        )


# --- Layer 2: Interface Spec (optional, Galaxy-inspired) ---


class WidgetType(str, Enum):
    FILE_UPLOAD = "file"
    TEXT = "text"
    NUMBER = "number"
    SLIDER = "slider"
    SELECT = "select"
    CHECKBOX = "checkbox"
    TEXTAREA = "textarea"


class Conditional(BaseModel):
    """Show/hide fields based on a controlling parameter's value (Galaxy <conditional>).
    Example: param="mode", branches={"advanced": ["kmer_size", "quiet"]}"""

    param: str = Field(description="Which parameter controls this.")
    branches: dict[str, list[str]] = Field(
        default_factory=dict, description="Value -> list of field names to show."
    )


class InputHint(BaseModel):
    """UI enrichment for a single input or parameter."""

    label: str = Field(default="", description="Display label.")
    help: str = Field(default="", description="Help text shown alongside the field.")
    widget: WidgetType | None = Field(default=None, description="UI widget to render.")
    section: str = Field(default="", description="Group into a collapsible section by id.")
    advanced: bool = Field(default=False, description="Collapsed by default when true.")


class RepeatBlock(BaseModel):
    """Galaxy <repeat>-style: user can add N instances of a param group."""

    name: str = Field(description="Repeat block identifier.")
    title: str = Field(default="", description="Display title.")
    min: int = Field(default=0, description="Minimum number of instances.")
    max: int | None = Field(default=None, description="Maximum number of instances.")
    fields: list[str] = Field(
        default_factory=list, description="Param names included in each repeat instance."
    )


class InterfaceSpec(BaseModel):
    """Layer 2: optional UI hints. Completely decoupled from execution."""

    hints: dict[str, InputHint] = Field(
        default_factory=dict,
        description="Per-field UI metadata, keyed by input/parameter name.",
    )
    conditionals: list[Conditional] = Field(
        default_factory=list,
        description="Show/hide param groups based on a controlling param.",
    )
    repeats: list[RepeatBlock] = Field(
        default_factory=list, description="Allow the user to add N instances of a field group."
    )
    sections: dict[str, str] = Field(
        default_factory=dict, description="Map of section id -> display title."
    )


# --- Combined ToolSpec ---


class ToolSpec(BaseModel):
    """Complete BioLedger tool specification = Execution + optional Interface."""

    spec_version: str = Field(
        default=SPEC_VERSION, description="Schema version, used for migrations."
    )
    execution: ExecutionSpec = Field(description="The portable execution contract.")
    interface: InterfaceSpec | None = Field(
        default=None, description="Optional UI enrichment. Completely decoupled from execution."
    )

    @property
    def name(self) -> str:
        return self.execution.name

    @property
    def container(self) -> str:
        return self.execution.container
