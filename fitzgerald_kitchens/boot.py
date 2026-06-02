# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe


def boot_session(bootinfo):
	"""Expose latest BOM per company for Capacity Pipeline Report filter defaults."""
	if frappe.session.user == "Guest":
		return

	bootinfo.capacity_pipeline_default_boms = _get_latest_boms_by_company()
	company = frappe.defaults.get_user_default("Company")
	if company:
		bootinfo.capacity_pipeline_default_bom = bootinfo.capacity_pipeline_default_boms.get(
			company
		)


def _get_latest_boms_by_company():
	"""Return {company: latest_active_bom_name} ordered by creation desc."""
	rows = frappe.db.sql(
		"""
		SELECT company, name
		FROM `tabBOM`
		WHERE docstatus = 1 AND is_active = 1
		ORDER BY company, creation DESC
		""",
		as_dict=True,
	)

	latest = {}
	for row in rows:
		if row.company not in latest:
			latest[row.company] = row.name

	return latest
