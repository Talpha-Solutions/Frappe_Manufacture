# Copyright (c) 2024, Talpha Solutions and contributors
# BOM Cost Calculator - cost estimation with routing folders and default BOM auto-load.

import frappe
from frappe import _, bold
from frappe.model.document import Document
from frappe.utils import cint, flt, sbool
from pypika.terms import ValueWrapper

from erpnext.manufacturing.doctype.bom.bom import get_bom_item_rate

ROUTING_PREFIX = "__routing__:"
RAW_MATERIALS_PREFIX = "__raw_materials__:"
OPERATION_SUFFIX = "__op__"

ITEM_FIELDS = [
	"item_code as value",
	"item_name as title",
	"is_expandable as expandable",
	"parent as parent_id",
	"fg_item",
	"qty",
	"idx",
	ValueWrapper("BOM Cost Calculator Item").as_("doctype"),
	"name",
	"uom",
	"rate",
	"amount",
	"operation",
	"routing",
	"is_subcontracted",
]


class BOMCostCalculator(Document):
	def before_save(self):
		self.status = "Draft"
		self.set_is_expandable()
		self.set_conversion_factor()
		self.set_reference_id()
		self.set_rate_for_items()

	def validate(self):
		self.validate_items()
		self.validate_duplicate_item()

	def validate_duplicate_item(self):
		item_map = {}
		for row in self.items:
			if not row.fg_reference_id:
				continue

			key = (row.item_code, row.fg_item, row.fg_reference_id)
			if key in item_map:
				parent_item_code = self._get_parent_item_code(row.fg_reference_id)
				frappe.throw(
					_(
						"Item {0} added multiple times under the same parent item {1} at rows {2} and {3}"
					).format(bold(row.item_code), bold(parent_item_code), item_map[key], row.idx),
					title=_("Duplicate Item Under Same Parent"),
				)
			item_map[key] = row.idx

	def _get_parent_item_code(self, fg_reference_id):
		if fg_reference_id == self.name:
			return self.item_code

		parent_row = next((item for item in self.items if item.name == fg_reference_id), None)
		return parent_row.item_code if parent_row else fg_reference_id

	def validate_items(self):
		for row in self.items:
			if row.is_expandable and row.item_code == self.item_code:
				frappe.throw(_("Item {0} cannot be added as a sub-assembly of itself").format(row.item_code))

			if not row.parent_row_no and row.fg_item and row.fg_item != self.item_code:
				frappe.throw(
					_("At row {0}: set Parent Row No for item {1}").format(row.idx, row.item_code),
					title=_("Set Parent Row No in Items Table"),
				)
			elif row.parent_row_no and row.fg_item == self.item_code:
				frappe.throw(
					_("At row {0}: Parent Row No cannot be set for item {1}").format(row.idx, row.item_code),
					title=_("Remove Parent Row No in Items Table"),
				)

	def set_reference_id(self):
		parent_reference = {row.idx: row.name for row in self.items}

		for row in self.items:
			ref_id = ""
			if row.parent_row_no:
				ref_id = parent_reference.get(cint(row.parent_row_no))

			if row.fg_reference_id and row.fg_reference_id == ref_id:
				continue

			if row.parent_row_no:
				row.fg_reference_id = ref_id
			elif row.fg_item == self.item_code:
				row.fg_reference_id = self.name

	def set_rate_for_items(self):
		breakdown = self.get_cost_breakdown()
		self.raw_materials_total = breakdown["raw_materials_total"]
		self.routing_cost_total = breakdown["routing_cost_total"]
		self.other_charges_total = breakdown["other_charges_total"]
		self.raw_material_cost = breakdown["bom_cost"]
		self.total_cost = breakdown["total_cost"]

	def get_cost_breakdown(self):
		raw_materials_total = sum(flt(row.amount) for row in self.items if not row.is_expandable)
		routing_cost_total = _get_routing_cost_total(self)
		other_charges_total = sum(flt(row.amount) for row in self.other_charges or [])
		bom_cost = self.get_total_cost(self.item_code, self.name)

		return {
			"raw_materials_total": raw_materials_total,
			"routing_cost_total": routing_cost_total,
			"other_charges_total": other_charges_total,
			"bom_cost": bom_cost,
			"total_cost": flt(bom_cost) + flt(other_charges_total),
		}

	def get_total_cost(self, fg_item=None, fg_reference_id=None, _visited=None):
		if not fg_item:
			fg_item = self.item_code
		if fg_reference_id is None and fg_item == self.item_code:
			fg_reference_id = self.name

		if _visited is None:
			_visited = set()

		visit_key = (fg_item, fg_reference_id)
		if visit_key in _visited:
			frappe.throw(
				_("Circular sub-assembly reference detected for item {0}").format(bold(fg_item)),
				title=_("Circular BOM Reference"),
			)
		_visited.add(visit_key)

		assembly_row = self._get_assembly_row(fg_reference_id)
		amount = 0
		for row in self.items:
			if row.fg_item != fg_item:
				continue

			if not self._is_row_under_assembly(row, assembly_row):
				continue

			if row.is_expandable:
				row.rate = flt(
					self.get_total_cost(row.item_code, row.name, _visited) * row.conversion_factor
				)
			else:
				row.rate = get_bom_item_rate(
					{
						"company": self.company,
						"item_code": row.item_code,
						"bom_no": "",
						"qty": row.qty,
						"uom": row.uom,
						"stock_uom": row.stock_uom,
						"conversion_factor": row.conversion_factor,
						"sourced_by_supplier": row.sourced_by_supplier,
					},
					self,
				)

			row.amount = flt(row.rate) * flt(row.qty)
			amount += flt(row.amount)

		if assembly_row and assembly_row.routing:
			amount += _get_routing_operation_cost(assembly_row.routing)
		elif not assembly_row and self.routing and not _has_assembly_routing(self, fg_item, assembly_row):
			amount += _get_routing_operation_cost(self.routing)

		return amount

	def _get_assembly_row(self, fg_reference_id):
		if not fg_reference_id or fg_reference_id == self.name:
			return None

		return next((row for row in self.items if row.name == fg_reference_id), None)

	def _is_row_under_assembly(self, row, assembly_row):
		if not assembly_row:
			return not row.parent_row_no

		return cint(row.parent_row_no) == assembly_row.idx

	def get_raw_material_cost(self, fg_item=None):
		return self.get_total_cost(fg_item)

	def set_is_expandable(self):
		for row in self.items:
			row.is_expandable = 1 if self._has_assembly_children(row) else 0

	def _has_assembly_children(self, row):
		if row.routing:
			return True

		return any(
			child.fg_item == row.item_code and cint(child.parent_row_no) == row.idx
			for child in self.items
		)

	def set_conversion_factor(self):
		for row in self.items:
			if not row.conversion_factor:
				row.conversion_factor = 1.0

	@frappe.whitelist()
	def get_default_bom(self, item_code) -> str:
		return frappe.get_cached_value("Item", item_code, "default_bom")


