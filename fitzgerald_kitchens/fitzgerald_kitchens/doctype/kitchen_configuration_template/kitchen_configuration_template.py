# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

STANDARD_SELLING_PRICE_LIST = "Standard Selling"


class KitchenConfigurationTemplate(Document):
	def validate(self):
		self._validate_cabinet_price_rows()

		if not self.is_default:
			return

		frappe.db.sql(
			"""
			update `tabKitchen Configuration Template`
			set is_default = 0
			where name != %s and is_default = 1
			""",
			self.name,
		)

	def _validate_cabinet_price_rows(self):
		required_price_rows = {
			"Base Units": self.base_units_price_row,
			"Wall Units": self.wall_units_price_row,
			"Tall Units": self.tall_units_price_row,
			"Drawer Packs": self.drawer_packs_price_row,
		}
		for label, price_row in required_price_rows.items():
			if not price_row:
				frappe.throw(_("{0} Price is required.").format(label))


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_item_price_list(doctype, txt, searchfield, start, page_len, filters):
	"""Link query: one row per Item Price (same item can appear multiple times)."""
	return frappe.db.sql(
		_get_item_price_link_query(),
		{
			"txt": f"%{txt or ''}%",
			"start": start,
			"page_len": page_len,
			"price_list": STANDARD_SELLING_PRICE_LIST,
		},
	)


@frappe.whitelist()
def get_all_item_price_options():
	rows = frappe.db.sql(
		_get_item_price_select_sql()
		+ _get_item_price_from_sql()
		+ _get_item_price_order_sql(),
		{"price_list": STANDARD_SELLING_PRICE_LIST},
		as_dict=True,
	)
	return [
		{
			"price_row": row.name,
			"item_code": row.item_code,
			"item_name": row.item_name,
			"price_list": row.price_list,
			"rate": flt(row.price_list_rate),
			"currency": row.currency,
			"uom": row.uom,
			"label": row.description,
		}
		for row in rows
	]


def _get_item_price_select_sql() -> str:
	return """
		select
			ip.name,
			i.name as item_code,
			i.item_name,
			ip.price_list,
			ip.price_list_rate,
			ip.currency,
			ip.uom,
			i.item_group,
			concat(
				ifnull(i.item_name, ip.item_code),
				' (',
				ifnull(i.item_group, ''),
				') - ',
				ifnull(ip.currency, ''),
				' ',
				round(ip.price_list_rate, 2),
				case when ifnull(ip.uom, '') != '' then concat('/', ip.uom) else '' end,
				case when ifnull(ip.price_list, '') != '' then concat(' [', ip.price_list, ']') else '' end
			) as description
	"""


def _get_item_price_from_sql() -> str:
	return """
		from `tabItem Price` ip
		inner join `tabItem` i on i.name = ip.item_code
		where i.disabled = 0
		  and ip.price_list = %(price_list)s
	"""


def _get_item_price_search_sql() -> str:
	return """
		  and (
			ip.name like %(txt)s
			or i.item_name like %(txt)s
			or i.name like %(txt)s
			or ifnull(ip.price_list, '') like %(txt)s
		  )
	"""


def _get_item_price_order_sql() -> str:
	return """
		order by i.item_name asc, ip.price_list asc, ip.price_list_rate asc
	"""


def _get_item_price_list_query() -> str:
	return (
		_get_item_price_select_sql()
		+ _get_item_price_from_sql()
		+ _get_item_price_search_sql()
		+ _get_item_price_order_sql()
		+ " limit %(page_len)s offset %(start)s"
	)


def _get_item_price_link_query() -> str:
	# For Link field search: return only value and label columns so each
	# Item Price appears as a single clean option in the dropdown.
	return (
		"""
		select
			ip.name,
			concat(
				ifnull(i.item_name, ip.item_code),
				' (',
				ifnull(i.item_group, ''),
				') - ',
				ifnull(ip.currency, ''),
				' ',
				round(ip.price_list_rate, 2),
				case when ifnull(ip.uom, '') != '' then concat('/', ip.uom) else '' end,
				case when ifnull(ip.price_list, '') != '' then concat(' [', ip.price_list, ']') else '' end
			) as description
	"""
		+ _get_item_price_from_sql()
		+ _get_item_price_search_sql()
		+ _get_item_price_order_sql()
		+ " limit %(page_len)s offset %(start)s"
	)
