from bioledger_toolspec_schema.models import (
    ExecutionSpec,
    InputHint,
    InterfaceSpec,
    ParamType,
    SpecStatus,
    ToolInput,
    ToolOutput,
    ToolParameter,
    ToolSpec,
)
from bioledger_toolspec_schema.validate import (
    Severity,
    validate_execution,
    validate_interface,
    validate_spec,
)


def _spec(command: str) -> ExecutionSpec:
    return ExecutionSpec(
        name="t",
        command=command,
        container="img:1",
        executors=["docker"],
        inputs={"bam": ToolInput(type=ParamType.FILE, format="bam")},
        status=SpecStatus.VALID,
    )


def test_undeclared_input_with_whitespace_is_caught():
    """{{ inputs.undeclared }} (spaced) must fail validation."""
    result = validate_execution(
        _spec("sort -o out.bam {{ inputs.undeclared }}")
    )
    assert not result.is_valid
    assert any(
        i.severity == Severity.ERROR and "undeclared" in i.message
        for i in result.issues
    )


def test_undeclared_input_with_filter_is_caught():
    """{{ inputs.undeclared | stem }} (filter) must fail validation."""
    result = validate_execution(
        _spec("sort -o {{ inputs.undeclared | stem }}.bam {{ inputs.bam }}")
    )
    assert not result.is_valid
    assert any(
        i.severity == Severity.ERROR and "undeclared" in i.message
        for i in result.issues
    )


def test_declared_input_with_filter_and_suffix_passes():
    """Declared inputs used with filters / .path suffixes stay valid."""
    result = validate_execution(
        _spec("sort -o out.bam {{ inputs.bam | shquote }} {{ inputs.bam }}")
    )
    assert not any(
        "undeclared" in i.message for i in result.issues
    )


def test_undeclared_output_ref_is_caught():
    """{{ outputs.nonexistent.path }} must fail validation."""
    result = validate_execution(
        _spec("tool -o {{ outputs.nonexistent.path }} {{ inputs.bam }}")
    )
    assert any(
        i.severity == Severity.ERROR and "nonexistent" in i.message
        for i in result.issues
    )


def test_declared_output_and_dir_ref_pass():
    """Declared outputs and the outputs._dir builtin stay valid."""
    spec = ExecutionSpec(
        name="t",
        command="tool -o {{ outputs.real.path }} --dir {{ outputs._dir }}",
        container="img:1",
        executors=["docker"],
        inputs={"bam": ToolInput(type=ParamType.FILE, format="bam")},
        outputs={
            "real": ToolOutput(
                type=ParamType.FILE, format="txt", pattern="real.txt"
            )
        },
        status=SpecStatus.VALID,
    )
    result = validate_execution(spec)
    assert not any(
        i.severity == Severity.ERROR and "outputs" in i.field
        for i in result.issues
    )


# --- Required-field errors -------------------------------------------------


def _errors(result):
    return [i for i in result.issues if i.severity == Severity.ERROR]


def _warnings(result):
    return [i for i in result.issues if i.severity == Severity.WARNING]


def _infos(result):
    return [i for i in result.issues if i.severity == Severity.INFO]


def test_missing_name_is_error():
    result = validate_execution(
        ExecutionSpec(name="", command="x", container="img:1")
    )
    assert any(i.field == "name" for i in _errors(result))


def test_missing_command_is_error():
    result = validate_execution(
        ExecutionSpec(name="t", command="", container="img:1")
    )
    assert any(i.field == "command" for i in _errors(result))


# --- Executor rules ---------------------------------------------------------


def test_two_engine_executors_is_error():
    spec = _spec("x")
    spec.executors = ["nextflow", "snakemake"]
    spec.container = ""  # engine executors forbid container
    result = validate_execution(spec)
    assert any(
        "At most one engine executor" in i.message for i in _errors(result)
    )


def test_docker_plus_conda_plus_one_engine_is_allowed():
    spec = _spec("x")
    spec.executors = ["docker", "conda", "nextflow"]
    spec.container = ""
    spec.conda_deps = []
    # engine executor present → container/conda must be absent; docker
    # with neither container nor conda_deps errors independently.
    result = validate_execution(spec)
    assert any(
        "docker executor requires" in i.message for i in _errors(result)
    )


def test_container_and_conda_deps_are_mutually_exclusive():
    spec = _spec("x")
    spec.conda_deps = ["samtools=1.20"]
    result = validate_execution(spec)
    assert any(
        "mutually exclusive" in i.message for i in _errors(result)
    )


def test_docker_without_container_or_conda_is_error():
    spec = _spec("x")
    spec.container = ""
    result = validate_execution(spec)
    assert any(
        "docker executor requires either container or conda_deps"
        in i.message
        for i in _errors(result)
    )


def test_docker_with_conda_deps_alone_is_valid():
    spec = _spec("x")
    spec.container = ""
    spec.conda_deps = ["samtools=1.20"]
    result = validate_execution(spec)
    assert not _errors(result)


