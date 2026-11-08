import httpx
import pytest
import yaml

from bioledger_toolspec_schema.models import (
    ExecutionSpec,
    ToolInput,
    ToolOutput,
    ToolParameter,
    ToolSpec,
)
from bioledger_toolspec_schema.store import (
    DEFAULT_RAW_URL_TEMPLATE,
    ToolStore,
)


def _toolspec(name="tool_a", categories=None, in_fmt="fastq", out_fmt="bam"):
    return ToolSpec(
        execution=ExecutionSpec(
            name=name,
            container="img:1",
            command="run {{ inputs.f }}",
            categories=categories or [],
            inputs={"f": ToolInput(format=in_fmt)},
            outputs={"o": ToolOutput(format=out_fmt)},
        )
    )


@pytest.fixture
def store(tmp_path):
    return ToolStore(tmp_path / "tools")


class TestBasics:
    def test_save_and_load(self, store):
        spec = _toolspec()
        path = store.save(spec)
        assert path.name == "tool_a.bioledger.yaml"
        loaded = store.load("tool_a")
        assert loaded.name == "tool_a"

    def test_load_missing_raises_keyerror(self, store):
        with pytest.raises(KeyError, match="tool_a"):
            store.load("tool_a")

    def test_has(self, store):
        assert not store.has("tool_a")
        store.save(_toolspec())
        assert store.has("tool_a")

    def test_list_tools(self, store):
        store.save(_toolspec("a"))
        store.save(_toolspec("b"))
        assert sorted(store.list_tools()) == ["a", "b"]

    def test_list_tools_ignores_non_spec_files(self, store):
        (store.tools_dir / "notes.txt").write_text("hi")
        (store.tools_dir / "x.yaml").write_text("name: not-a-spec")
        assert store.list_tools() == []

    def test_list_all(self, store):
        store.save(_toolspec("a"))
        store.save(_toolspec("b"))
        specs = store.list_all()
        assert {s.name for s in specs} == {"a", "b"}

    def test_default_tools_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        store = ToolStore()
        assert store.tools_dir == tmp_path / ".bioledger" / "tools"
        assert store.tools_dir.is_dir()


class TestCaching:
    def test_load_caches(self, store, monkeypatch):
        store.save(_toolspec())  # save() populates cache
        calls = []
        import bioledger_toolspec_schema.store as store_mod

        real = store_mod.load_spec
        monkeypatch.setattr(
            store_mod,
            "load_spec",
            lambda p: (calls.append(p), real(p))[1],
        )
        store.load("tool_a")
        store.load("tool_a")
        assert len(calls) == 0  # served from cache written by save()
        store.invalidate_cache()
        store.load("tool_a")
        store.load("tool_a")
        assert len(calls) == 1  # one disk read after invalidation

    def test_cache_reads_from_disk_once(self, store, monkeypatch):
        # Write file directly (bypassing save → cache empty)
        store.tools_dir.mkdir(exist_ok=True)
        from bioledger_toolspec_schema.load import save_spec

        save_spec(_toolspec(), store.tools_dir / "tool_a.bioledger.yaml")
        calls = []
        import bioledger_toolspec_schema.store as store_mod

        real = store_mod.load_spec
        monkeypatch.setattr(
            store_mod,
            "load_spec",
            lambda p: (calls.append(p), real(p))[1],
        )
        store.list_all()
        store.list_all()
        assert len(calls) == 1

    def test_save_invalidates_stale_entry(self, store):
        store.save(_toolspec())
        updated = _toolspec()
        updated.execution.description = "v2"
        store.save(updated)
        assert store.load("tool_a").execution.description == "v2"


class TestSearch:
    @pytest.fixture
    def populated(self, store):
        store.save(_toolspec("fastqc", categories=["qc"], out_fmt="html"))
        store.save(
            _toolspec("samtools_sort", categories=["alignment"], out_fmt="bam")
        )
        return store

    def test_by_name_substring(self, populated):
        assert [s.name for s in populated.search(name="fastq")] == ["fastqc"]

    def test_name_case_insensitive(self, populated):
        assert [s.name for s in populated.search(name="FASTQC")] == ["fastqc"]

    def test_by_category(self, populated):
        assert [s.name for s in populated.search(category="alignment")] == [
            "samtools_sort"
        ]

    def test_by_input_format(self, populated):
        assert {s.name for s in populated.search(input_format="fastq")} == {
            "fastqc",
            "samtools_sort",
        }

    def test_by_output_format(self, populated):
        assert [s.name for s in populated.search(output_format="html")] == [
            "fastqc"
        ]

    def test_no_match(self, populated):
        assert populated.search(name="nonexistent") == []

    def test_combined_filters(self, populated):
        assert populated.search(name="samtools", category="qc") == []
        assert [
            s.name
            for s in populated.search(name="samtools", category="alignment")
        ] == ["samtools_sort"]


class _FakeResponse:
    def __init__(self, text="", status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code}", request=None, response=None
            )


class TestImportFromLibrary:
    def test_success_imports_and_saves(self, store, monkeypatch):
        spec_yaml = yaml.dump(
            {
                "spec_version": "0.1",
                "execution": {
                    "name": "remote_tool",
                    "container": "img:1",
                    "command": "x",
                },
            }
        )
        monkeypatch.setattr(
            "bioledger_toolspec_schema.store.httpx.get",
            lambda url, **kw: _FakeResponse(spec_yaml),
        )
        spec = store.import_from_library("fam/remote_tool")
        assert spec.name == "remote_tool"
        assert store.has("remote_tool")

    def test_url_template_uses_ref_and_path(self, store, monkeypatch):
        seen = {}

        def fake_get(url, **kw):
            seen["url"] = url
            return _FakeResponse(yaml.dump({
                "execution": {"name": "t", "command": "x"}
            }))

        monkeypatch.setattr(
            "bioledger_toolspec_schema.store.httpx.get", fake_get
        )
        store.import_from_library("a/b", ref="v1.2")
        assert seen["url"] == DEFAULT_RAW_URL_TEMPLATE.format(
            ref="v1.2", path="a/b"
        )

    def test_http_error_raises_valueerror(self, store, monkeypatch):
        monkeypatch.setattr(
            "bioledger_toolspec_schema.store.httpx.get",
            lambda url, **kw: _FakeResponse("nope", status=404),
        )
        with pytest.raises(ValueError, match="Failed to fetch"):
            store.import_from_library("fam/missing")

    def test_network_error_raises_valueerror(self, store, monkeypatch):
        def boom(url, **kw):
            raise httpx.ConnectError("dns fail")

        monkeypatch.setattr(
            "bioledger_toolspec_schema.store.httpx.get", boom
        )
        with pytest.raises(ValueError, match="Failed to fetch"):
            store.import_from_library("fam/x")

    def test_malformed_yaml_raises_valueerror(self, store, monkeypatch):
        monkeypatch.setattr(
            "bioledger_toolspec_schema.store.httpx.get",
            lambda url, **kw: _FakeResponse("{bad: [yaml"),
        )
        with pytest.raises(ValueError, match="Failed to parse"):
            store.import_from_library("fam/x")

    def test_schema_invalid_spec_raises_valueerror(self, store, monkeypatch):
        monkeypatch.setattr(
            "bioledger_toolspec_schema.store.httpx.get",
            lambda url, **kw: _FakeResponse(
                yaml.dump({"execution": {"command": 123}})
            ),
        )
        with pytest.raises(ValueError, match="Failed to parse"):
            store.import_from_library("fam/x")
