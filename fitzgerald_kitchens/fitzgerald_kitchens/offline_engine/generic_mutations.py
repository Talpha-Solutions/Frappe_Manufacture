# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

"""Generic DocType insert/save mutators for Offline Sync Settings–selected DocTypes."""

from __future__ import annotations

import frappe

from fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.settings import SIMPLE_FIELDTYPES, assert_doctype_allowed
from fitzgerald_kitchens.fitzgerald_kitchens.offline_engine.validation import assert_not_stale


def _clean_doc_dict(doctype: str, doc: dict, *, for_insert: bool) -> dict:
	"""Keep only simple parent fields (+ name/doctype). Child tables ignored in v1 writes."""
	if isinstance(doc, str):
		doc = frappe.parse_json(doc)
	doc = dict(doc or {})

	meta = frappe.get_meta(doctype)
	allowed = {df.fieldname for df in meta.fields if df.fieldtype in SIMPLE_FIELDTYPES}
	# Always allow identity fields
	allowed.update({"name", "doctype", "owner", "creation", "modified", "modified_by", "docstatus"})

	cleaned = {"doctype": doctype}
	for key, value in doc.items():
		if key in allowed:
			cleaned[key] = value

	if for_insert:
		cleaned.pop("name", None)
		cleaned.pop("creation", None)
		cleaned.pop("modified", None)
		cleaned.pop("modified_by", None)
		cleaned.pop("owner", None)
		cleaned["docstatus"] = 0
	else:
		# Never change docstatus via generic offline save in v1
		cleaned.pop("docstatus", None)

	return cleaned


@frappe.whitelist()
def insert_doc(doctype: str, doc=None, **_kwargs):
	"""Create a new document for a settings-enabled DocType.

	Extra kwargs (e.g. client-only `_local_id`) are ignored.
	"""
	assert_doctype_allowed(doctype, "create")
	if not frappe.has_permission(doctype, "create"):
		frappe.throw(frappe._("Not permitted to create {0}").format(doctype), frappe.PermissionError)

	payload = _clean_doc_dict(doctype, doc or {}, for_insert=True)
	new_doc = frappe.get_doc(payload)
	new_doc.insert()

	return {
		"doctype": new_doc.doctype,
		"name": new_doc.name,
		"modified": str(new_doc.modified),
		"doc": new_doc.as_dict(no_nulls=False),
	}


@frappe.whitelist()
def save_doc(doctype: str, name: str, doc=None, based_on_modified=None, **_kwargs):
	"""Update an existing document with compare-and-swap on modified.

	Extra client-only kwargs are ignored.
	"""
	assert_doctype_allowed(doctype, "write")
	if not frappe.has_permission(doctype, "write", doc=name):
		frappe.throw(
			frappe._("Not permitted to write {0} {1}").format(doctype, name),
			frappe.PermissionError,
		)

	existing = frappe.get_doc(doctype, name)
	assert_not_stale(existing, based_on_modified)

	payload = _clean_doc_dict(doctype, doc or {}, for_insert=False)
	meta = frappe.get_meta(doctype)
	for df in meta.fields:
		if df.fieldtype not in SIMPLE_FIELDTYPES:
			continue
		if df.fieldname not in payload:
			continue
		if df.read_only or df.fieldtype == "Read Only":
			continue
		existing.set(df.fieldname, payload[df.fieldname])

	existing.save()

	return {
		"doctype": existing.doctype,
		"name": existing.name,
		"modified": str(existing.modified),
		"doc": existing.as_dict(no_nulls=False),
	}
