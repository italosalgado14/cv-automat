# images-to-rotate

Images dropped in this folder are picked up by `scripts/build.py` and shuffled
in the 16:9 box on `docs/about.html`.

- Recognised extensions: `.png .jpg .jpeg .gif .webp .svg`
- No naming convention and no fixed count — the build globs whatever is here.
- Any aspect ratio works: the box crops with `object-fit: cover` (it is 16:9, so
  tall portraits lose their top and bottom).
- This README is ignored (only image extensions are collected).

## Size

Drop full-resolution files here if you like — `scripts/normalize_assets.py`
caps the longest side at **2400px** (JPEG/WebP quality 85) in place, keeping the
filename and format. `.gif` and `.svg` are left alone.

This matters: the shuffler flips frames every 120ms via `display:none/block`,
and a hidden image loses its decoded bitmap, so each flip re-decodes the file
on the main thread. A 6000px photo takes longer to decode than the interval
between flips, which freezes the page.

Files already within the cap are skipped, never re-encoded — so CI can run this
on every push without stacking JPEG generation loss.

Add files, then run `make assets && make html` (or push — CI does both).
