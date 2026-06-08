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
	"""Return {company: default_capacity_pipeline_bom} for boot filter defaults."""
	from fitzgerald_kitchens.fitzgerald_kitchens.report.capacity_pipeline_report.capacity_pipeline_report import (
		get_default_bom,
	)

	companies = frappe.get_all(
		"BOM",
		filters={"docstatus": 1, "is_active": 1},
		pluck="company",
		distinct=True,
	)
	return {company: get_default_bom(company) for company in companies if company}
