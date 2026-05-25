# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from fitzgerald_kitchens.setup.project_bom_fields import ensure_project_bom_fields


def execute():
	from fitzgerald_kitchens.setup.project_bom_fields import cleanup_obsolete_bom_fields

	cleanup_obsolete_bom_fields()
	ensure_project_bom_fields()