@frappe.whitelist()
def get_default_bom_details(item_code):
	default_bom = frappe.get_cached_value("Item", item_code, "default_bom")
	if not default_bom:
		return {"items": [], "routing": None, "operations": [], "bom_no": None}

	bom = frappe.get_doc("BOM", default_bom)
	items = [
		{
			"item_code": row.item_code,
			"item_name": row.item_name or frappe.get_cached_value("Item", row.item_code, "item_name"),
			"qty": row.qty,
		}
		for row in bom.items
		if row.item_code
	]

	routing = bom.routing
	operations = []

	if routing:
		operations = _get_routing_operations(routing)
	elif bom.get("operations"):
		for row in bom.operations:
			operations.append(
				{
					"operation": row.operation,
					"time_in_mins": flt(row.time_in_mins),
					"operating_cost": flt(row.operating_cost),
				}
			)

	return {
		"items": items,
		"routing": routing,
		"operations": operations,
		"bom_no": default_bom,
	}


@frappe.whitelist()
def get_children(doctype=None, parent=None, **kwargs):
	if isinstance(kwargs, str):
		kwargs = frappe.parse_json(kwargs)
	if isinstance(kwargs, dict):
		kwargs = frappe._dict(kwargs)

	if parent and str(parent).startswith(ROUTING_PREFIX):
		return _get_routing_folder_children(parent, kwargs)

	if parent and str(parent).startswith(RAW_MATERIALS_PREFIX):
		return _get_raw_materials_folder_children(parent, kwargs)

	children = _get_item_children(parent, kwargs)
	assembly_row_name = kwargs.get("assembly_row_name") or _resolve_assembly_row_name(parent, kwargs)

	if assembly_row_name:
		routing = frappe.db.get_value("BOM Cost Calculator Item", assembly_row_name, "routing")
		if routing:
			children = [
				_make_routing_node(routing, assembly_row_name, kwargs),
				_make_raw_materials_node(assembly_row_name, kwargs),
				*children,
			]

	return children


