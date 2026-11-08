import json

import pytest
import yaml

from bioledger_toolspec_schema.index import build_index, main, write_index


def _write_spec(specs_dir, family, tool, execution_extra=None, **top):
    spec_dir = specs_dir / family / tool
    spec_dir.mkdir(parents=True)
    execution = {
        "name": tool,
        "version": "1.0",
        "description": f"{tool} desc",
        "container": f"img/{tool}:1",
        "command": "x",
        "categories": ["qc"],
        "inputs": {"reads": {"format": "fastq"}},
        "outputs": {"report": {"format": "html"}},
    }
    execution.update(execution_extra or {})
    doc = {"spec_version": "0.1", "revision": "2", "execution": execution}
    doc.update(top)
    (spec_dir / "spec.yaml").write_text(yaml.dump(doc))
    return spec_dir


class TestBuildIndex:
    def test_single_spec_fields(self, tmp_path):
        _write_spec(tmp_path, "samtools", "samtools-sort")
        entries = build_index(tmp_path)
        assert len(entries) == 1
        e = entries[0]
        assert e["name"] == "samtools-sort"
        assert e["family"] == "samtools"
        assert e["version"] == "1.0"
        assert e["revision"] == "2"
        assert e["description"] == "samtools-sort desc"
        assert e["container"] == "img/samtools-sort:1"
        assert e["categories"] == ["qc"]
        assert e["inputs"] == ["reads"]
        assert e["outputs"] == ["report"]
        assert e["path"] == "samtools/samtools-sort"

    def test_multiple_specs_sorted_by_path(self, tmp_path):
        _write_spec(tmp_path, "bwa", "bwa-mem")
        _write_spec(tmp_path, "samtools", "samtools-sort")
        _write_spec(tmp_path, "gatk", "gatk-haplotypecaller")
        names = [e["name"] for e in build_index(tmp_path)]
        assert names == ["bwa-mem", "gatk-haplotypecaller", "samtools-sort"]

    def test_unparseable_yaml_is_skipped(self, tmp_path):
        _write_spec(tmp_path, "samtools", "samtools-sort")
        bad_dir = tmp_path / "bad" / "bad-tool"
        bad_dir.mkdir(parents=True)
        (bad_dir / "spec.yaml").write_text("{not: [valid yaml")
        entries = build_index(tmp_path)
        assert len(entries) == 1
        assert entries[0]["name"] == "samtools-sort"

    def test_missing_execution_keys_use_defaults(self, tmp_path):
        spec_dir = tmp_path / "fam" / "tooldir"
        spec_dir.mkdir(parents=True)
        (spec_dir / "spec.yaml").write_text(yaml.dump({"revision": "5"}))
        (e,) = build_index(tmp_path)
        assert e["name"] == "tooldir"  # falls back to dir name
        assert e["version"] == ""
        assert e["revision"] == "5"
        assert e["inputs"] == []
        assert e["outputs"] == []
        assert e["categories"] == []

    def test_shallow_spec_has_empty_family(self, tmp_path):
        # specs/<tool>/spec.yaml — only 2 parts, no family level
        spec_dir = tmp_path / "tooldir"
        spec_dir.mkdir()
        (spec_dir / "spec.yaml").write_text(
            yaml.dump({"execution": {"name": "x", "command": "y"}})
        )
        (e,) = build_index(tmp_path)
        assert e["family"] == ""
        assert e["path"] == "tooldir"

    def test_empty_dir_returns_empty(self, tmp_path):
        assert build_index(tmp_path) == []


class TestWriteIndex:
    def test_writes_valid_json(self, tmp_path):
        _write_spec(tmp_path / "specs", "samtools", "samtools-sort")
        out = tmp_path / "site" / "index.json"
        write_index(tmp_path / "specs", out)
        data = json.loads(out.read_text())
        assert isinstance(data, list)
        assert data[0]["name"] == "samtools-sort"

    def test_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "deep" / "nested" / "index.json"
        write_index(tmp_path, out)
        assert out.exists()


class TestMain:
    def test_no_args_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["prog"])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
        assert "Usage" in capsys.readouterr().out

    def test_nonexistent_dir_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["prog", "/no/such/dir"])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
        assert "not a directory" in capsys.readouterr().err

    def test_stdout_output(self, tmp_path, monkeypatch, capsys):
        _write_spec(tmp_path / "specs", "fam", "tool-a")
        monkeypatch.setattr("sys.argv", ["prog", str(tmp_path / "specs")])
        main()
        data = json.loads(capsys.readouterr().out)
        assert data[0]["name"] == "tool-a"

    def test_output_file(self, tmp_path, monkeypatch):
        _write_spec(tmp_path / "specs", "fam", "tool-a")
        out = tmp_path / "idx.json"
        monkeypatch.setattr(
            "sys.argv", ["prog", str(tmp_path / "specs"), str(out)]
        )
        main()
        assert json.loads(out.read_text())[0]["name"] == "tool-a"
