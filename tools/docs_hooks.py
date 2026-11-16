"""Publish selected repository artifacts without duplicating their sources."""

import re
from pathlib import Path

from mkdocs.config.defaults import MkDocsConfig
from mkdocs.structure.files import File, Files


def browser_demos(gallery: str) -> tuple[str, str]:
    """Reuse three real gallery charts and its shared Plotly bundle."""
    head = gallery.split("</head>", 1)[0]
    library = head.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    panels = []
    tabs = []
    examples = (("indexed", "Indexed"), ("gaps", "Gaps"), ("seasonal", "Seasonal"))
    for index, (key, label) in enumerate(examples):
        article = re.search(rf'<article id="{key}"[^>]*>(.*?)</article>', gallery, re.S)
        if article is None:
            raise ValueError(f"Missing gallery example: {key}")
        content = article.group(1)
        pane = re.search(
            r'<section class="pane" aria-label="Plotly interactive chart">'
            r"(.*?)</section>",
            content,
            re.S,
        )
        description = re.search(r"<h2>.*?</p>", content, re.S)
        if pane is None or description is None:
            raise ValueError(f"Incomplete gallery example: {key}")
        hidden = " hidden" if index else ""
        selected = "false" if index else "true"
        tabs.append(
            f'<button type="button" data-example="{key}" '
            f'aria-pressed="{selected}">{label}</button>'
        )
        panels.append(
            f'<section data-panel="{key}"{hidden}>'
            + description.group(0)
            + pane.group(1)
            + "</section>"
        )
    html = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Interactive browser chart examples</title>
<script src="../assets/plotly-demo.js"></script>
<style>
*{box-sizing:border-box}body{margin:0;padding:14px;color:#171717;background:white;
font:14px/1.5 system-ui,sans-serif}nav{display:flex;flex-wrap:wrap;gap:8px}
button{font:inherit;border:1px solid #dbe1e8;border-radius:5px;background:white;
color:#1f77b4;padding:6px 13px;cursor:pointer}
button[aria-pressed=true]{color:white;background:#1f77b4;border-color:#1f77b4}
button:focus-visible{outline:2px solid #111;outline-offset:2px}
h2{font-size:21px;line-height:1.25;margin:18px 0 8px}p{margin:0 0 10px;color:#525962}
section{min-width:0}[hidden]{display:none!important}.chart{width:100%;min-width:0}
.pane-heading{display:flex;gap:8px;align-items:center;font-size:12px;color:#525962}
.pane-heading button{margin-left:auto;padding:3px 8px;font-size:12px}
</style></head><body><nav aria-label="Choose a chart example">"""
    html += "".join(tabs) + "</nav>" + "".join(panels)
    html += """<script>
document.querySelectorAll('button[data-example]').forEach(button => {
  button.addEventListener('click', () => {
    document.querySelectorAll('button[data-example]').forEach(tab => {
      tab.setAttribute('aria-pressed', String(tab === button));
    });
    document.querySelectorAll('[data-panel]').forEach(panel => {
      panel.hidden = panel.dataset.panel !== button.dataset.example;
    });
    Plotly.Plots.resize(document.querySelector(
      '[data-panel="' + button.dataset.example + '"] .js-plotly-plot'));
  });
});
document.querySelectorAll('button[data-chart]').forEach(button => {
  button.addEventListener('click', async () => {
    const chart = document.getElementById(button.dataset.chart);
    await Plotly.restyle(chart, {visible:true});
    await Plotly.relayout(chart, {'xaxis.range':JSON.parse(button.dataset.range),
      'yaxis.autorange':true});
  });
});
</script></body></html>"""
    return library, html


def on_files(files: Files, config: MkDocsConfig) -> Files:
    root = Path(__file__).resolve().parent.parent
    sources = {
        "changelog.md": "CHANGELOG.md",
        "license.md": "LICENSE",
        "validation.md": "docs/_source/browser-validation.md",
        "examples/browser-examples.html": "docs/_source/browser-examples.html",
        "assets/termseries-yahoo.png": "images/termseries-yahoo.png",
        "assets/termseries.env.example": "termseries.env.example",
    }
    for destination, source in sources.items():
        files.append(
            File.generated(config, destination, abs_src_path=str(root / source))
        )
    gallery = root / "docs/_source/browser-examples.html"
    library, demos = browser_demos(gallery.read_text())
    files.append(File.generated(config, "assets/plotly-demo.js", content=library))
    files.append(File.generated(config, "examples/browser-demos.html", content=demos))
    return files


def on_config(config: MkDocsConfig) -> MkDocsConfig:
    """Keep the public site origin in preview pages, metadata and sitemaps."""
    config.site_url = config.extra["canonical_site_url"]
    return config
