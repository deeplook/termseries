"""Publish selected repository artifacts without duplicating their sources."""

from pathlib import Path

from mkdocs.config.defaults import MkDocsConfig
from mkdocs.structure.files import File, Files


def on_files(files: Files, config: MkDocsConfig) -> Files:
    root = Path(__file__).resolve().parent.parent
    sources = {
        "changelog.md": "CHANGELOG.md",
        "license.md": "LICENSE",
        "validation.md": "work/browser-validation.md",
        "examples/browser-examples.html": "work/browser-examples.html",
        "assets/termseries-yahoo.png": "images/termseries-yahoo.png",
        "assets/termseries.env.example": "termseries.env.example",
    }
    for destination, source in sources.items():
        files.append(
            File.generated(config, destination, abs_src_path=str(root / source))
        )
    return files
