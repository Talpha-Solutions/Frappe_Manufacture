# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import csv
import io
from typing import Any

import frappe

from fitzgerald_kitchens.workbook_import.constants import COLUMN_ALIASES, REQUIRED_COLUMNS


class WorkbookParseError(Exception):
	pass


def parse_workbook_file(file_url: str) -> list[dict[str, Any]]:
	"""Read CSV/XLSX attachment and return normalized row dicts."""
	if not file_url:
		raise WorkbookParseError(frappe._("Import File is required."))

	content, extension = _read_file_content(file_url)
	if extension in ("xlsx", "xls"):
		return _parse_xlsx(content)
	return _parse_csv(content)


def _read_file_content(file_url: str) -> tuple[bytes, str]:
	file_doc = frappe.get_doc("File", {"file_url": file_url})
	content = file_doc.get_content()
	extension = (file_doc.file_name or file_url).rsplit(".", 1)[-1].lower()
	return content, extension


def _parse_csv(content: bytes | str) -> list[dict[str, Any]]:
	if isinstance(content, bytes):
		content = content.decode("utf-8-sig")

	reader = csv.DictReader(io.StringIO(content))
	if not reader.fieldnames:
		raise WorkbookParseError(frappe._("Import file has no header row."))

	header_map = _build_header_map(reader.fieldnames)
	rows: list[dict[str, Any]] = []

	for row_number, raw in enumerate(reader, start=2):
		if _is_empty_row(raw):
			continue

		normalized = {"row_number": row_number}
		for header, value in raw.items():
			key = header_map.get(_normalize_header(header))
			if key:
				normalized[key] = (value or "").strip()

		rows.append(normalized)

	if not rows:
		raise WorkbookParseError(frappe._("Import file has no data rows."))

	return rows


def _parse_xlsx(content: bytes) -> list[dict[str, Any]]:
	try:
		import openpyxl
	except ImportError as exc:
		raise WorkbookParseError(
			frappe._("XLSX import requires openpyxl. Upload CSV or install openpyxl.")
		) from exc

	workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
	sheet = workbook.active
	iterator = sheet.iter_rows(values_only=True)
	header_row = next(iterator, None)
	if not header_row:
		raise WorkbookParseError(frappe._("Import file has no header row."))

	headers = [str(cell).strip() if cell is not None else "" for cell in header_row]
	header_map = _build_header_map(headers)
	rows: list[dict[str, Any]] = []

	for row_number, values in enumerate(iterator, start=2):
		raw = {headers[idx]: values[idx] for idx in range(len(headers))}
		if _is_empty_row(raw):
			continue

		normalized = {"row_number": row_number}
		for header, value in raw.items():
			key = header_map.get(_normalize_header(header))
			if key and value is not None:
				normalized[key] = str(value).strip()

		rows.append(normalized)

	if not rows:
		raise WorkbookParseError(frappe._("Import file has no data rows."))

	return rows


def _build_header_map(fieldnames: list[str]) -> dict[str, str]:
	header_map: dict[str, str] = {}
	missing = set(REQUIRED_COLUMNS)

	for fieldname in fieldnames:
		normalized_header = _normalize_header(fieldname)
		mapped = COLUMN_ALIASES.get(normalized_header)
		if mapped:
			header_map[normalized_header] = mapped
			missing.discard(mapped)

	if missing:
		raise WorkbookParseError(
			frappe._("Missing required columns: {0}").format(", ".join(sorted(missing)))
		)

	return header_map


def _normalize_header(header: str | None) -> str:
	return (header or "").strip().lower()


def _is_empty_row(row: dict) -> bool:
	return not any(str(value or "").strip() for value in row.values())
