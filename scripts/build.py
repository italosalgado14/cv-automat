#!/usr/bin/env python3
"""
build.py — Parse cv.tex → structured dict → render Jinja2 template → docs/index.html

Usage:
    python scripts/build.py
    python scripts/build.py --cv cv/cv.tex --template templates/index.html.j2 --out docs/index.html
    python scripts/build.py --dump-json   # print extracted JSON and exit
"""

import re
import sys
import json
import argparse
from pathlib import Path

# Jinja2 is the only non-stdlib dependency
try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ImportError:
    sys.exit("Missing dependency: pip install jinja2")


# ── Argument parser ────────────────────────────────────────────────────────────

def cli() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cv",             default=None,                         help="Path to cv.tex (overrides multi-lang)")
    p.add_argument("--template",       default="templates/index.html.j2",    help="Path to CV Jinja2 template")
    p.add_argument("--out",            default=None,                         help="Output CV HTML path (overrides multi-lang)")
    p.add_argument("--posts-data",     default="data/posts.json",            help="Path to posts JSON")
    p.add_argument("--posts-template", default="templates/posts.html.j2",   help="Path to posts Jinja2 template")
    p.add_argument("--posts-out",      default="docs/posts.html",            help="Output posts HTML path")
    p.add_argument("--certs-data",     default="data/certifications.json",   help="Path to certifications JSON")
    p.add_argument("--dump-json",      action="store_true",                  help="Print extracted JSON and exit")
    return p.parse_args()


# ── Multi-language CV definitions ─────────────────────────────────────────────

CV_LANGS = [
    {"lang": "en", "cv": "cv/cv_en.tex", "out": "docs/index.html"},
    {"lang": "es", "cv": "cv/cv_es.tex", "out": "docs/es.html"},
]


# ── Brace-balanced argument extractor ─────────────────────────────────────────

def extract_args(text: str, start: int, n: int) -> tuple[list[str], int]:
    """
    Extract n brace-balanced arguments from `text` starting at position `start`.
    Handles nested braces and escaped characters (e.g. \\{ \\}).
    Returns (list_of_arg_strings, position_after_last_arg).
    """
    args: list[str] = []
    pos = start
    for _ in range(n):
        # skip whitespace / newlines between arguments
        while pos < len(text) and text[pos] in " \t\n":
            pos += 1
        if pos >= len(text) or text[pos] != "{":
            break
        depth = 0
        arg_start = pos + 1
        while pos < len(text):
            ch = text[pos]
            if ch == "\\":
                pos += 2          # skip backslash + next char (escaped brace, etc.)
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    args.append(text[arg_start:pos])
                    pos += 1
                    break
            pos += 1
    return args, pos


# ── LaTeX → HTML cleanup ───────────────────────────────────────────────────────

def clean_latex(text: str) -> str:
    """
    Convert a LaTeX snippet to an HTML-safe string.
    Preserves inline semantic markup as HTML tags.
    """
    # 1. Strip LaTeX line comments (% not preceded by \)
    text = re.sub(r"(?<!\\)%[^\n]*", "", text)

    # 2. Typographic dashes  (must come before \% handling)
    text = text.replace("---", "\u2014")   # em-dash
    text = text.replace("--",  "\u2013")   # en-dash

    # 3. LaTeX special-character escapes
    replacements = [
        (r"\%", "%"),
        (r"\&", "&amp;"),
        (r"\$", "$"),
        (r"\#", "#"),
        (r"\_", "_"),
    ]
    for src, dst in replacements:
        text = text.replace(src, dst)

    # narrow no-break space  (\,)
    text = re.sub(r"\\,", "\u202f", text)

    # 4. Inline math
    text = re.sub(r"\$\\times\$", "\u00d7", text)          # $\times$ → ×
    text = re.sub(r"\$10\^\\times\$", "10\u00d7", text)
    text = re.sub(r"\$([^$]+)\$", r"\1", text)             # strip remaining $ delimiters

    # 5. Formatting commands → HTML  (one level of nesting is enough for this CV)
    text = re.sub(r"\\textbf\{([^{}]*)\}", r"<strong>\1</strong>", text)
    text = re.sub(r"\\textit\{([^{}]*)\}", r"<em>\1</em>",         text)
    text = re.sub(r"\\texttt\{([^{}]*)\}", r"<code>\1</code>",     text)
    text = re.sub(r"\\href\{([^{}]+)\}\{([^{}]+)\}",
                  r'<a href="\1">\2</a>', text)

    # 6. Strip remaining \commands (with optional star and trailing space)
    text = re.sub(r"\\[a-zA-Z@]+\*?\s*", "", text)

    # 7. Strip stray bare braces left over from LaTeX grouping
    text = text.replace("{", "").replace("}", "")

    # 8. Normalise whitespace
    text = re.sub(r"[ \t]+",  " ", text)
    text = re.sub(r"\n\s*\n", " ", text)
    text = re.sub(r"\s+",     " ", text).strip()

    return text


