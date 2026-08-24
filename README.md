# AUTOCV

Generate a static page with a CV in one repo

Compiled PDF with:

```
pdflatex -output-directory=cv cv/cv_en.tex && pdflatex -output-directory=cv cv/cv_es.tex
```
# Based on

https://owickstrom.github.io/the-monospace-web/

# URLs

https://italosalgado14.github.io/cv-automat/    --> CV page

https://italosalgado14.github.io/cv-automat/posts.html --> Posts page

https://italosalgado14.github.io/cv-automat/about.html --> About page (text in `data/about.json`, shuffled images in `docs/images-to-rotate/`)

The about page shuffles the images at a constant speed for 5 s, then shows a play
button (`docs/buttons/play.png`) over the settled square. Fill in `videos` in
`data/about.json` — any YouTube URL form works (`watch?v=`, `youtu.be/`, `shorts/`,
`embed/`, `live/`, `?t=1m30s` honoured). Empty URLs are skipped, so no URL means no
button. With more than one entry, one is drawn at random per page load.
