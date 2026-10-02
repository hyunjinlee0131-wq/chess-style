"""Percent-format .py ('# %%' cells) -> .ipynb next to it."""
import sys
from pathlib import Path

import nbformat as nbf

src = Path(sys.argv[1])
cells = [c.strip() for c in src.read_text(encoding="utf-8").split("# %%") if c.strip()]
nbf.write(nbf.v4.new_notebook(cells=[nbf.v4.new_code_cell(c) for c in cells]), src.with_suffix(".ipynb"))
