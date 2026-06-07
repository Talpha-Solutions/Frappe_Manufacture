import frappe

from fitzgerald_kitchens.setup.projects_settings_fields import ensure_projects_settings_fields
from fitzgerald_kitchens.setup.workspace_sidebar import ensure_projects_sidebar


def execute():
	ensure_projects_settings_fields()
	ensure_projects_sidebar()
