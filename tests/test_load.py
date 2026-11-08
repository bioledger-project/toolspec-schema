import pytest
import yaml

from bioledger_toolspec_schema.load import (
    _migrate,
    dump_spec_yaml,
    load_spec,
    save_spec,
)
from bioledger_toolspec_schema.models import (
    SPEC_VERSION,
    ExecutionSpec,
    ToolInput,
    ToolSpec,
)


def _toolspec() -> ToolSpec:
    return ToolSpec(
        execution=ExecutionSpec(
            name="sample_tool",
            version="1.0",
            description="d",
            container="img:1",
            command="run {{ inputs.f }}",
            inputs={"f": ToolInput(name="f", format="fastq")},
        )
    )


def test_save_and_load_roundtrip(tmp_path):
    spec = _toolspec()
    path = tmp_path / "nested" / "sample_tool.bioledger.yaml"
    save_spec(spec, path)  # creates parent dirs
    loaded = load_spec(path)
    assert loaded.name == "sample_tool"
    assert loaded.execution.container == "img:1"
    assert loaded.execution.inputs["f"].format == "fastq"


def test_dump_spec_yaml_is_parseable_and_stable():
    spec = _toolspec()
    text = dump_spec_yaml(spec)
    raw = yaml.safe_load(text)
    assert raw["spec_version"] == SPEC_VERSION
    assert raw["revision"] == "1"
    assert raw["execution"]["name"] == "sample_tool"
    assert raw["execution"]["inputs"]["f"]["format"] == "fastq"


def test_dump_then_validate_roundtrip(tmp_path):
    # Dumped YAML must re-validate into an equivalent model
    spec = _toolspec()
    path = tmp_path / "s.yaml"
    path.write_text(dump_spec_yaml(spec))
    loaded = load_spec(path)
    assert loaded.model_dump() == spec.model_dump()


def test_load_spec_fills_names_from_keys(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text(
        yaml.dump(
            {
                "spec_version": SPEC_VERSION,
                "execution": {
                    "name": "t",
                    "container": "img:1",
                    "command": "x {{ inputs.r }}",
                    "inputs": {"r": {"format": "fastq"}},  # no explicit name
                },
            }
        )
    )
    spec = load_spec(path)
    assert spec.execution.inputs["r"].name == "r"


def test_load_spec_unknown_version_raises(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text(
        yaml.dump(
            {
                "spec_version": "0.0",
                "execution": {"name": "t", "command": "x"},
            }
        )
    )
    with pytest.raises(ValueError, match="No migration path"):
        load_spec(path)


def test_migrate_raises_without_registered_migration():
    with pytest.raises(ValueError, match="No migration path"):
        _migrate({"spec_version": "2.0"}, from_version="2.0")


def test_load_spec_missing_spec_version_defaults(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text(
        yaml.dump({"execution": {"name": "t", "command": "x", "container": "i:1"}})
    )
    spec = load_spec(path)
    assert spec.spec_version == SPEC_VERSION


def test_load_spec_invalid_yaml_model_raises(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text("execution: {name: 123, command: []}")
    with pytest.raises(Exception):
        load_spec(path)
