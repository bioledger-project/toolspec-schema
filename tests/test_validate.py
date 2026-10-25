from bioledger_toolspec_schema.models import (
    ExecutionSpec,
    ParamType,
    SpecStatus,
    ToolInput,
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