def _resolve_assembly_row_name(parent, kwargs):
	if not parent or str(parent).startswith(ROUTING_PREFIX):
		return None

	rows = frappe.get_all(
		"BOM Cost Calculator Item",
		filters={
			"parent": kwargs.parent_id,
			"item_code": parent,
		},
		fields=["name", "routing"],
	)
	rows = [row for row in rows if row.routing]
	if len(rows) == 1:
		return rows[0].name

	return None


def _make_routing_node(routing, assembly_row_name, kwargs):
	total_cost = _get_routing_folder_total(routing, assembly_row_name, kwargs.get("parent_id"))
	return frappe._dict(
		{
			"value": f"{ROUTING_PREFIX}{routing}:{assembly_row_name}",
			"title": routing,
			"expandable": 1,
			"doctype": "BOM Cost Calculator Item",
			"name": f"{ROUTING_PREFIX}{routing}:{assembly_row_name}",
			"parent_id": kwargs.get("parent_id"),
			"qty": 0,
			"uom": "",
			"amount": total_cost,
			"rate": total_cost,
			"is_routing_node": 1,
			"routing_name": routing,
			"assembly_row_name": assembly_row_name,
			"idx": 0,
			"operation": "",
			"is_subcontracted": 0,
		}
	)


def _make_raw_materials_node(assembly_row_name, kwargs):
	total_cost = _get_raw_materials_folder_total(assembly_row_name, kwargs.get("parent_id"))
	return frappe._dict(
		{
			"value": f"{RAW_MATERIALS_PREFIX}{assembly_row_name}",
			"title": _("Raw Materials"),
			"expandable": 1,
			"doctype": "BOM Cost Calculator Item",
			"name": f"{RAW_MATERIALS_PREFIX}{assembly_row_name}",
			"parent_id": kwargs.get("parent_id"),
			"qty": 0,
			"uom": "",
			"amount": total_cost,
			"rate": total_cost,
			"is_raw_materials_node": 1,
			"assembly_row_name": assembly_row_name,
			"idx": 1,
			"operation": "",
			"is_subcontracted": 0,
		}
	)


def _get_item_children(parent, kwargs):
	query_filters = {
		"fg_item": parent,
		"parent": kwargs.parent_id,
	}
	if kwargs.name:
		query_filters["name"] = kwargs.name

	children = frappe.get_all(
		"BOM Cost Calculator Item",
		fields=ITEM_FIELDS,
		filters=query_filters,
		order_by="idx",
	)

	filtered = []
	for child in children:
		routing = frappe.db.get_value("BOM Cost Calculator Item", child.name, "routing")
		if routing:
			child.expandable = 1

		if routing or child.get("expandable"):
			child.assembly_row_name = child.name
			child.amount = _get_assembly_display_cost(kwargs.parent_id, child.name, child.value)
			child.rate = child.amount

		filtered.append(child)

	# Hide raw materials that belong under a routing folder (parent has routing set).
	routing_assembly_rows = {
		row.name
		for row in frappe.get_all(
			"BOM Cost Calculator Item",
			filters={"parent": kwargs.parent_id},
			fields=["name", "routing"],
		)
		if row.routing
	}

	if routing_assembly_rows:
		filtered = [
			child
			for child in filtered
			if child.get("expandable")
			or not _is_raw_material_under_routing(child, kwargs.parent_id, routing_assembly_rows)
		]

	return filtered


