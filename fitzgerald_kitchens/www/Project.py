import frappe
from frappe import _

from fitzgerald_kitchens.fitzgerald_kitchens.website.production_tracker import get_tracker_context


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.throw(_("You need to be logged in to view projects."), frappe.PermissionError)

	context.no_cache = 1
	context.show_sidebar = True

	tracker = get_tracker_context()
	context.update(tracker)
	context.title = tracker.get("page_title") or _("Projects")
