# images-to-rotate

Images dropped in this folder are picked up by `scripts/build.py` and shuffled
in the square on `docs/about.html`.

- Recognised extensions: `.png .jpg .jpeg .gif .webp .svg`
- No naming convention and no fixed count — the build globs whatever is here.
- Any aspect ratio works: the square crops with `object-fit: cover`.
- This README is ignored (only image extensions are collected).

Add files, then run `make html` (or push — CI rebuilds).