def _is_raw_material_under_routing(child, parent_id, routing_assembly_rows):
	if child.get("expandable"):
		return False

	row = frappe.db.get_value(
		"BOM Cost Calculator Item",
		child.name,
		["parent_row_no", "fg_item"],
		as_dict=True,
	)
	if not row or not row.parent_row_no:
		return False

	assembly_row = frappe.db.get_value(
		"BOM Cost Calculator Item",
		{"parent": parent_id, "idx": row.parent_row_no},
		["name", "item_code", "routing"],
		as_dict=True,
	)
	return bool(assembly_row and assembly_row.routing and assembly_row.name in routing_assembly_rows)


def _get_routing_folder_children(parent_value, kwargs):
	routing_part = parent_value[len(ROUTING_PREFIX) :]
	routing_name, assembly_row_name = (routing_part.split(":", 1) + [""])[:2]

	children = []
	for op in _get_routing_operations(routing_name):
		unique_value = f"{op.get('operation')}{OPERATION_SUFFIX}{routing_name}"
		children.append(
			frappe._dict(
				{
					"value": unique_value,
					"title": op.get("operation"),
					"expandable": 0,
					"doctype": "BOM Cost Calculator Item",
					"name": unique_value,
					"qty": flt(op.get("time_in_mins")),
					"uom": "mins",
					"amount": flt(op.get("operating_cost")),
					"rate": flt(op.get("operating_cost")),
					"is_operation_node": 1,
					"operation_name": op.get("operation"),
					"idx": op.get("sequence_id") or 0,
					"operation": op.get("operation"),
					"is_subcontracted": 0,
				}
			)
		)

	return children


def _get_raw_materials_folder_children(parent_value, kwargs):
	assembly_row_name = parent_value[len(RAW_MATERIALS_PREFIX) :]
	if not assembly_row_name:
		return []

	assembly_row = frappe.get_doc("BOM Cost Calculator Item", assembly_row_name)
	rm_filters = {
		"parent": kwargs.parent_id,
		"fg_item": assembly_row.item_code,
		"parent_row_no": assembly_row.idx,
		"is_expandable": 0,
	}
	return frappe.get_all(
		"BOM Cost Calculator Item", fields=ITEM_FIELDS, filters=rm_filters, order_by="idx"
	)


def _get_routing_operations(routing_name):
	return frappe.get_all(
		"BOM Operation",
		filters={"parent": routing_name},
		fields=["operation", "operating_cost", "time_in_mins", "sequence_id"],
		order_by="sequence_id, idx",
	)


def _get_routing_operation_cost(routing_name):
	result = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(operating_cost), 0) AS total
		FROM `tabBOM Operation`
		WHERE parent = %s
		""",
		routing_name,
		as_dict=True,
	)
	return flt(result[0].total) if result else 0.0


def _iter_unique_assembly_routings(doc):
	seen = set()
	for row in doc.items:
		if row.is_expandable and row.routing and row.routing not in seen:
			seen.add(row.routing)
			yield row.routing


def _has_assembly_routing(doc, fg_item, assembly_row):
	return any(
		row.is_expandable and row.routing
		for row in doc.items
		if row.fg_item == fg_item and doc._is_row_under_assembly(row, assembly_row)
	)


def _get_routing_cost_total(doc):
	assembly_routings = list(_iter_unique_assembly_routings(doc))
	if assembly_routings:
		return sum(_get_routing_operation_cost(routing) for routing in assembly_routings)

	if doc.routing:
		return _get_routing_operation_cost(doc.routing)

	return 0.0


def _get_routing_folder_total(routing_name, assembly_row_name, parent_id):
	return _get_routing_operation_cost(routing_name)


def _get_raw_materials_folder_total(assembly_row_name, parent_id):
	rm_total = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(amount), 0) AS total
		FROM `tabBOM Cost Calculator Item`
		WHERE parent = %s
		  AND parent_row_no = (
			SELECT idx FROM `tabBOM Cost Calculator Item` WHERE name = %s
		  )
		  AND is_expandable = 0
		""",
		(parent_id, assembly_row_name),
		as_dict=True,
	)
	return flt(rm_total[0].total if rm_total else 0)


