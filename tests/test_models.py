import pytest
from pydantic import ValidationError

from bioledger_toolspec_schema.models import (
    SPEC_VERSION,
    Conditional,
    ExecutionMode,
    ExecutionSpec,
    ExecutionSpecDraft,
    FileFormat,
    InputHint,
    InterfaceSpec,
    ParamType,
    RepeatBlock,
    SpecStatus,
    ToolInput,
    ToolOutput,
    ToolParameter,
    ToolSpec,
    WidgetType,
    _fill_names_from_keys,
)


def _minimal_spec(**overrides) -> ExecutionSpec:
    kwargs = {"name": "t", "command": "run {{ inputs.f }}"}
    kwargs.update(overrides)
    return ExecutionSpec(**kwargs)


class TestFillNamesFromKeys:
    def test_missing_name_filled_from_key(self):
        spec = _minimal_spec(inputs={"reads": {"format": "fastq"}})
        assert spec.inputs["reads"].name == "reads"

    def test_explicit_name_preserved(self):
        spec = _minimal_spec(inputs={"k": {"name": "other", "format": "bam"}})
        assert spec.inputs["k"].name == "other"

    def test_applies_to_outputs_and_parameters(self):
        spec = _minimal_spec(
            inputs={"r": {"format": "fastq"}},
            outputs={"o": {"format": "txt"}},
            parameters={"p": {"type": "integer"}},
        )
        assert spec.outputs["o"].name == "o"
        assert spec.parameters["p"].name == "p"

    def test_non_dict_passthrough(self):
        assert _fill_names_from_keys(None) is None
        assert _fill_names_from_keys(["a", "b"]) == ["a", "b"]

    def test_non_dict_values_passthrough(self):
        out = _fill_names_from_keys({"k": "scalar"})
        assert out == {"k": "scalar"}


class TestExecutionSpecDefaults:
    def test_defaults(self):
        spec = _minimal_spec()
        assert spec.executors == ["docker"]
        assert spec.conda_deps == []
        assert spec.container == ""
        assert spec.version == ""
        assert spec.categories == []
        assert spec.status == SpecStatus.DRAFT
        assert spec.suggested_mode == ExecutionMode.BLOCKING
        assert spec.inputs == {}
        assert spec.outputs == {}
        assert spec.parameters == {}

    def test_name_and_command_required(self):
        with pytest.raises(ValidationError):
            ExecutionSpec()
        with pytest.raises(ValidationError):
            ExecutionSpec(name="t")

    def test_lookup_helpers(self):
        spec = _minimal_spec(
            inputs={"r": {"format": "fastq"}},
            outputs={"o": {"format": "txt"}},
            parameters={"p": {"type": "integer"}},
        )
        assert spec.get_input("r").format == "fastq"
        assert spec.get_input("nope") is None
        assert spec.get_output("o").format == "txt"
        assert spec.get_output("nope") is None
        assert spec.get_parameter("p").type == ParamType.INTEGER
        assert spec.get_parameter("nope") is None

    def test_invalid_executor_rejected(self):
        with pytest.raises(ValidationError):
            _minimal_spec(executors=["pbs"])

    def test_input_type_enum_enforced(self):
        with pytest.raises(ValidationError):
            ToolInput(type="blob")


class TestToolParameter:
    def test_numeric_bounds(self):
        p = ToolParameter(type="integer", default=4, min=1, max=32)
        assert p.min == 1 and p.max == 32

    def test_select_options(self):
        p = ToolParameter(type="select", options=["a", "b"], default="a")
        assert p.options == ["a", "b"]

    def test_file_type_in_parameters_is_allowed_by_model(self):
        # The model permits ParamType.FILE on ToolParameter — the convention
        # that files belong under inputs is a doc rule, not a model rule.
        p = ToolParameter(type="file")
        assert p.type == ParamType.FILE


