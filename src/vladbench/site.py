"""The GitHub Pages site: one static folder with the results page, its embed mode, the take-the-benchmark page,
the data files, the per-task answer files, the figures, and the record.

The embed list is documented where it is defined: EMBED_TABS in web/results.js.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil

from . import paths
from .sitedata import FILES

FULL_DATA = re.compile(r'<script src="task-review-data\.js(\?v=\d+)?" defer></script>')
SLIM_DATA = '<script src="task-review-tasks.js" defer></script>'
FIGURES = ("cost-vs-score.png", "cost-vs-score-hero.png")


def embed_html(results_html: str) -> str:
    """results.html with the slim task file instead of the 16 MB question file."""
    slim, count = FULL_DATA.subn(SLIM_DATA, results_html)
    if count != 1:
        raise ValueError("results.html no longer loads task-review-data.js the way embed_html expects")
    return slim


def config_js(article: str | None, blog: str | None) -> str:
    """Nav targets; an empty URL leaves that link hidden, e.g. before the article is published."""
    return f"window.VLADBENCH_ARTICLE = {json.dumps(article or None)};\nwindow.VLADBENCH_BLOG = {json.dumps(blog or None)};\n"


def build_site(out: Path, *, article: str | None = None, blog: str | None = "https://www.eventual.ai/blog") -> Path:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    page = (paths.ROOT / "results.html").read_text()
    (out / "embed.html").write_text(embed_html(page))
    (out / "index.html").write_text(page)
    (out / "results.html").write_text(page)                                    # the nav and self-test.html link here
    shutil.copy(paths.ROOT / "self-test.html", out / "self-test.html")
    shutil.copy(paths.RECORD, out / "rerun.json")                              # machine-readable results next to the page
    shutil.copytree(paths.ROOT / "web", out / "web")
    shutil.copytree(paths.ANSWERS, out / "answers")                            # fetched one task at a time when a row expands
    (out / "web/config.js").write_text(config_js(article, blog))
    for name, _ in FILES.values():
        shutil.copy(paths.SITE_DATA / name, out / name)
    for figure in FIGURES:
        shutil.copy(paths.DATASET / figure, out / figure)
    return out
