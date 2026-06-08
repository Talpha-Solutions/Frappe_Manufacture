# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

from fitzgerald_kitchens.workbook_import.constants import QTY_COLUMNS


def parse_row_qtys(row: dict[str, Any]) -> dict[str, int]:
	qtys: dict[str, int] = {}
	for col, _project_type in QTY_COLUMNS:
		raw = row.get(col, 0)
		if raw in (None, ""):
			qtys[col] = 0
			continue
		qtys[col] = int(float(str(raw).strip()))
	return qtys