class TestExecutionSpecDraft:
    def test_to_execution_spec_empty_executors_defaults_docker(self):
        draft = ExecutionSpecDraft(name="t", command="x")
        spec = draft.to_execution_spec()
        assert spec.executors == ["docker"]

    def test_to_execution_spec_converts_lists_to_dicts(self):
        draft = ExecutionSpecDraft(
            name="t",
            command="x",
            executors=["conda"],
            conda_deps=["samtools=1.20"],
            inputs=[ToolInput(name="r", format="fastq")],
            outputs=[ToolOutput(name="o", format="txt")],
            parameters=[ToolParameter(name="p", type="integer", default=2)],
            categories=["qc"],
            suggested_mode=ExecutionMode.ASYNC,
            homepage="https://example.org",
        )
        spec = draft.to_execution_spec()
        assert spec.executors == ["conda"]
        assert set(spec.inputs) == {"r"}
        assert set(spec.outputs) == {"o"}
        assert spec.parameters["p"].default == 2
        assert spec.suggested_mode == ExecutionMode.ASYNC
        assert spec.homepage == "https://example.org"

    def test_roundtrip(self):
        spec = _minimal_spec(
            version="1.0",
            description="d",
            container="img:1",
            inputs={"r": {"format": "fastq"}},
            outputs={"o": {"format": "txt"}},
            parameters={"p": {"type": "integer", "default": 1}},
            categories=["a"],
            license="MIT",
        )
        spec.status = SpecStatus.VALID
        draft = ExecutionSpecDraft.from_execution_spec(spec)
        back = draft.to_execution_spec()
        assert back.name == spec.name
        assert back.version == "1.0"
        assert back.inputs.keys() == spec.inputs.keys()
        assert back.outputs.keys() == spec.outputs.keys()
        assert back.parameters["p"].default == 1
        assert back.license == "MIT"
        assert back.status == SpecStatus.VALID

    def test_draft_schema_has_no_additional_properties(self):
        # The whole point of the Draft variant: Gemini-compatible JSON schema
        schema = ExecutionSpecDraft.model_json_schema()
        assert "$defs" in schema
        for prop in schema["properties"].values():
            if "additionalProperties" in prop:
                pytest.fail("Draft schema must not use additionalProperties")


class TestToolSpec:
    def test_defaults(self):
        spec = ToolSpec(execution=_minimal_spec())
        assert spec.spec_version == SPEC_VERSION
        assert spec.revision == "1"
        assert spec.interface is None

    def test_name_and_container_delegate_to_execution(self):
        spec = ToolSpec(execution=_minimal_spec(container="img:2"))
        assert spec.name == "t"
        assert spec.container == "img:2"

    def test_full_spec_with_interface(self):
        iface = InterfaceSpec(
            hints={"reads": InputHint(label="Reads", widget=WidgetType.FILE_UPLOAD)},
            conditionals=[Conditional(param="mode", branches={"adv": ["kmer"]})],
            repeats=[RepeatBlock(name="rep", fields=["p1"], min=1)],
            sections={"s1": "Advanced"},
        )
        spec = ToolSpec(execution=_minimal_spec(), interface=iface, revision="3")
        assert spec.interface.hints["reads"].label == "Reads"
        assert spec.interface.conditionals[0].param == "mode"
        assert spec.interface.repeats[0].min == 1
        assert spec.interface.sections["s1"] == "Advanced"
        assert spec.revision == "3"


class TestEnumsAndFormats:
    def test_known_formats_match_constants(self):
        for attr in ("FASTQ", "BAM", "VCF", "ANY"):
            assert getattr(FileFormat, attr) in FileFormat.KNOWN

    def test_execution_modes(self):
        assert ExecutionMode("blocking") is ExecutionMode.BLOCKING
        assert ExecutionMode("async") is ExecutionMode.ASYNC

    def test_spec_status_ordering_values(self):
        assert SpecStatus("draft") is SpecStatus.DRAFT
        assert SpecStatus("valid") is SpecStatus.VALID
        assert SpecStatus("enriched") is SpecStatus.ENRICHED
