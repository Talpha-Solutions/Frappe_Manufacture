# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from fitzgerald_kitchens.setup.project_unit_fields import ensure_project_unit_fields


def execute():
	ensure_project_unit_fields()  # idempotent: parent unit rules, project type tab
