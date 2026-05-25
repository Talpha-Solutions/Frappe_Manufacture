# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

from fitzgerald_kitchens.setup.project_bom_fields import (
	ensure_project_bom_fields,
	remove_work_order_button_fields,
)


def execute():
	remove_work_order_button_fields()
	ensure_project_bom_fields()
