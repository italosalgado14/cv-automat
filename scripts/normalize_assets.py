#!/usr/bin/env python3
"""
normalize_assets.py — Prepare images for the web before build.py renders them.

Two independent passes:

  1. docs/assets/  — pad to square with transparency (does NOT crop or resize).
       - Already-square images are left untouched.
       - Non-square images are centered on a transparent square canvas whose
         side equals max(width, height), then saved as PNG.
       - If the original was a JPEG (.jpg/.jpeg) it is replaced by a .png file
         and any reference in data/posts.json is updated automatically.

  2. docs/images-to-rotate/  — downscale for the about-page shuffler.
       Straight-off-camera photos are 6000px wide / 10-20MB each; the shuffler
       box renders at ~1600px, and every flip forces a full decode on the main
       thread. Anything whose longest side exceeds --rotate-max-width is shrunk
       in place, keeping its original format and filename.

Pass 2 is idempotent on purpose: a file already within the cap is skipped, not
re-encoded. CI runs this script on every push, so re-encoding would stack JPEG
generation loss and produce an endless stream of "rebuild" commits.

Usage:
    python scripts/normalize_assets.py
    python scripts/normalize_assets.py --dry-run
    python scripts/normalize_assets.py --rotate-max-width 1600 --quality 80
"""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("Missing dependency: pip install Pillow")

SUPPORTED = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# Formats we can safely re-encode. .gif is excluded (resizing kills animation)
# and .svg never reaches Image.open at all.
RESIZABLE = {".jpg", ".jpeg", ".png", ".webp"}

SAVE_FORMAT = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}


# ── CLI ────────────────────────────────────────────────────────────────────────

def cli() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    repo_root = Path(__file__).parent.parent
    p.add_argument("--assets", default=str(repo_root / "docs" / "assets"),
                   help="Path to assets directory")
    p.add_argument("--posts",  default=str(repo_root / "data" / "posts.json"),
                   help="Path to posts.json (updated when files are renamed)")
    p.add_argument("--rotate", default=str(repo_root / "docs" / "images-to-rotate"),
                   help="Folder of shuffler images to downscale")
    p.add_argument("--rotate-max-width", type=int, default=2400, metavar="PX",
                   help="Cap on the longest side of a shuffler image (default: 2400)")
    p.add_argument("--quality", type=int, default=85, metavar="Q",
                   help="JPEG/WebP quality used when downscaling (default: 85)")
    p.add_argument("--dry-run", action="store_true",
                   help="Report what would change without writing anything")
    return p.parse_args()


# ── Pass 1: docs/assets — pad to square ────────────────────────────────────────

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


# ── Pass 2: docs/images-to-rotate — downscale ──────────────────────────────────

def downscale(img_path: Path, max_side: int, quality: int, dry_run: bool) -> int:
    """
    Shrink `img_path` in place so its longest side is at most `max_side`.
    Format and filename are preserved. Returns the bytes saved (0 if skipped).
    """
    with Image.open(img_path) as probe:
        w, h = probe.size

    if max(w, h) <= max_side:
        return 0

    before = img_path.stat().st_size
    fmt = SAVE_FORMAT[img_path.suffix.lower()]

    with Image.open(img_path) as img:
        # Bake camera rotation into the pixels — we drop EXIF on save, so an
        # unapplied orientation tag would silently flip the photo.
        img = ImageOps.exif_transpose(img)
        icc = img.info.get("icc_profile")

        # JPEG has no alpha and no palette; WebP/PNG keep whatever they had.
        # Grayscale ("L") is a valid JPEG mode, so leave it alone.
        if fmt == "JPEG" and img.mode in ("RGBA", "P", "CMYK", "LA"):
            img = img.convert("RGB")

        img.thumbnail((max_side, max_side), Image.LANCZOS)
        new_w, new_h = img.size

        if dry_run:
            print(f"  → {img_path.name:18s} {w}×{h} → {new_w}×{new_h}   "
                  f"({before / 1e6:.1f} MB → ?)")
            return before

        opts = {"optimize": True}
        if fmt in ("JPEG", "WEBP"):
            opts["quality"] = quality
        if fmt == "JPEG":
            opts["progressive"] = True
        if icc:
            opts["icc_profile"] = icc

        # Write beside the original, then swap: a crash mid-encode must not
        # leave a truncated photo behind. Format is passed explicitly because
        # the ".tmp" suffix gives Pillow nothing to infer from.
        tmp = img_path.with_name(img_path.name + ".tmp")
        img.save(tmp, format=fmt, **opts)

    os.replace(tmp, img_path)
    after = img_path.stat().st_size
    print(f"  ✓ {img_path.name:18s} {w}×{h} → {new_w}×{new_h}   "
          f"{before / 1e6:.1f} MB → {after / 1e6:.2f} MB")
    return before - after


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


# ── Passes ─────────────────────────────────────────────────────────────────────

def normalize_assets(assets_dir: Path, posts_path: Path, dry_run: bool) -> None:
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

    print(f"Squaring {len(images)} image(s) in {assets_dir} …")

    if dry_run:
        print("  (dry run — pass 1 skipped)")
        return

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


def shrink_rotating(rotate_dir: Path, max_side: int, quality: int,
                    dry_run: bool) -> None:
    if not rotate_dir.exists():
        print(f"\nRotate directory not found: {rotate_dir}  — nothing to do.")
        return

    images = sorted(
        p for p in rotate_dir.iterdir()
        if p.is_file() and p.suffix.lower() in RESIZABLE
    )

    if not images:
        print(f"\nNo resizable images in {rotate_dir}.")
        return

    total_before = sum(p.stat().st_size for p in images)
    print(f"\nCapping {len(images)} image(s) in {rotate_dir} at {max_side}px "
          f"(quality {quality}) …")

    touched = 0
    for img_path in images:
        if downscale(img_path, max_side, quality, dry_run):
            touched += 1

    skipped = len(images) - touched
    if dry_run:
        print(f"\n  {touched} would be resized, {skipped} already within the cap.")
        return

    total_after = sum(p.stat().st_size for p in images)
    print(f"\n  {touched} resized, {skipped} already within the cap.")
    print(f"  Folder: {total_before / 1e6:.1f} MB → {total_after / 1e6:.1f} MB")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    args = cli()

    if args.dry_run:
        print("DRY RUN — no files will be written.\n")

    normalize_assets(Path(args.assets), Path(args.posts), args.dry_run)
    shrink_rotating(Path(args.rotate), args.rotate_max_width, args.quality,
                    args.dry_run)

    print("\nDone.")


if __name__ == "__main__":
    main()
