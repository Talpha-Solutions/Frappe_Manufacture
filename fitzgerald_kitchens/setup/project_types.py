STANDARD_PROJECT_TYPES = [
	{"project_type": "Site"},
	{"project_type": "Kitchen"},
	{"project_type": "Robe"},
	{"project_type": "Utility"},
	{"project_type": "Vanity Unit"},
	{"project_type": "Unit"},
	{"project_type": "Pantry"},
]

STANDARD_PROJECT_TYPE_NAMES = {row["project_type"] for row in STANDARD_PROJECT_TYPES}


def ensure_project_types():
	import frappe

	for row in STANDARD_PROJECT_TYPES:
		name = row["project_type"]
		if frappe.db.exists("Project Type", name):
			continue

		frappe.get_doc(
			{
				"doctype": "Project Type",
				"project_type": name,
				"description": row.get("description", ""),
			}
		).insert(ignore_permissions=True)
