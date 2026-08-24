# images-to-rotate

Images dropped in this folder are picked up by `scripts/build.py` and shuffled
in the 16:9 box on `docs/about.html`.

- Recognised extensions: `.png .jpg .jpeg .gif .webp .svg`
- No naming convention and no fixed count — the build globs whatever is here.
- Any aspect ratio works: the box crops with `object-fit: cover` (it is 16:9, so
  tall portraits lose their top and bottom).
- This README is ignored (only image extensions are collected).

Add files, then run `make html` (or push — CI rebuilds).
