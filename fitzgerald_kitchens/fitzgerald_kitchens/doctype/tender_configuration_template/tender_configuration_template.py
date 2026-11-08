# Copyright (c) 2026, talpha solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


# who a tender, or a template made for one, can be for: a Lead until we've won work from them,
# then a Customer
PARTY_TYPES = ("Lead", "Customer")


class TenderConfigurationTemplate(Document):
	def validate(self):
		self._validate_party()

	def _validate_party(self):
		# a base template is for everyone; a party's template is a copy of one
		if self.is_template:
			self.party_type = self.party_name = self.party_title = None
		validate_party_type(self.party_type)
		self.party_title = party_title(self.party_type, self.party_name)
		if self.based_on == self.name:
			self.based_on = None


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
	party = frappe.db.get_value("Pre Production Plan", tender, ["party_type", "party_name"], as_dict=True)
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
	"""Copy a base template for a Lead or Customer (its rows); the copy is theirs to edit."""
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
