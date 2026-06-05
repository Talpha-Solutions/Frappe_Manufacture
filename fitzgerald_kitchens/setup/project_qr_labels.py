# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import base64
import zipfile
from io import BytesIO

import frappe
from frappe import _
from frappe.utils import cint, flt

from fitzgerald_kitchens.fitzgerald_kitchens.utils.qr_codes import generate_qr_png_bytes


def slug_item_code(item_code: str) -> str:
	slug = frappe.scrub(item_code or "").replace("_", "-").upper()
	return slug or "ITEM"


def _item_name_map(item_codes: set[str]) -> dict[str, str]:
	if not item_codes:
		return {}

	return {
		row.name: row.item_name
		for row in frappe.get_all(
			"Item",
			filters={"name": ["in", list(item_codes)]},
			fields=["name", "item_name"],
		)
	}


def expand_manifest_item_instances(project: str, manifest_name: str | None = None) -> list[dict]:
	"""Expand manifest qty into one row per label instance with unique item codes."""
	if not manifest_name:
		manifest_name = frappe.db.get_value("Project", project, "fk_effective_manifest")

	if not manifest_name:
		return []

	if not frappe.db.exists("Manifest", manifest_name):
		return []

	manifest = frappe.get_doc("Manifest", manifest_name)
	counters: dict[str, int] = {}
	rows: list[dict] = []

	for line in manifest.items:
		if not line.item_code:
			continue
		if not cint(line.include_in_qr_labels if line.include_in_qr_labels is not None else 1):
			continue

		qty = max(cint(flt(line.qty or 1)), 1)
		for _ in range(qty):
			counters[line.item_code] = counters.get(line.item_code, 0) + 1
			sequence = counters[line.item_code]
			item_instance_code = f"{project}-{slug_item_code(line.item_code)}-{sequence:04d}"
			rows.append(
				{
					"item_instance_code": item_instance_code,
					"item_code": line.item_code,
					"room": line.room,
					"sequence": sequence,
					"manifest": manifest_name,
				}
			)

	item_names = _item_name_map({row["item_code"] for row in rows})
	for row in rows:
		row["item_name"] = item_names.get(row["item_code"]) or row["item_code"]

	return rows


@frappe.whitelist()
def get_project_qr_label_data(project: str) -> dict:
	"""Return manifest item instances and QR previews for the Download QR tab."""
	frappe.has_permission("Project", "read", project, throw=True)

	manifest_name = frappe.db.get_value("Project", project, "fk_effective_manifest")
	rows = expand_manifest_item_instances(project, manifest_name)

	for row in rows:
		png = generate_qr_png_bytes(row["item_instance_code"])
		row["qr_base64"] = base64.b64encode(png).decode("ascii")

	return {
		"project": project,
		"manifest": manifest_name,
		"count": len(rows),
		"rows": rows,
	}


@frappe.whitelist()
def download_project_qr_zip(project: str):
	"""Download a ZIP of QR PNG files for all manifest item instances on this project."""
	frappe.has_permission("Project", "read", project, throw=True)

	rows = expand_manifest_item_instances(project)
	if not rows:
		frappe.throw(
			_("No QR labels to download. Set Effective Manifest on the Unit tab and ensure manifest items are included in QR labels.")
		)

	buffer = BytesIO()
	with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
		for row in rows:
			code = row["item_instance_code"]
			png = generate_qr_png_bytes(code)
			archive.writestr(f"{code}.png", png)

	frappe.local.response.filename = f"{project}-qr-labels.zip"
	frappe.local.response.filecontent = buffer.getvalue()
	frappe.local.response.type = "download"
