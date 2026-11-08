import shlex

import pytest

from bioledger_toolspec_schema.filters import (
    _basename,
    _splitext,
    _stem,
    get_jinja_env,
    render_command,
)


class TestBasename:
    def test_strips_directory(self):
        assert _basename("/data/reads/sample1.fastq") == "sample1.fastq"

    def test_bare_filename(self):
        assert _basename("sample1.fastq") == "sample1.fastq"

    def test_trailing_slash_returns_empty(self):
        assert _basename("/data/dir/") == ""

    def test_jinja_usage(self):
        out = render_command("cp {{ inputs.f | basename }} out/", inputs={"f": "/a/b.txt"})
        assert out == "cp b.txt out/"


class TestSplitext:
    def test_returns_root_and_ext(self):
        assert _splitext("reads.fastq.gz") == ["reads.fastq", ".gz"]

    def test_no_extension(self):
        assert _splitext("Makefile") == ["Makefile", ""]

    def test_includes_directory_in_root(self):
        root, ext = _splitext("/data/x.bam")
        assert root == "/data/x"
        assert ext == ".bam"


class TestStem:
    def test_strips_last_extension(self):
        assert _stem("reads.fastq.gz") == "reads.fastq"

    def test_strips_directory(self):
        assert _stem("/data/reads.fastq") == "reads"

    def test_all_strips_every_extension(self):
        assert _stem("reference.fna.gz", all=True) == "reference"
        assert _stem("a.b.c.d", all=True) == "a"

    def test_all_false_default(self):
        assert _stem("a.b.c") == "a.b"

    def test_no_extension(self):
        assert _stem("Makefile") == "Makefile"
        assert _stem("Makefile", all=True) == "Makefile"

    def test_jinja_usage_with_arg(self):
        out = render_command(
            "gunzip -c {{ inputs.f | stem(true) }}",
            inputs={"f": "ref.fna.gz"},
        )
        assert out == "gunzip -c ref"


class TestShquote:
    def test_plain_value_unchanged(self):
        out = render_command("cat {{ inputs.f | shquote }}", inputs={"f": "reads.fq"})
        assert out == "cat reads.fq"

    def test_spaces_are_quoted(self):
        name = "my file.txt"
        out = render_command("cat {{ inputs.f | shquote }}", inputs={"f": name})
        assert out == f"cat {shlex.quote(name)}"

    def test_shell_metachars_are_escaped(self):
        value = "a;rm -rf /"
        out = render_command("cat {{ inputs.f | shquote }}", inputs={"f": value})
        # shlex.quote wraps in single quotes, neutralising the metachars
        assert out == f"cat {shlex.quote(value)}"
        assert out == "cat 'a;rm -rf /'"


class TestRenderCommand:
    def test_renders_namespaces(self):
        out = render_command(
            "sort -@ {{ parameters.threads }} -o {{ outputs._dir }}/sorted.bam {{ inputs.bam }}",
            inputs={"bam": "in.bam"},
            parameters={"threads": 8},
            outputs={"_dir": "/out"},
        )
        assert out == "sort -@ 8 -o /out/sorted.bam in.bam"

    def test_undefined_variable_renders_empty(self):
        # Jinja default: undefined names render as empty string, not an error
        out = render_command("echo {{ inputs.missing }}", inputs={})
        assert out == "echo "


class TestGetJinjaEnv:
    def test_returns_environment_with_all_filters(self):
        env = get_jinja_env()
        for f in ("basename", "splitext", "stem", "shquote"):
            assert f in env.filters

    def test_returns_shared_instance(self):
        # Filters are registered on a module-level env; callers share it
        assert get_jinja_env() is get_jinja_env()


@pytest.mark.parametrize(
    "template,expected",
    [
        ("{{ 'a/b/c.txt' | basename }}", "c.txt"),
        ("{{ 'x/y.bam' | stem }}", "y"),
        ("{{ 'x/y.bam' | splitext }}", "['x/y', '.bam']"),
    ],
)
def test_filters_via_template_literal(template, expected):
    assert render_command(template) == expected
