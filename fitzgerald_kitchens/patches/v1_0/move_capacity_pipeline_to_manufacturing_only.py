import frappe

from fitzgerald_kitchens.setup.workspace_sidebar import ensure_manufacturing_sidebar, ensure_projects_sidebar


def execute():
	"""Keep Capacity Pipeline Report under Manufacturing sidebar only."""
	ensure_projects_sidebar()
	ensure_manufacturing_sidebar()