def _get_assembly_total_cost(parent_id, assembly_row_name, fg_item):
	doc = frappe.get_doc("BOM Cost Calculator", parent_id)
	return doc.get_total_cost(fg_item, assembly_row_name)


def _get_assembly_display_cost(parent_id, assembly_row_name, fg_item):
	doc = frappe.get_doc("BOM Cost Calculator", parent_id)
	row = next((item for item in doc.items if item.name == assembly_row_name), None)
	if row and flt(row.amount):
		return flt(row.amount)

	unit_cost = doc.get_total_cost(fg_item, assembly_row_name)
	return flt(unit_cost) * flt(row.qty or 1) if row else unit_cost


@frappe.whitelist()
def add_item(**kwargs):
	if isinstance(kwargs, str):
		kwargs = frappe.parse_json(kwargs)
	if isinstance(kwargs, dict):
		kwargs = frappe._dict(kwargs)

	doc = frappe.get_doc("BOM Cost Calculator", kwargs.parent)
	fg_item = kwargs.fg_item
	fg_reference_id = resolve_assembly_reference(doc, fg_item, kwargs.fg_reference_id)
	parent_row_no = ""

	if fg_item and str(fg_item).startswith(RAW_MATERIALS_PREFIX):
		assembly_row_name = fg_item[len(RAW_MATERIALS_PREFIX) :]
		if assembly_row_name:
			assembly_row = frappe.get_doc("BOM Cost Calculator Item", assembly_row_name)
			fg_item = assembly_row.item_code
			fg_reference_id = ""
			parent_row_no = assembly_row.idx
	elif fg_item and str(fg_item).startswith(ROUTING_PREFIX):
		routing_part = fg_item[len(ROUTING_PREFIX) :]
		_, assembly_row_name = (routing_part.split(":", 1) + [""])[:2]
		if assembly_row_name:
			assembly_row = frappe.get_doc("BOM Cost Calculator Item", assembly_row_name)
			fg_item = assembly_row.item_code
			fg_reference_id = ""
			parent_row_no = assembly_row.idx
	elif fg_reference_id and doc.name != fg_reference_id:
		parent_row_no = get_parent_row_no(doc, fg_reference_id)

	item_info = get_item_details(kwargs.item_code)
	row_data = {
		"item_code": kwargs.item_code,
		"qty": kwargs.qty,
		"fg_item": fg_item,
		"uom": item_info.stock_uom,
		"stock_uom": item_info.stock_uom,
		"conversion_factor": 1,
		"fg_reference_id": fg_reference_id,
	}
	if parent_row_no:
		row_data["parent_row_no"] = parent_row_no

	doc.append("items", row_data)
	doc.save()
	return doc