def extract_items(block: str) -> list[str]:
    """
    Extract bullet text from a LaTeX itemize block.
    Returns a list of HTML-cleaned strings, one per \\item.
    """
    # drop the environment wrappers
    block = re.sub(r"\\begin\{[^}]+\}", "", block)
    block = re.sub(r"\\end\{[^}]+\}",   "", block)
    parts = re.split(r"\\item\b", block)
    return [clean_latex(p) for p in parts if p.strip()]


# ── CV parser ──────────────────────────────────────────────────────────────────

def parse_cv(tex: str) -> dict:
    """
    Parse cv.tex and return a structured dict.
    Only the parse-target custom commands defined in the DESIGN CONTRACT are read.
    Everything else (preamble, layout commands) is ignored.
    """
    # Restrict search to the document body so \newcommand definitions
    # (which also mention the command names) are never accidentally matched.
    body_match = re.search(r"\\begin\{document\}", tex)
    body = tex[body_match.start():] if body_match else tex

    data: dict = {}

    # ── 1. \cvperson{name}{email}{phone}{linkedin}{github}{website} ────────────
    m = re.search(r"\\cvperson", body)
    if m:
        args, _ = extract_args(body, m.end(), 6)
        data["person"] = {
            "name":     args[0].strip() if len(args) > 0 else "",
            "email":    args[1].strip() if len(args) > 1 else "",
            "phone":    args[2].strip() if len(args) > 2 else "",
            "linkedin": args[3].strip() if len(args) > 3 else "",
            "github":   args[4].strip() if len(args) > 4 else "",
            "website":  args[5].strip() if len(args) > 5 else "",
        }

    # ── 2. \section{Summary} … freeform text (until next \section) ────────────
    m = re.search(r"\\section\{Summary\}(.*?)(?=\\section)", body, re.DOTALL)
    if m:
        raw = re.sub(r"%%?[^\n]*", "", m.group(1))   # strip comments
        data["summary"] = re.sub(r"\s+", " ", raw).strip()

    # ── 3. \experience{title}{company}{location}{dates}{bullets} ──────────────
    data["experience"] = []
    for m in re.finditer(r"\\experience(?!\s*\[)", body):   # skip \experience[ ]
        args, _ = extract_args(body, m.end(), 5)
        if len(args) < 5:
            continue
        data["experience"].append({
            "title":    clean_latex(args[0]),
            "company":  clean_latex(args[1]),
            "location": clean_latex(args[2]),
            "dates":    clean_latex(args[3]),
            "bullets":  extract_items(args[4]),
        })

    # ── 4. \project{name}{tech}{dates}{bullets} ───────────────────────────────
    data["projects"] = []
    for m in re.finditer(r"\\project(?!\s*\[)", body):
        args, _ = extract_args(body, m.end(), 4)
        if len(args) < 4:
            continue
        data["projects"].append({
            "name":    clean_latex(args[0]),
            "tech":    clean_latex(args[1]),
            "dates":   clean_latex(args[2]),
            "bullets": extract_items(args[3]),
        })

    # ── 5. \education{degree}{institution}{location}{dates}{details} ──────────
    data["education"] = []
    for m in re.finditer(r"\\education(?!\s*\[)", body):
        args, _ = extract_args(body, m.end(), 5)
        if len(args) < 5:
            continue
        data["education"].append({
            "degree":      clean_latex(args[0]),
            "institution": clean_latex(args[1]),
            "location":    clean_latex(args[2]),
            "dates":       clean_latex(args[3]),
            "details":     clean_latex(args[4]),
        })

    # ── 6. \skillgroup{category}{comma-separated items} ───────────────────────
    data["skills"] = []
    for m in re.finditer(r"\\skillgroup(?!\s*\[)", body):
        args, _ = extract_args(body, m.end(), 2)
        if len(args) < 2:
            continue
        raw_items = re.sub(r"\\,", "\u202f", args[1])   # \, → narrow space before split
        data["skills"].append({
            "category": clean_latex(args[0]),
            "tags":     [s.strip() for s in raw_items.split(",") if s.strip()],
        })

    return data


