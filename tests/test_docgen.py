from bioledger_toolspec_schema.docgen import DOCUMENTED_MODELS, generate_reference_markdown


def test_generate_reference_markdown_includes_all_documented_models():
    text = generate_reference_markdown()
    for model in DOCUMENTED_MODELS:
        assert f"`{model.__name__}`" in text


def test_generate_reference_markdown_includes_known_fields():
    text = generate_reference_markdown()
    for field in ["container", "command", "categories", "pattern", "options"]:
        assert f"`{field}`" in text


def test_generate_reference_markdown_has_no_empty_descriptions_for_key_fields():
    text = generate_reference_markdown()
    assert "Fully qualified Docker image URI" in text
    assert "Jinja2 command template" in text
