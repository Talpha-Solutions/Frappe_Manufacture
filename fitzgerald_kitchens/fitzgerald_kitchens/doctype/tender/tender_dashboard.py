from frappe import _


def get_data():
	return {
		"fieldname": "tender",
		"non_standard_fieldnames": {"Project": "fk_tender"},
		"transactions": [
			{"label": _("Tender Manifests"), "items": ["Tender Manifest"]},
			{"label": _("Projects"), "items": ["Project"]},
		],
	}
