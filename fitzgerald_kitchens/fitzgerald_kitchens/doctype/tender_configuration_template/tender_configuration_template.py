# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

STANDARD_SELLING_PRICE_LIST = "Standard Selling"

# who a tender, or a template made for one, can be for: a Lead until we've won work from them,
# then a Customer
PARTY_TYPES = ("Lead", "Customer")


class TenderConfigurationTemplate(Document):
	def validate(self):
		self._validate_cabinet_price_rows()
		self._validate_party()

	def _validate_party(self):
		# a base template is for everyone; a party's template is a copy of one
		if self.is_template:
			self.party_type = self.party_name = self.party_title = None
		validate_party_type(self.party_type)
		self.party_title = party_title(self.party_type, self.party_name)
		if self.based_on == self.name:
			self.based_on = None

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


def validate_party_type(party_type: str | None):
	if party_type and party_type not in PARTY_TYPES:
		frappe.throw(_("Party Type must be one of {0}").format(", ".join(PARTY_TYPES)))


def party_title(party_type: str | None, party_name: str | None) -> str | None:
	"""A party's readable name: the Customer's name, or the Lead's company (else the person)."""
	if not party_type or not party_name:
		return None
	if party_type == "Customer":
		return frappe.db.get_value("Customer", party_name, "customer_name") or party_name
	lead = frappe.db.get_value("Lead", party_name, ["company_name", "lead_name"], as_dict=True) or {}
	return lead.get("company_name") or lead.get("lead_name") or party_name


def tender_party(tender: str | None) -> tuple[str | None, str | None]:
	"""(party type, party) a tender is for, or (None, None)."""
	if not tender:
		return None, None
	party = frappe.db.get_value("Tender", tender, ["party_type", "party_name"], as_dict=True)
	return (party.party_type, party.party_name) if party and party.party_name else (None, None)


def validate_template_party(template: str | None, party_type: str | None, party_name: str | None):
	"""A party's template can only be used on that party's tenders."""
	if not template:
		return
	owner = frappe.db.get_value("Tender Configuration Template", template, ["party_type", "party_name"], as_dict=True)
	if owner and owner.party_name and (owner.party_type, owner.party_name) != (party_type, party_name):
		frappe.throw(
			_("Template {0} is for {1} {2}; this tender isn't.").format(
				frappe.bold(template), _(owner.party_type), frappe.bold(party_title(owner.party_type, owner.party_name))
			)
		)


@frappe.whitelist()
def create_party_template(
	template: str, party_type: str, party_name: str, template_name: str | None = None
) -> str:
	"""Copy a base template for a Lead or Customer (rows and cabinet prices); the copy is theirs to edit."""
	source = frappe.get_doc("Tender Configuration Template", template)
	source.check_permission("read")
	if not source.is_template:
		frappe.throw(_("{0} isn't a base template (Is Template).").format(source.name))
	validate_party_type(party_type)
	if not frappe.db.exists(party_type, party_name):
		frappe.throw(_("{0} {1} not found.").format(_(party_type), party_name))

	copy = frappe.copy_doc(source)
	copy.template_name = (template_name or "").strip() or f"{source.template_name} - {party_title(party_type, party_name)}"
	copy.is_template = 0
	copy.party_type = party_type
	copy.party_name = party_name
	copy.based_on = source.name
	copy.insert()
	return copy.name


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def template_query(doctype, txt, searchfield, start, page_len, filters):
	"""Template link search: a party with templates of their own sees only those; anyone else (a
	party without one, no tender) sees the templates for everyone.

	filters: party_type and party_name, or tender (a manifest passes its tender and the party is
	looked up).
	"""
	filters = filters or {}
	party_type, party_name = filters.get("party_type"), filters.get("party_name")
	if not party_name:
		party_type, party_name = tender_party(filters.get("tender"))
	own = bool(party_name) and frappe.db.exists(
		"Tender Configuration Template", {"party_type": party_type, "party_name": party_name}
	)
	return frappe.db.sql(
		f"""
		select name, if(is_template, 'Template', ifnull(party_title, '')) as description
		from `tabTender Configuration Template`
		where {"party_type = %(party_type)s and party_name = %(party_name)s" if own else "ifnull(party_name, '') = ''"}
		  and name like %(txt)s
		order by is_template desc, name
		limit %(page_len)s offset %(start)s
		""",
		{"party_type": party_type, "party_name": party_name, "txt": f"%{txt or ''}%", "start": start, "page_len": page_len},
	)


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
