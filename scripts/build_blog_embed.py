"""Assemble the blog embed bundle: one static folder the blog serves under /blog/assets/vladbench-reeval/.

  PYTHONPATH=src python3 scripts/build_blog_embed.py                       # writes dist/blog/vladbench-reeval/
  PYTHONPATH=src python3 scripts/build_blog_embed.py --into <blog>/content/daft/assets   # and copies it there

The bundle holds site.html (the whole results page), embed.html (the same page in ?embed= mode, loading the slim
task list instead of the 16 MB question file), the web/ assets, the data scripts, and the figures. It prints the
Markdown to paste into the post.
"""

import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist/blog/vladbench-reeval"
DATA_SCRIPTS = ["task-review-tasks.js", "task-review-audit.js", "task-review-published.js", "task-review-results.js", "task-review-variants.js"]
FIGURES = ["results/dataset/cost-vs-score.png", "results/dataset/cost-vs-score-hero.png"]
VIEWS = {
    "overview": ("Leaderboard, Cost vs Score, frontier tables, and the video cost calculator", 2500),
    "leaderboard": ("Leaderboard with score, sweep cost, and metered video costs", 700),
    "plot": ("Cost vs Score with the cost-performance frontier", 640),
    "frontier": ("Cost-performance frontier and marginal cost per point", 520),
    "video": ("Metered cost of video question answering, with knobs", 620),
    "results": ("Our results in the paper's Table 10 layout, above the paper's own table", 2200),
    "score": ("Score by task, one bar per model", 900),
    "matrix": ("Task by model matrix with scorer components", 1600),
}


def embed_html() -> str:
    """results.html with the slim task list instead of the 16 MB question file."""
    html = (ROOT / "results.html").read_text()
    return html.replace('<script src="task-review-data.js" defer></script>', '<script src="task-review-tasks.js" defer></script>')


def site_html() -> str:
    """The whole tabbed page for /blog/VLADBench, with the full question data for the inspector."""
    return (ROOT / "results.html").read_text()


def build(out: Path = OUT) -> Path:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / "embed.html").write_text(embed_html())
    (out / "site.html").write_text(site_html())
    shutil.copy(ROOT / "self-test.html", out / "self-test.html")   # linked from the results nav
    shutil.copytree(ROOT / "web", out / "web", ignore=shutil.ignore_patterns("article-gsap.html"))   # the GSAP prototype stays local
    shutil.copytree(ROOT / "answers", out / "answers")   # per-question answers and marks, one file per task, fetched on expand
    (out / "web/config.js").write_text('window.VLADBENCH_ARTICLE = "/blog/vladbench-reeval";\nwindow.VLADBENCH_BLOG = "/blog";\n')
    for name in DATA_SCRIPTS + ["task-review-data.js"]:
        shutil.copy(ROOT / name, out / name)
    for figure in FIGURES:
        shutil.copy(ROOT / figure, out / Path(figure).name)
    return out


def snippets(base: str) -> str:
    lines = ["## Paste into the post", "", "Static figure:", "", f"![Cost vs Score: overall score against sweep cost for every model, with the cost-performance frontier]({base}/cost-vs-score.png)", "", "Interactive panels (raw HTML passes through the blog's Markdown):", ""]
    for view, (caption, height) in VIEWS.items():
        lines.append(f'<iframe src="{base}/embed.html?embed={view}" title="{caption}" width="100%" height="{height}" loading="lazy" style="border:0;background:#08080b"></iframe>')
        lines.append("")
    lines += ["Add `&models=frontier` or `&models=gemma431,gemini38,astra6` to any embed to show a subset; ids are the protocol file's model ids.",
              "Each iframe is the same page in a different mode; the weights bar, heat pickers, and hover states all work inside the frame.",
              "Heights are starting points; the matrix and results panels scroll inside the frame if the height is shorter than the content."]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--into", type=Path, help="blog assets directory; the bundle lands in <into>/vladbench-reeval/")
    parser.add_argument("--base", default="/blog/assets/vladbench-reeval", help="URL path the blog serves the folder at")
    args = parser.parse_args()
    out = build()
    if args.into:
        target = args.into / "vladbench-reeval"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(out, target)
        print(f"Copied to {target}")
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"Bundle: {out} ({size / 1e6:.1f} MB)\n")
    (out / "SNIPPETS.md").write_text(snippets(args.base) + "\n")
    print(snippets(args.base))


if __name__ == "__main__":
    main()
