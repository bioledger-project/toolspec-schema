import pytest

from bioledger_toolspec_schema.models import (
    ExecutionSpec,
    ToolSpec,
)
from bioledger_toolspec_schema.load import save_spec
from bioledger_toolspec_schema.sources import LocalDirSource, ToolSource


def _spec(name):
    return ToolSpec(
        execution=ExecutionSpec(name=name, container="img:1", command="x")
    )


@pytest.fixture
def source(tmp_path):
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    save_spec(_spec("alpha"), tools_dir / "alpha.bioledger.yaml")
    save_spec(_spec("beta"), tools_dir / "beta.bioledger.yaml")
    return LocalDirSource(tools_dir)


def test_is_tool_source(source):
    assert isinstance(source, ToolSource)


def test_list_tools(source):
    assert sorted(source.list_tools()) == ["alpha", "beta"]


def test_load(source):
    spec = source.load("alpha")
    assert spec.name == "alpha"


def test_load_missing_raises_keyerror(source):
    with pytest.raises(KeyError, match="ghost"):
        source.load("ghost")


def test_has(source):
    assert source.has("alpha")
    assert not source.has("ghost")


def test_toolsource_is_abstract():
    with pytest.raises(TypeError):
        ToolSource()
