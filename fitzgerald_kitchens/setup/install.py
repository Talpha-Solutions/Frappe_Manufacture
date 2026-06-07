import frappe

from fitzgerald_kitchens.setup.development_stages import (
	STANDARD_DEVELOPMENT_STAGES,
	STANDARD_STAGES_BY_NAME,
	normalize_evidence_required,
)


def ensure_capacity_pipeline_report_module():
	"""Script reports must use the app module so Python resolves correctly."""
	if not frappe.db.exists("Report", "Capacity Pipeline Report"):
		return
	frappe.db.set_value(
		"Report",
		"Capacity Pipeline Report",
		"module",
		"fitzgerald_kitchens",
		update_modified=False,
	)


def after_install():
	ensure_capacity_pipeline_report_module()
	from fitzgerald_kitchens.setup.project_bom_fields import remove_project_bom_fields
	from fitzgerald_kitchens.setup.project_unit_fields import ensure_project_unit_fields
	from fitzgerald_kitchens.setup.project_bom_fields import ensure_project_bom_fields
	from fitzgerald_kitchens.setup.production_plan_fields import ensure_production_plan_fields
	from fitzgerald_kitchens.setup.project_website_list import (
		patch_project_website_list,
		patch_project_website_tasks,
	)
	from fitzgerald_kitchens.setup.my_tasks_desk import ensure_my_tasks_desk
	from fitzgerald_kitchens.setup.workspace_sidebar import (
		ensure_manufacturing_sidebar,
		ensure_projects_sidebar,
	)

	ensure_development_stage_settings()
	from fitzgerald_kitchens.setup.project_form_layout import reset_project_form_layout

	reset_project_form_layout()
	from fitzgerald_kitchens.setup.project_naming import (
		ensure_project_naming_series_options,
		ensure_unit_series_counters,
	)

	ensure_project_naming_series_options()
	ensure_unit_series_counters()
	ensure_project_types()
	ensure_project_bom_fields()
	ensure_production_plan_fields()
	ensure_projects_sidebar()
	ensure_manufacturing_sidebar()
	ensure_my_tasks_desk()
	patch_project_website_list()
	patch_project_website_tasks()


def ensure_project_types():
	from fitzgerald_kitchens.setup.project_types import ensure_project_types as _ensure

	_ensure()


def ensure_development_stage_settings():
	from fitzgerald_kitchens.fitzgerald_kitchens.doctype.development_stage_settings.development_stage_settings import (
		sync_stages_to_master,
	)

	doc = frappe.get_single("Development Stage Settings")

	if not doc.stages:
		for stage in STANDARD_DEVELOPMENT_STAGES:
			doc.append("stages", stage)
		doc.save(ignore_permissions=True)
		return

	existing_names = set()
	updated = False

	for row in doc.stages:
		if not row.stage_name:
			continue

		existing_names.add(row.stage_name)

		if row.stage_name in STANDARD_STAGES_BY_NAME:
			standard = STANDARD_STAGES_BY_NAME[row.stage_name]
			for field, value in standard.items():
				if row.get(field) != value:
					row.set(field, value)
					updated = True
		else:
			normalized = normalize_evidence_required(row.evidence_required)
			if row.evidence_required != normalized:
				row.evidence_required = normalized
				updated = True

	for stage in STANDARD_DEVELOPMENT_STAGES:
		if stage["stage_name"] not in existing_names:
			doc.append("stages", stage)
			updated = True

	if updated:
		doc.save(ignore_permissions=True)
	else:
		sync_stages_to_master(doc)
