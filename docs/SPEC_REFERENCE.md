# BioLedger ToolSpec Reference (moved)

This document has been split in two, published on GitHub Pages at <https://bioledger-project.github.io/toolspec-schema/>:

- **[Guide](GUIDE.md)** (rendered as the site's landing page) — concepts, command templates, container execution model, validation, migrations, FAQ.
- **API Reference** (rendered at `/reference.html`) — field-by-field tables, auto-generated from `models.py` via `bioledger_toolspec_schema.docgen` so they can never drift from the code. Run `python -m bioledger_toolspec_schema.docgen` to view it locally.
