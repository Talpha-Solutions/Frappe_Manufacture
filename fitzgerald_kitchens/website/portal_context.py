# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe

# First URL segment for ERPNext portal templates (detail / utility pages).
_PORTAL_TEMPLATE_PREFIXES = frozenset(
	{
		"order",
		"rfq",
		"material_request_info",
		"portal",
		"tasks",
		"projects",
		"timelog_info",
		"task_info",
		"addresses",
	}
)

# Pages that must not get the portal sidebar even for portal users.
_EXCLUDED_PATHS = frozenset({"me", "login", "update-password", "signup", "logout"})


def update_website_context(context):
	"""Keep the portal sidebar visible on all customer/supplier portal routes."""
	if frappe.session.user == "Guest":
		return

	if context.get("show_sidebar") is False:
		return

	if not _has_portal_menu():
		return

	path = _normalized_path(context)
	if not path or path in _EXCLUDED_PATHS:
		return

	if not _is_portal_path(path):
		return

	return {"show_sidebar": True}


def _has_portal_menu():
	from frappe.website.utils import get_portal_sidebar_items

	return bool(get_portal_sidebar_items())


def _normalized_path(context):
	path = context.pathname or context.path or ""
	return path.strip("/").lower()


def _is_portal_path(path):
	for route in _portal_routes():
		if path == route or path.startswith(f"{route}/"):
			return True

	first_segment = path.split("/", 1)[0]
	return first_segment in _PORTAL_TEMPLATE_PREFIXES


def _portal_routes():
	routes = set()
	for item in frappe.get_hooks("portal_menu_items") or []:
		route = (item.get("route") or "").strip("/").lower()
		if route:
			routes.add(route)
	return routes
