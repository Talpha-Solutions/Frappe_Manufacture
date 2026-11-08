import frappe

STATES = ("Draft", "In Progress", "Submitted", "Won", "Lost", "Cancelled")
ACTIONS = ("Start Pricing", "Submit to Client", "Revise", "Mark Won", "Mark Lost", "Reopen", "Cancel")


def execute():
	"""Pre Production Plans no longer have a workflow or a Status.

	Deletes the Tender Workflow, the workflow actions waiting on plans, its workflow states and actions
	(only those no other workflow uses), and Customize Form changes on the removed Status field. The
	status column stays in the table (Frappe doesn't drop columns), so the old values aren't lost.
	"""
	frappe.db.delete("Workflow Action", {"reference_doctype": "Pre Production Plan"})
	if frappe.db.exists("Workflow", "Tender Workflow"):
		frappe.delete_doc("Workflow", "Tender Workflow", force=True, ignore_permissions=True)

	used_states = set(frappe.get_all("Workflow Document State", pluck="state")) | set(
		frappe.get_all("Workflow Transition", pluck="state") + frappe.get_all("Workflow Transition", pluck="next_state")
	)
	used_actions = set(frappe.get_all("Workflow Transition", pluck="action"))
	for state in STATES:
		if state not in used_states and frappe.db.exists("Workflow State", state):
			frappe.delete_doc("Workflow State", state, force=True, ignore_permissions=True)
	for action in ACTIONS:
		if action not in used_actions and frappe.db.exists("Workflow Action Master", action):
			frappe.delete_doc("Workflow Action Master", action, force=True, ignore_permissions=True)

	frappe.db.delete("Property Setter", {"doc_type": "Pre Production Plan", "field_name": "status"})