# ── Renderer ───────────────────────────────────────────────────────────────────

def render(data: dict, template_path: Path) -> str:
    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        autoescape=select_autoescape(["html"]),
    )
    # We produce safe HTML strings in clean_latex, so mark them safe in Jinja2.
    from markupsafe import Markup
    env.filters["safe_html"] = lambda s: Markup(s)

    tmpl = env.get_template(template_path.name)
    return tmpl.render(**data)


# ── Entry point ────────────────────────────────────────────────────────────────

def build_cv(repo_root: Path, cv_rel: str, template_path: Path,
             out_rel: str, certs_data_path: Path, lang: str,
             dump_json: bool = False) -> dict | None:
    """Build a single CV variant. Returns parsed data (for reuse in posts)."""
    cv_path  = repo_root / cv_rel
    out_path = repo_root / out_rel

    if not cv_path.exists():
        print(f"SKIP: CV file not found: {cv_path}")
        return None
    if not template_path.exists():
        sys.exit(f"ERROR: Template not found: {template_path}")

    tex  = cv_path.read_text(encoding="utf-8")
    data = parse_cv(tex)

    if dump_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return data

    # ── Split skills → tech_skills + languages ─────────────────────
    all_skills  = data.get("skills", [])
    tech_skills = [s for s in all_skills if "human" not in s["category"].lower()]
    languages   = [s for s in all_skills if "human"     in s["category"].lower()]
    lang_tags   = languages[0]["tags"] if languages else []

    # ── Load certifications ────────────────────────────────────────
    certifications = (
        json.loads(certs_data_path.read_text(encoding="utf-8"))
        if certs_data_path.exists() else []
    )

    # ── Determine the other language link ──────────────────────────
    lang_switch = {"en": "es.html", "es": "index.html"}

    # ── Build CV page ──────────────────────────────────────────────
    index_ctx = {**data,
                 "tech_skills":    tech_skills,
                 "lang_tags":      lang_tags,
                 "certifications": certifications,
                 "lang":           lang,
                 "lang_switch_url": lang_switch.get(lang, "")}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(index_ctx, template_path), encoding="utf-8")
    print(f"Built: {out_path} [{lang}]")
    return data


def main() -> None:
    args = cli()

    repo_root       = Path(__file__).parent.parent
    template_path   = repo_root / args.template
    posts_data_path = repo_root / args.posts_data
    posts_tmpl_path = repo_root / args.posts_template
    posts_out_path  = repo_root / args.posts_out
    certs_data_path = repo_root / args.certs_data

    # ── Build CV(s) ────────────────────────────────────────────────
    if args.cv and args.out:
        # Single-file mode (backward compat)
        person_data = build_cv(repo_root, args.cv, template_path, args.out,
                               certs_data_path, lang="en", dump_json=args.dump_json)
    else:
        # Multi-language mode (default)
        person_data = None
        for entry in CV_LANGS:
            d = build_cv(repo_root, entry["cv"], template_path, entry["out"],
                         certs_data_path, lang=entry["lang"], dump_json=args.dump_json)
            if d and person_data is None:
                person_data = d

    if args.dump_json:
        return

    # ── Build posts page ───────────────────────────────────────────
    if posts_tmpl_path.exists() and person_data:
        posts = json.loads(posts_data_path.read_text(encoding="utf-8")) \
                if posts_data_path.exists() else []
        posts_html = render({"person": person_data["person"], "posts": posts}, posts_tmpl_path)
        posts_out_path.write_text(posts_html, encoding="utf-8")
        print(f"Built: {posts_out_path}")
    else:
        print(f"Skipped posts page (template not found: {posts_tmpl_path})")


if __name__ == "__main__":
    main()