@frappe.whitelist()
def add_sub_assembly(**kwargs):
	if isinstance(kwargs, str):
		kwargs = frappe.parse_json(kwargs)
	if isinstance(kwargs, dict):
		kwargs = frappe._dict(kwargs)

	doc = frappe.get_doc("BOM Cost Calculator", kwargs.parent)
	bom_item = frappe.parse_json(kwargs.bom_item)
	routing = bom_item.get("routing") or kwargs.get("routing")
	kwargs.fg_reference_id = resolve_assembly_reference(doc, kwargs.fg_item, kwargs.fg_reference_id)
	name = kwargs.fg_reference_id
	parent_row_no = ""

	if not kwargs.convert_to_sub_assembly:
		item_info = get_item_details(bom_item.item_code)
		parent_row_no = get_parent_row_no(doc, kwargs.fg_reference_id)
		item_row = doc.append(
			"items",
			{
				"item_code": bom_item.item_code,
				"qty": bom_item.qty,
				"uom": item_info.stock_uom,
				"fg_item": kwargs.fg_item,
				"conversion_factor": 1,
				"parent_row_no": parent_row_no,
				"fg_reference_id": name,
				"stock_qty": bom_item.qty,
				"do_not_explode": 1,
				"is_expandable": 1,
				"stock_uom": item_info.stock_uom,
				"routing": routing,
				"is_phantom_item": sbool(kwargs.phantom),
			},
		)
		parent_row_no = item_row.idx
		name = ""
	else:
		if sbool(kwargs.phantom):
			parent_row = next(item for item in doc.items if item.name == kwargs.fg_reference_id)
			parent_row.db_set("is_phantom_item", 1)
		parent_row_no = get_parent_row_no(doc, kwargs.fg_reference_id)
		if routing and kwargs.fg_reference_id:
			frappe.db.set_value("BOM Cost Calculator Item", kwargs.fg_reference_id, "routing", routing)

	for row in bom_item.get("items") or []:
		row = frappe._dict(row)
		if not row.item_code:
			continue
		item_info = get_item_details(row.item_code)
		doc.append(
			"items",
			{
				"item_code": row.item_code,
				"qty": row.qty,
				"fg_item": bom_item.item_code,
				"uom": item_info.stock_uom,
				"fg_reference_id": name,
				"parent_row_no": parent_row_no,
				"conversion_factor": 1,
				"do_not_explode": 1,
				"stock_qty": row.qty,
				"stock_uom": item_info.stock_uom,
			},
		)

	doc.save()
	return doc


def get_item_details(item_code):
	return frappe.get_cached_value(
		"Item", item_code, ["item_name", "description", "image", "stock_uom", "default_bom"], as_dict=1
	)


def resolve_assembly_reference(doc, fg_item, fg_reference_id):
	if fg_reference_id and fg_reference_id != doc.name:
		if str(fg_reference_id).startswith(ROUTING_PREFIX):
			_, assembly_row_name = (str(fg_reference_id)[len(ROUTING_PREFIX) :].split(":", 1) + [""])[:2]
			if assembly_row_name:
				return assembly_row_name
		if str(fg_reference_id).startswith(RAW_MATERIALS_PREFIX):
			assembly_row_name = str(fg_reference_id)[len(RAW_MATERIALS_PREFIX) :]
			if assembly_row_name:
				return assembly_row_name
		return fg_reference_id

	if fg_item == doc.item_code:
		return doc.name

	candidates = [
		row for row in doc.items if row.item_code == fg_item and cint(row.is_expandable)
	]
	if len(candidates) == 1:
		return candidates[0].name

	if len(candidates) > 1:
		frappe.throw(
			_("Multiple '{0}' sub-assemblies found. Reload the form and try again from the correct node.").format(
				bold(fg_item)
			),
			title=_("Ambiguous Parent"),
		)

	return doc.name


def get_parent_row_no(doc, name):
	for row in doc.items:
		if row.name == name:
			return row.idx

	if name == doc.name:
		return None

	frappe.msgprint(_("Parent Row No not found for {0}").format(name), alert=True)
	return None


