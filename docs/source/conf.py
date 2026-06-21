from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

project = "BILBO"
author = "Laboratório de Fisiologia Molecular de Plantas, Universidade Federal de Lavras"
copyright = f"{date.today().year}, Laboratório de Fisiologia Molecular de Plantas, Universidade Federal de Lavras"
release = "1.0.0"

extensions = [
    "myst_parser",
    "sphinx.ext.autosectionlabel",
]

autosectionlabel_prefix_document = True
templates_path = ["_templates"]
exclude_patterns: list[str] = []

html_theme = "sphinx_rtd_theme"
html_title = "BILBO RNA-seq Documentation"
html_static_path = ["_static"]
html_css_files = ["custom.css"]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

master_doc = "index"
language = "en"
nitpicky = False
