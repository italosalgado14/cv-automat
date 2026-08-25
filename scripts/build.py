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
from urllib.parse import urlparse, parse_qs

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
    p.add_argument("--about-data",     default="data/about.json",            help="Path to about-page JSON")
    p.add_argument("--about-template", default="templates/about.html.j2",    help="Path to about Jinja2 template")
    p.add_argument("--about-out",      default="docs/about.html",            help="Output about HTML path")
    p.add_argument("--rotate-dir",     default="docs/images-to-rotate",      help="Folder of images shuffled on the about page")
    p.add_argument("--buttons-dir",    default="docs/buttons",               help="Folder holding UI button images")
    p.add_argument("--play-button",    default="play2.jpg",                  help="Filename inside --buttons-dir to use for the about-page play button")
    p.add_argument("--dump-json",      action="store_true",                  help="Print extracted JSON and exit")
    return p.parse_args()


# ── Multi-language CV definitions ─────────────────────────────────────────────

CV_LANGS = [
    {"lang": "en", "cv": "cv/cv_en.tex", "out": "docs/index.html"},
    {"lang": "es", "cv": "cv/cv_es.tex", "out": "docs/es.html"},
]


# ── About-page image rotation ─────────────────────────────────────────────────

ROTATE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


def collect_rotating_images(rotate_dir: Path, docs_dir: Path) -> list[str]:
    """
    Return the images in `rotate_dir` as paths relative to `docs_dir`
    (i.e. usable as-is in <img src=...>). Non-images (README, etc.) are ignored.
    """
    if not rotate_dir.is_dir():
        return []
    return [
        p.relative_to(docs_dir).as_posix()
        for p in sorted(rotate_dir.iterdir())
        if p.is_file() and p.suffix.lower() in ROTATE_EXTS
    ]


# ── About-page videos ─────────────────────────────────────────────────────────

YOUTUBE_ID = re.compile(r"[A-Za-z0-9_-]{11}")
YOUTUBE_HOSTS = {"youtube.com", "m.youtube.com", "youtube-nocookie.com", "music.youtube.com"}
TIMESTAMP = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?$")


def youtube_id(url: str) -> str | None:
    """
    Return the 11-character video id from any common YouTube URL form
    (watch?v=ID, youtu.be/ID, /embed/ID, /shorts/ID, /live/ID) or from a
    bare id. Returns None when the string is not recognisably a YouTube video.
    """
    url = url.strip()
    if YOUTUBE_ID.fullmatch(url):
        return url

    parts = urlparse(url if "//" in url else "https://" + url)
    host  = parts.netloc.lower().removeprefix("www.")

    if host == "youtu.be":
        candidate = parts.path.lstrip("/").split("/")[0]
    elif host in YOUTUBE_HOSTS:
        if parts.path.rstrip("/") == "/watch":
            candidate = parse_qs(parts.query).get("v", [""])[0]
        else:
            m = re.match(r"^/(?:embed|shorts|live|v)/([^/?#]+)", parts.path)
            candidate = m.group(1) if m else ""
    else:
        return None

    return candidate if YOUTUBE_ID.fullmatch(candidate) else None


def youtube_start(url: str) -> int:
    """Start offset in seconds from ?t= / ?start= (accepts 90, 90s, 1h2m3s)."""
    query = parse_qs(urlparse(url).query)
    raw   = (query.get("start") or query.get("t") or [""])[0].strip().lower()
    if not raw:
        return 0
    if raw.isdigit():
        return int(raw)
    m = TIMESTAMP.match(raw)
    if not m or not any(m.groups()):
        return 0
    hours, minutes, seconds = (int(g or 0) for g in m.groups())
    return hours * 3600 + minutes * 60 + seconds