def test_conda_executor_requires_conda_deps():
    spec = _spec("x")
    spec.executors = ["conda"]
    spec.container = ""  # container+conda_deps also errors if both set
    result = validate_execution(spec)
    assert any(
        "conda executor requires conda_deps" in i.message
        for i in _errors(result)
    )


def test_engine_executor_with_container_is_error():
    spec = _spec("x")
    spec.executors = ["nextflow"]
    result = validate_execution(spec)  # container="img:1" from _spec
    assert any(
        "must not have" in i.message and "container" in i.message
        for i in _errors(result)
    )


def test_engine_executor_with_conda_deps_is_error():
    spec = _spec("x")
    spec.executors = ["snakemake"]
    spec.container = ""
    spec.conda_deps = ["bwa=0.7"]
    result = validate_execution(spec)
    assert any(
        "must not have" in i.message for i in _errors(result)
    )


def test_engine_executor_alone_is_clean():
    spec = _spec("x")
    spec.executors = ["galaxy"]
    spec.container = ""
    result = validate_execution(spec)
    assert not _errors(result)


# --- Command reference checks ------------------------------------------------


def test_undeclared_parameter_ref_is_caught():
    result = validate_execution(
        _spec("tool --threads {{ parameters.threads }} {{ inputs.bam }}")
    )
    assert any(
        i.field == "command.parameters.threads" for i in _errors(result)
    )


def test_declared_parameter_ref_passes():

    spec = _spec("tool -@ {{ parameters.threads }} {{ inputs.bam }}")
    spec.parameters = {"threads": ToolParameter(type="integer", default=4)}
    result = validate_execution(spec)
    assert not _errors(result)


def test_multiple_namespaces_checked_independently():
    result = validate_execution(
        _spec(
            "tool {{ inputs.bad_in }} --p {{ parameters.bad_p }} "
            "-o {{ outputs.bad_out }}"
        )
    )
    fields = {i.field for i in _errors(result)}
    assert "command.inputs.bad_in" in fields
    assert "command.parameters.bad_p" in fields
    assert "command.outputs.bad_out" in fields


# --- Parameter bounds ----------------------------------------------------------


def test_param_default_below_min_is_error():

    spec = _spec("x {{ inputs.bam }}")
    spec.parameters = {"n": ToolParameter(type="integer", default=1, min=2)}
    result = validate_execution(spec)
    assert any(
        "below minimum" in i.message and i.field == "parameters.n.default"
        for i in _errors(result)
    )


def test_param_default_above_max_is_error():

    spec = _spec("x {{ inputs.bam }}")
    spec.parameters = {
        "n": ToolParameter(type="float", default=99.5, max=10.0)
    }
    result = validate_execution(spec)
    assert any("exceeds maximum" in i.message for i in _errors(result))


def test_param_default_within_bounds_passes():

    spec = _spec("x {{ inputs.bam }}")
    spec.parameters = {
        "n": ToolParameter(type="integer", default=5, min=1, max=10)
    }
    result = validate_execution(spec)
    assert not _errors(result)


def test_param_no_default_skips_bounds_check():

    spec = _spec("x {{ inputs.bam }}")
    spec.parameters = {
        "n": ToolParameter(type="integer", required=True, min=1, max=10)
    }
    result = validate_execution(spec)
    assert not _errors(result)


# --- Warnings -----------------------------------------------------------------


def test_missing_version_warns():
    result = validate_execution(_spec("x {{ inputs.bam }}"))
    assert any(
        i.field == "version" and "recommended" in i.message
        for i in _warnings(result)
    )


def test_latest_version_warns():
    spec = _spec("x {{ inputs.bam }}")
    spec.version = "latest"
    result = validate_execution(spec)
    assert any(
        i.field == "version" and "specific version" in i.message
        for i in _warnings(result)
    )


def test_missing_description_warns():
    result = validate_execution(_spec("x {{ inputs.bam }}"))
    assert any(i.field == "description" for i in _warnings(result))


def test_no_outputs_warns():
    result = validate_execution(_spec("x {{ inputs.bam }}"))
    assert any(i.field == "outputs" for i in _warnings(result))


def test_latest_container_tag_warns():
    spec = _spec("x {{ inputs.bam }}")
    spec.container = "quay.io/biocontainers/fastqc:LATEST"
    result = validate_execution(spec)
    assert any(
        i.field == "container" and "latest" in i.message.lower()
        for i in _warnings(result)
    )


def test_input_format_any_warns():
    spec = _spec("x {{ inputs.bam }}")
    spec.inputs["bam"].format = "any"
    result = validate_execution(spec)
    assert any(
        i.field == "inputs.bam.format" for i in _warnings(result)
    )


def test_input_format_unknown_is_info():
    spec = _spec("x {{ inputs.bam }}")
    spec.inputs["bam"].format = "exoticfmt"
    result = validate_execution(spec)
    assert any(
        i.field == "inputs.bam.format" and "non-standard" in i.message
        for i in _infos(result)
    )
    # INFO must not affect validity in either mode
    assert result.is_valid