@frappe.whitelist()
def delete_node(**kwargs):
	if isinstance(kwargs, str):
		kwargs = frappe.parse_json(kwargs)
	if isinstance(kwargs, dict):
		kwargs = frappe._dict(kwargs)

	if kwargs.fg_item and str(kwargs.fg_item).startswith(ROUTING_PREFIX):
		return frappe.get_doc("BOM Cost Calculator", kwargs.parent)

	if kwargs.fg_item and str(kwargs.fg_item).startswith(RAW_MATERIALS_PREFIX):
		return frappe.get_doc("BOM Cost Calculator", kwargs.parent)

	if kwargs.docname and (
		str(kwargs.docname).startswith(ROUTING_PREFIX)
		or str(kwargs.docname).startswith(RAW_MATERIALS_PREFIX)
		or OPERATION_SUFFIX in str(kwargs.docname)
	):
		return frappe.get_doc("BOM Cost Calculator", kwargs.parent)

	if kwargs.docname and frappe.db.exists("BOM Cost Calculator Item", kwargs.docname):
		row = frappe.get_doc("BOM Cost Calculator Item", kwargs.docname)
		frappe.delete_doc("BOM Cost Calculator Item", kwargs.docname)

		if not row.is_expandable:
			doc = frappe.get_doc("BOM Cost Calculator", kwargs.parent)
			doc.save()
			return doc

	items = get_children(parent=kwargs.fg_item, parent_id=kwargs.parent)

	for item in items:
		if item.get("is_routing_node") or item.get("is_operation_node") or item.get("is_raw_materials_node"):
			continue
		frappe.delete_doc("BOM Cost Calculator Item", item.name)
		if item.expandable:
			delete_node(fg_item=item.value, parent=item.parent_id)

	doc = frappe.get_doc("BOM Cost Calculator", kwargs.parent)
	doc.set_rate_for_items()
	doc.save()
	return doc


@frappe.whitelist()
def remove_routing(parent, assembly_row_name):
	if not assembly_row_name or str(assembly_row_name).startswith(ROUTING_PREFIX):
		frappe.throw(_("Invalid sub assembly row"))

	if not frappe.db.exists("BOM Cost Calculator Item", assembly_row_name):
		frappe.throw(_("Sub assembly row not found"))

	doc = frappe.get_doc("BOM Cost Calculator", parent)
	row = next((item for item in doc.items if item.name == assembly_row_name), None)
	if not row:
		frappe.throw(_("Sub assembly row not found"))

	row.routing = ""
	doc.save()
	frappe.msgprint(_("Routing removed"), alert=True)
	return doc


@frappe.whitelist()
def get_cost_summary(parent):
	doc = frappe.get_doc("BOM Cost Calculator", parent)
	breakdown = doc.get_cost_breakdown()

	if _cost_breakdown_is_stale(doc, breakdown):
		doc.save(ignore_permissions=True)
		breakdown = doc.get_cost_breakdown()

	return breakdown


def _cost_breakdown_is_stale(doc, breakdown):
	return (
		flt(doc.raw_materials_total) != flt(breakdown["raw_materials_total"])
		or flt(doc.routing_cost_total) != flt(breakdown["routing_cost_total"])
		or flt(doc.other_charges_total) != flt(breakdown["other_charges_total"])
		or flt(doc.raw_material_cost) != flt(breakdown["bom_cost"])
		or flt(doc.total_cost) != flt(breakdown["total_cost"])
	)


@frappe.whitelist()
def add_other_charge(parent, charge_type, amount, description=None):
	doc = frappe.get_doc("BOM Cost Calculator", parent)
	doc.append(
		"other_charges",
		{
			"charge_type": charge_type,
			"description": description or "",
			"amount": flt(amount),
		},
	)
	doc.save()
	return doc


@frappe.whitelist()
def remove_other_charge(parent, row_name):
	doc = frappe.get_doc("BOM Cost Calculator", parent)
	for row in list(doc.other_charges):
		if row.name == row_name:
			doc.remove(row)
			break
	doc.save()
	return doc


@frappe.whitelist()
def edit_bom_cost_calculator(doctype, docname, data, parent):
	if isinstance(data, str):
		data = frappe.parse_json(data)

	if str(docname).startswith(ROUTING_PREFIX) or str(docname).startswith(RAW_MATERIALS_PREFIX) or OPERATION_SUFFIX in str(docname):
		return frappe.get_doc("BOM Cost Calculator", parent)

	frappe.db.set_value(doctype, docname, data)
	doc = frappe.get_doc("BOM Cost Calculator", parent)
	doc.set_rate_for_items()
	doc.save()
	frappe.msgprint(_("Updated successfully"), alert=True)
	return doc
