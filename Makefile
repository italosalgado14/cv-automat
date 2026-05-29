## ============================================================
##  cv-automat — build targets
##  Usage: `make help` to list targets
## ============================================================

PYTHON      ?= python
VENV        ?= .venv
PIP         := $(VENV)/bin/pip
PY          := $(VENV)/bin/python

CV_DIR      := cv
TEX_SOURCES := $(CV_DIR)/cv_en.tex $(CV_DIR)/cv_es.tex
PDF_OUTPUTS := $(CV_DIR)/cv_italo_salgado_en.pdf $(CV_DIR)/cv_italo_salgado_es.pdf

LATEX       ?= tectonic
LATEX_FLAGS ?=

.DEFAULT_GOAL := help
.PHONY: help install venv html pdf build assets clean clean-tex clean-pdf clean-all

help:
	@echo "Targets:"
	@echo "  install     Create venv and install Python deps"
	@echo "  html        Render docs/*.html from cv/*.tex"
	@echo "  pdf         Compile cv/*.tex to PDF (requires tectonic or pdflatex)"
	@echo "  build       html + pdf"
	@echo "  assets      Normalize images under docs/assets/"
	@echo "  clean       Remove LaTeX aux files"
	@echo "  clean-pdf   Remove generated PDFs"
	@echo "  clean-all   Remove venv, aux files, and generated PDFs"

## ── Dependencies ─────────────────────────────────────────────
$(VENV)/bin/activate: requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@touch $@

venv: $(VENV)/bin/activate

install: venv

## ── HTML ─────────────────────────────────────────────────────
html: venv
	$(PY) scripts/build.py

## ── PDF ──────────────────────────────────────────────────────
pdf: $(PDF_OUTPUTS)

$(CV_DIR)/cv_italo_salgado_en.pdf: $(CV_DIR)/cv_en.tex
	cd $(CV_DIR) && $(LATEX) $(LATEX_FLAGS) cv_en.tex
	mv $(CV_DIR)/cv_en.pdf $@

$(CV_DIR)/cv_italo_salgado_es.pdf: $(CV_DIR)/cv_es.tex
	cd $(CV_DIR) && $(LATEX) $(LATEX_FLAGS) cv_es.tex
	mv $(CV_DIR)/cv_es.pdf $@

## ── Combined ─────────────────────────────────────────────────
build: html pdf

## ── Assets ───────────────────────────────────────────────────
assets: venv
	$(PY) scripts/normalize_assets.py

## ── Cleanup ──────────────────────────────────────────────────
clean: clean-tex

clean-tex:
	rm -f $(CV_DIR)/*.aux $(CV_DIR)/*.log $(CV_DIR)/*.out

clean-pdf:
	rm -f $(PDF_OUTPUTS)

clean-all: clean-tex clean-pdf
	rm -rf $(VENV)
