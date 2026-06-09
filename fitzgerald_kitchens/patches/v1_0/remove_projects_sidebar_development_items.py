import frappe

from fitzgerald_kitchens.setup.workspace_sidebar import ensure_projects_sidebar


def execute():
	"""Remove Development Unit and QR Stage Scan from Projects workspace sidebar."""
	ensure_projects_sidebar()
