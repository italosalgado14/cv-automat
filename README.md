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