from bioledger_toolspec_schema.models import (
    ExecutionSpec,
    ParamType,
    SpecStatus,
    ToolInput,
    ToolOutput,
)
from bioledger_toolspec_schema.validate import Severity, validate_execution


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
