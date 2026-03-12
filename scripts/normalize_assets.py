#!/usr/bin/env python3
"""
normalize_assets.py — Make every image in docs/assets/ square by padding
with transparency (does NOT crop or resize).

Rules:
  - Already-square images are left untouched.
  - Non-square images are centered on a transparent square canvas whose
    side equals max(width, height), then saved as PNG.
  - If the original was a JPEG (.jpg/.jpeg) it is replaced by a .png file
    and any reference in data/posts.json is updated automatically.

Usage:
    python scripts/normalize_assets.py
    python scripts/normalize_assets.py --assets docs/assets --posts data/posts.json
"""

import argparse
import json
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Missing dependency: pip install Pillow")

SUPPORTED = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


# ── CLI ────────────────────────────────────────────────────────────────────────

def cli() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    repo_root = Path(__file__).parent.parent
    p.add_argument("--assets", default=str(repo_root / "docs" / "assets"),
                   help="Path to assets directory")
    p.add_argument("--posts",  default=str(repo_root / "data" / "posts.json"),
                   help="Path to posts.json (updated when files are renamed)")
    return p.parse_args()


# ── Image processing ───────────────────────────────────────────────────────────

def pad_to_square(img_path: Path) -> Path | None:
    """
    Pad `img_path` to a square with transparent background.
    Returns the (possibly renamed) output path, or None if already square.
    """
    img = Image.open(img_path).convert("RGBA")
    w, h = img.size

    if w == h:
        return None  # nothing to do

    s = max(w, h)
    canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    canvas.paste(img, ((s - w) // 2, (s - h) // 2))

    # Always output PNG to preserve the alpha channel
    out_path = img_path.with_suffix(".png")
    canvas.save(out_path, "PNG", optimize=True)

    # Remove the original only when it differs from the output (jpg → png)
    if out_path != img_path:
        img_path.unlink()

    print(f"  ✓ {img_path.name} → {out_path.name}  ({w}×{h} → {s}×{s})")
    return out_path


# ── posts.json patch ───────────────────────────────────────────────────────────

def patch_posts_json(posts_path: Path, renames: dict[str, str]) -> None:
    """
    Replace image paths in posts.json when a file was renamed (e.g. .jpg → .png).
    `renames` maps old basename (e.g. 'ibm1.jpg') to new basename ('ibm1.png').
    """
    if not renames or not posts_path.exists():
        return

    posts = json.loads(posts_path.read_text(encoding="utf-8"))
    changed = False

    for entry in posts:
        img = entry.get("image", "")
        basename = Path(img).name
        if basename in renames:
            new_img = str(Path(img).with_name(renames[basename]))
            print(f"  posts.json: {img!r} → {new_img!r}")
            entry["image"] = new_img
            changed = True

    if changed:
        posts_path.write_text(
            json.dumps(posts, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    args  = cli()
    assets_dir = Path(args.assets)
    posts_path = Path(args.posts)

    if not assets_dir.exists():
        print(f"Assets directory not found: {assets_dir}  — nothing to do.")
        return

    images = sorted(
        p for p in assets_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED
    )

    if not images:
        print("No images found in assets directory.")
        return

    print(f"Checking {len(images)} image(s) in {assets_dir} …")

    renames: dict[str, str] = {}   # old_name → new_name

    for img_path in images:
        out = pad_to_square(img_path)
        if out is None:
            print(f"  – {img_path.name}  (already square, skipped)")
        elif out.name != img_path.name:
            renames[img_path.name] = out.name

    if renames:
        print(f"\nPatching {posts_path.name} for {len(renames)} rename(s) …")
        patch_posts_json(posts_path, renames)

    print("\nDone.")


if __name__ == "__main__":
    main()
