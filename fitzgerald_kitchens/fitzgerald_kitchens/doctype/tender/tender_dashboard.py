from frappe import _


def get_data():
	return {
		"fieldname": "tender",
		"transactions": [
			{"label": _("Tender Manifests"), "items": ["Tender Manifest"]},
		],
	}
