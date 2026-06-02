# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from fitzgerald_kitchens.setup.project_bom_fields import remove_project_bom_fields
from fitzgerald_kitchens.setup.project_unit_fields import ensure_project_unit_fields


def execute():
	remove_project_bom_fields()
	ensure_project_unit_fields()
