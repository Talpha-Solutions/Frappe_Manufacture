from frappe import _


def get_data():
	return {
		"fieldname": "pre_production_plan",
		"non_standard_fieldnames": {"Project": "fk_pre_production_plan"},
		"transactions": [
			{"label": _("Pre Production Manifests"), "items": ["Pre Production Manifest"]},
			{"label": _("Projects"), "items": ["Project"]},
		],
	}