def test_output_format_unknown_is_info():
    spec = _spec("x {{ inputs.bam }}")
    spec.outputs = {"o": ToolOutput(format="weird")}
    result = validate_execution(spec)
    assert any(
        i.field == "outputs.o.format" for i in _infos(result)
    )


# --- Stem-preservation lint -----------------------------------------------------


def _collection_spec(pattern: str) -> ExecutionSpec:
    spec = _spec("x {{ inputs.bams }}")
    spec.inputs = {
        "bams": ToolInput(type=ParamType.FILE, format="bam", collection=True)
    }
    spec.outputs = {
        "out": ToolOutput(type=ParamType.FILE, format="bam", pattern=pattern)
    }
    return spec


def test_collection_input_with_static_output_pattern_warns():
    result = validate_execution(_collection_spec("sorted.bam"))
    assert any(
        "does not preserve" in i.message and i.field == "outputs.out.pattern"
        for i in _warnings(result)
    )


def test_collection_input_with_wildcard_pattern_passes():
    result = validate_execution(_collection_spec("*.sorted.bam"))
    assert not any("does not preserve" in i.message for i in result.issues)


def test_collection_input_with_stem_placeholder_passes():
    result = validate_execution(_collection_spec("{stem}.sorted.bam"))
    assert not any("does not preserve" in i.message for i in result.issues)


def test_collection_input_with_empty_pattern_warns():
    result = validate_execution(_collection_spec(""))
    assert any("does not preserve" in i.message for i in _warnings(result))


def test_non_collection_input_skips_stem_lint():
    spec = _spec("x {{ inputs.bam }}")
    spec.outputs = {"o": ToolOutput(format="bam", pattern="static.bam")}
    result = validate_execution(spec)
    assert not any("does not preserve" in i.message for i in result.issues)


# --- Status transitions and strict mode ------------------------------------------


def test_status_set_to_valid_on_clean_spec():
    spec = ExecutionSpec(
        name="t",
        version="1.0",
        description="d",
        command="tool {{ inputs.bam }}",
        container="img:1",
        executors=["docker"],
        inputs={"bam": ToolInput(format="bam")},
        outputs={"o": ToolOutput(format="txt", pattern="*.txt")},
    )
    validate_execution(spec)
    assert spec.status == SpecStatus.VALID


def test_status_set_to_draft_on_error():
    spec = ExecutionSpec(name="t", command="", container="img:1")
    validate_execution(spec)
    assert spec.status == SpecStatus.DRAFT


def test_warnings_do_not_affect_non_strict_status():
    spec = _spec("x {{ inputs.bam }}")  # missing version/description/outputs
    result = validate_execution(spec)
    assert result.is_valid
    assert not result.is_strict_valid
    assert spec.status == SpecStatus.VALID


def test_warnings_affect_strict_status():
    spec = _spec("x {{ inputs.bam }}")
    result = validate_execution(spec, strict=True)
    assert not result.is_strict_valid
    assert spec.status == SpecStatus.DRAFT


# --- validate_interface / validate_spec -------------------------------------------


def test_interface_hint_on_undeclared_field_warns():

    spec = _spec("x {{ inputs.bam }}")
    spec.version = "1"
    spec.description = "d"
    spec.outputs = {"o": ToolOutput(format="txt", pattern="*.txt")}
    iface = InterfaceSpec(hints={"ghost": InputHint(label="G")})
    result = validate_interface(iface, spec)
    assert any("ghost" in i.message for i in _warnings(result))


def test_validate_spec_flags_spec_version_mismatch():

    toolspec = ToolSpec(execution=_spec("x {{ inputs.bam }}"))
    toolspec.spec_version = "9.9"
    result = validate_spec(toolspec)
    assert any(
        i.field == "spec_version" and "migration" in i.message
        for i in _warnings(result)
    )


def test_validate_spec_merges_interface_issues():

    toolspec = ToolSpec(
        execution=_spec("x {{ inputs.bam }}"),
        interface=InterfaceSpec(hints={"ghost": InputHint()}),
    )
    result = validate_spec(toolspec)
    assert any("ghost" in i.message for i in result.issues)


def test_validate_spec_without_interface():

    toolspec = ToolSpec(
        execution=ExecutionSpec(
            name="t",
            version="1.0",
            description="d",
            command="tool {{ inputs.bam }}",
            container="img:1",
            inputs={"bam": ToolInput(format="bam")},
            outputs={"o": ToolOutput(format="txt", pattern="*.txt")},
        )
    )
    result = validate_spec(toolspec)
    assert result.is_valid
    assert result.is_strict_valid


# --- ValidationResult helpers ------------------------------------------------------


def test_summary_and_validity_properties():
    result = validate_execution(ExecutionSpec(name="", command=""))
    errors = _errors(result)
    assert len(errors) >= 2  # name + command (+ docker-without-container)
    summary = result.summary()
    assert "errors" in summary and "warnings" in summary
    assert not result.is_valid
    assert not result.is_strict_valid
