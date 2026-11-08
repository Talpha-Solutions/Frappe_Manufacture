from frappe import _


def get_data():
	return {
		"fieldname": "template",
		"non_standard_fieldnames": {"Pre Production Manifest Template": "based_on"},
		"transactions": [
			{"label": _("Customer Templates"), "items": ["Pre Production Manifest Template"]},
			{"label": _("Used On"), "items": ["Pre Production Plan", "Pre Production Manifest"]},
		],
	}