def collect_videos(about: dict) -> list[dict]:
    """
    Normalise about["videos"] (or a single about["video"]) into
    [{id, url, title, start}, ...]. Entries whose URL is empty or not a
    YouTube link are dropped — a placeholder with "url": "" simply means
    "no play button yet".
    """
    raw = about.get("videos")
    if raw is None:
        raw = [about["video"]] if about.get("video") else []
    if isinstance(raw, (str, dict)):
        raw = [raw]

    videos: list[dict] = []
    for entry in raw:
        if isinstance(entry, str):
            entry = {"url": entry}
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url") or "").strip()
        if not url:
            continue
        vid = youtube_id(url)
        if not vid:
            print(f"SKIP video (not a recognised YouTube URL): {url}")
            continue
        videos.append({
            "id":    vid,
            "url":   url,
            "title": str(entry.get("title") or "youtube video").strip(),
            "start": youtube_start(url),
        })
    return videos


BUTTON_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


def find_play_button(buttons_dir: Path, docs_dir: Path,
                     preferred: str) -> str | None:
    """
    Path to the play-button image relative to docs/, or None (the template
    falls back to a ▶ glyph).

    `preferred` wins whenever that exact file exists. Otherwise any other
    play*.<image> in the folder is used, so swapping the file for a different
    name or extension does not silently drop the button back to the glyph.
    """
    if not buttons_dir.is_dir():
        return None

    others = sorted(
        p for p in buttons_dir.iterdir()
        if p.is_file()
        and p.suffix.lower() in BUTTON_EXTS
        and p.name.lower().startswith("play")
        and p.name != preferred
    )

    for candidate in [buttons_dir / preferred, *others]:
        if not candidate.is_file():
            continue
        try:
            return candidate.relative_to(docs_dir).as_posix()
        except ValueError:
            continue
    return None


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
    text = text.replace("---", "-")
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

    # 3.5  LaTeX accent commands → Unicode  (handles {\'e} and \'e forms)
    _ACCENTS = {
        "'": {'a':'á','e':'é','i':'í','o':'ó','u':'ú','A':'Á','E':'É','I':'Í','O':'Ó','U':'Ú'},
        '`': {'a':'à','e':'è','i':'ì','o':'ò','u':'ù'},
        '"': {'a':'ä','e':'ë','i':'ï','o':'ö','u':'ü','A':'Ä','E':'Ë','O':'Ö','U':'Ü'},
        '^': {'a':'â','e':'ê','i':'î','o':'ô','u':'û'},
        '~': {'a':'ã','n':'ñ','o':'õ','A':'Ã','N':'Ñ','O':'Õ'},
    }
    def _accent_sub(m):
        mark = m.group(1) or m.group(3)
        char = m.group(2) or m.group(4)
        return _ACCENTS.get(mark, {}).get(char, char)
    text = re.sub(r"\{\\(['\"`^~])([a-zA-Z])\}|\\(['\"`^~])([a-zA-Z])", _accent_sub, text)

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
            "tags":     [clean_latex(s) for s in raw_items.split(",") if s.strip()],
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
    about_data_path = repo_root / args.about_data
    about_tmpl_path = repo_root / args.about_template
    about_out_path  = repo_root / args.about_out
    rotate_dir      = repo_root / args.rotate_dir
    buttons_dir     = repo_root / args.buttons_dir

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

    # ── Build about page ───────────────────────────────────────────
    if about_tmpl_path.exists() and person_data:
        about = json.loads(about_data_path.read_text(encoding="utf-8")) \
                if about_data_path.exists() else {"sections": []}
        images      = collect_rotating_images(rotate_dir, about_out_path.parent)
        videos      = collect_videos(about)
        play_button = find_play_button(buttons_dir, about_out_path.parent,
                                       args.play_button)
        about_html = render({"person":      person_data["person"],
                             "about":       about,
                             "images":      images,
                             "videos":      videos,
                             "play_button": play_button}, about_tmpl_path)
        about_out_path.write_text(about_html, encoding="utf-8")
        print(f"Built: {about_out_path} "
              f"({len(images)} image(s) to shuffle, {len(videos)} video(s))")
    else:
        print(f"Skipped about page (template not found: {about_tmpl_path})")


if __name__ == "__main__":
    main()
