from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, field_validator

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

    name: str = ""  # identifier for this input (used as dict key internally)
    type: ParamType = ParamType.FILE
    format: str = "any"  # free-form string, not enum
    required: bool = True
    description: str = ""


class ToolParameter(BaseModel):
    """A configurable parameter (not a file)."""

    name: str = ""  # identifier for this parameter (used as dict key internally)
    type: ParamType
    default: str | int | float | bool | None = None
    required: bool = False
    description: str = ""
    min: int | float | None = None
    max: int | float | None = None
    options: list[str] | None = None  # for SELECT type


class ToolOutput(BaseModel):
    """A typed output from a tool."""

    name: str = ""  # identifier for this output (used as dict key internally)
    type: ParamType = ParamType.FILE
    format: str = "any"  # free-form string, not enum
    pattern: str = ""  # glob for discovery, e.g. "*.html"
    description: str = ""


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

    name: str
    version: str = ""
    description: str = ""
    container: str  # required: Docker image URI
    command: str  # Jinja2-style template
    inputs: dict[str, ToolInput] = {}
    outputs: dict[str, ToolOutput] = {}
    parameters: dict[str, ToolParameter] = {}
    categories: list[str] = []
    status: SpecStatus = SpecStatus.DRAFT
    # Provenance / attribution (optional)
    homepage: str = ""  # tool homepage or docs URL
    citation: str = ""  # how to cite (DOI / paper reference)
    license: str = ""  # SPDX identifier, e.g. "MIT", "GPL-3.0-or-later"
    contact: str = ""  # maintainer contact

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

    param: str  # which parameter controls this
    branches: dict[str, list[str]] = {}  # value → list of field names to show


class InputHint(BaseModel):
    """UI enrichment for a single input or parameter."""

    label: str = ""
    help: str = ""
    widget: WidgetType | None = None
    section: str = ""  # group into collapsible sections
    advanced: bool = False  # collapsed by default


class RepeatBlock(BaseModel):
    """Galaxy <repeat>-style: user can add N instances of a param group."""

    name: str
    title: str = ""
    min: int = 0
    max: int | None = None
    fields: list[str] = []  # param names in each repeat instance


class InterfaceSpec(BaseModel):
    """Layer 2: optional UI hints. Completely decoupled from execution."""

    hints: dict[str, InputHint] = {}  # keyed by input/param name
    conditionals: list[Conditional] = []
    repeats: list[RepeatBlock] = []
    sections: dict[str, str] = {}  # section_id → display title


# --- Combined ToolSpec ---


class ToolSpec(BaseModel):
    """Complete BioLedger tool specification = Execution + optional Interface."""

    spec_version: str = SPEC_VERSION  # for schema migration
    execution: ExecutionSpec
    interface: InterfaceSpec | None = None

    @property
    def name(self) -> str:
        return self.execution.name

    @property
    def container(self) -> str:
        return self.execution.container
