import frappe

from fitzgerald_kitchens.setup.workspace_sidebar import ensure_manufacturing_sidebar


def execute():
	"""Remove sidebar icon so Capacity Pipeline Report aligns with other report links."""
	ensure_manufacturing_sidebar()
