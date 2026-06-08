import json
from urllib.parse import quote

import frappe

from fitzgerald_kitchens.setup.project_unit_fields import SITE_PROJECT_TYPE

PROJECTS_SIDEBAR = "Projects"
MANUFACTURING_SIDEBAR = "Manufacturing"

SITE_PROJECTS_SIDEBAR_FILTERS = f'[["Project","project_type","=","{SITE_PROJECT_TYPE}"]]'


def unit_projects_list_url() -> str:
	"""URL preserves != operator (DocType sidebar filters strip it)."""
	filter_value = quote(json.dumps(["!=", SITE_PROJECT_TYPE]))
	return f"/desk/project/view/list?project_type={filter_value}"


UNIT_PROJECTS_SIDEBAR_ITEM = {
	"label": "Unit",
	"link_to": None,
	"link_type": "URL",
	"type": "Link",
	"icon": "organization",
	"filters": None,
	"url": unit_projects_list_url(),
	"child": 0,
	"collapsible": 1,
	"indent": 0,
	"keep_closed": 0,
	"show_arrow": 0,
}

MAIN_SIDEBAR_ITEM = {
	"label": "Development Unit",
	"link_to": "Development Unit",
	"link_type": "DocType",
	"type": "Link",
	"icon": "package",
	"child": 0,
	"collapsible": 1,
	"indent": 0,
	"keep_closed": 0,
	"show_arrow": 0,
}

QR_SCAN_SIDEBAR_ITEM = {
	"label": "QR Stage Scan",
	"link_to": "Development Unit QR Scan",
	"link_type": "DocType",
	"type": "Link",
	"icon": "scan-barcode",
	"child": 0,
	"collapsible": 1,
	"indent": 0,
	"keep_closed": 0,
	"show_arrow": 0,
}

MY_TASKS_SIDEBAR_ITEM = {
	"label": "My Tasks",
	"link_to": "my-tasks",
	"link_type": "Page",
	"type": "Link",
	"icon": "list-checks",
	"child": 0,
	"collapsible": 1,
	"indent": 0,
	"keep_closed": 0,
	"show_arrow": 0,
}

SETUP_SIDEBAR_ITEMS = [
	{"label": "Development Block", "link_to": "Development Block"},
	{"label": "Development Unit Type", "link_to": "Development Unit Type"},
	{"label": "Project Unit Configuration", "link_to": "Project Unit Configuration"},
	{"label": "Manifest", "link_to": "Manifest"},
	{"label": "Unit Process Template", "link_to": "Unit Process Template"},
	{"label": "Development Workbook Import", "link_to": "Development Workbook Import"},
	{"label": "Kitchen Type", "link_to": "Kitchen Type"},
	{"label": "Kitchen Specification", "link_to": "Kitchen Specification"},
	{"label": "Wardrobe Type", "link_to": "Wardrobe Type"},
	{"label": "Wardrobe Specification", "link_to": "Wardrobe Specification"},
	{"label": "Development Stage", "link_to": "Development Stage"},
	{"label": "Development Stage Settings", "link_to": "Development Stage Settings"},
]

JOB_CARD_SUMMARY_DETAIL_ITEM = {
	"label": "Job Card Summary Detail",
	"link_to": "Job Card Summary Detail",
	"link_type": "Report",
	"type": "Link",
	"child": 1,
	"collapsible": 1,
	"indent": 0,
	"keep_closed": 0,
	"show_arrow": 0,
}

PROJECT_PRODUCTION_TIME_SUMMARY_ITEM = {
	"label": "Project Production Time Summary",
	"link_to": "Project Production Time Summary",
	"link_type": "Report",
	"type": "Link",
	"child": 1,
	"collapsible": 1,
	"indent": 0,
	"keep_closed": 0,
	"show_arrow": 0,
}

MANUFACTURING_COST_SUMMARY_ITEM = {
	"label": "Manufacturing Cost Summary",
	"link_to": "Manufacturing Cost Summary",
	"link_type": "Report",
	"type": "Link",
	"child": 1,
	"collapsible": 1,
	"indent": 0,
	"keep_closed": 0,
	"show_arrow": 0,
}

CAPACITY_PIPELINE_REPORT_ITEM = {
	"label": "Capacity Pipeline Report",
	"link_to": "Capacity Pipeline Report",
	"link_type": "Report",
	"type": "Link",
	"child": 1,
	"collapsible": 1,
	"indent": 0,
	"keep_closed": 0,
	"show_arrow": 0,
}

BOM_COST_CALCULATOR_ITEM = {
	"label": "BOM Cost Calculator",
	"link_to": "BOM Cost Calculator",
	"link_type": "DocType",
	"type": "Link",
	"child": 1,
	"collapsible": 1,
	"indent": 0,
	"keep_closed": 0,
	"show_arrow": 0,
}

PROJECT_REPORT_SIDEBAR_ITEMS = [
	CAPACITY_PIPELINE_REPORT_ITEM,
	PROJECT_PRODUCTION_TIME_SUMMARY_ITEM,
	MANUFACTURING_COST_SUMMARY_ITEM,
]


def ensure_projects_sidebar():
	if not frappe.db.exists("Workspace Sidebar", PROJECTS_SIDEBAR):
		return

	sidebar = frappe.get_doc("Workspace Sidebar", PROJECTS_SIDEBAR)
	changed = False

	if _ensure_site_projects_sidebar_filter(sidebar):
		changed = True

	if _ensure_unit_projects_sidebar_item(sidebar):
		changed = True

	if _ensure_main_sidebar_item(sidebar):
		changed = True

	if _ensure_my_tasks_sidebar_item(sidebar):
		changed = True

	if _ensure_qr_scan_sidebar_item(sidebar):
		changed = True

	if _ensure_setup_sidebar_items(sidebar):
		changed = True

	if _ensure_projects_reports_sidebar(sidebar):
		changed = True

	if changed:
		sidebar.flags.ignore_permissions = True
		sidebar.save()


def _ensure_site_projects_sidebar_filter(sidebar):
	items = [_item_dict(row) for row in sidebar.items]
	changed = False

	for item in items:
		if item.get("link_to") != "Project" or item.get("link_type") != "DocType":
			continue
		if item.get("label") != "Project":
			continue
		if item.get("filters") != SITE_PROJECTS_SIDEBAR_FILTERS:
			item["filters"] = SITE_PROJECTS_SIDEBAR_FILTERS
			changed = True
		break

	if changed:
		_apply_items(sidebar, items)
	return changed


def _ensure_unit_projects_sidebar_item(sidebar):
	items = [_item_dict(row) for row in sidebar.items]
	if _has_sidebar_label(items, UNIT_PROJECTS_SIDEBAR_ITEM["label"]):
		changed = _sync_unit_projects_sidebar_item(items, sidebar)
		return changed or _ensure_unit_projects_sidebar_order(sidebar)

	insert_at = _index_of_project_doctype_link(items)
	if insert_at is None:
		return False

	items.insert(insert_at + 1, UNIT_PROJECTS_SIDEBAR_ITEM.copy())
	_apply_items(sidebar, items)
	return True


def _ensure_unit_projects_sidebar_order(sidebar):
	items = [_item_dict(row) for row in sidebar.items]
	project_index = _index_of_project_doctype_link(items)
	unit_index = _index_of_sidebar_label(items, UNIT_PROJECTS_SIDEBAR_ITEM["label"])
	if project_index is None or unit_index is None or unit_index == project_index + 1:
		return False

	unit_item = items.pop(unit_index)
	if unit_index < project_index:
		project_index = _index_of_project_doctype_link(items)
	items.insert(project_index + 1, unit_item)
	_apply_items(sidebar, items)
	return True


def _index_of_sidebar_label(items, label, link_to=None):
	for index, item in enumerate(items):
		if item.get("label") != label:
			continue
		if link_to and item.get("link_to") != link_to:
			continue
		return index
	return None


def _sync_unit_projects_sidebar_item(items, sidebar):
	changed = False
	expected_url = unit_projects_list_url()
	for item in items:
		if item.get("label") != UNIT_PROJECTS_SIDEBAR_ITEM["label"]:
			continue
		for key, value in UNIT_PROJECTS_SIDEBAR_ITEM.items():
			if item.get(key) != value:
				item[key] = value
				changed = True
		if item.get("url") != expected_url:
			item["url"] = expected_url
			changed = True
		break

	if changed:
		_apply_items(sidebar, items)
	return changed


def _ensure_projects_reports_sidebar(sidebar):
	items = [_item_dict(row) for row in sidebar.items]
	changed = False

	for report_item in PROJECT_REPORT_SIDEBAR_ITEMS:
		if _has_link_in(items, report_item["link_to"]):
			continue

		insert_at = _index_after_reports_section(items)
		for existing_item in PROJECT_REPORT_SIDEBAR_ITEMS:
			existing_index = _index_of_link(items, existing_item["link_to"])
			if existing_index is not None and existing_index >= insert_at:
				insert_at = existing_index + 1

		items.insert(insert_at, report_item)
		changed = True

	if changed:
		_apply_items(sidebar, items)
	return changed


def ensure_manufacturing_sidebar():
	if not frappe.db.exists("Workspace Sidebar", MANUFACTURING_SIDEBAR):
		return

	sidebar = frappe.get_doc("Workspace Sidebar", MANUFACTURING_SIDEBAR)
	changed = False

	if _ensure_manufacturing_tools_sidebar(sidebar):
		changed = True

	if _ensure_manufacturing_reports_sidebar(sidebar):
		changed = True

	if changed:
		sidebar.flags.ignore_permissions = True
		sidebar.save()


def _ensure_manufacturing_tools_sidebar(sidebar):
	items = [_item_dict(row) for row in sidebar.items]
	if _has_link_in(items, BOM_COST_CALCULATOR_ITEM["link_to"]):
		return False

	insert_at = _index_of_link(items, "BOM Creator")
	if insert_at is None:
		insert_at = _index_after_tools_section(items)
	else:
		insert_at += 1

	if insert_at is None:
		return False

	items.insert(insert_at, BOM_COST_CALCULATOR_ITEM)
	_apply_items(sidebar, items)
	return True


def _ensure_manufacturing_reports_sidebar(sidebar):
	items = [_item_dict(row) for row in sidebar.items]
	changed = False

	if not _has_link_in(items, JOB_CARD_SUMMARY_DETAIL_ITEM["link_to"]):
		insert_at = _index_of_link(items, "Job Card Summary")
		if insert_at is None:
			insert_at = _index_after_reports_section(items)
		else:
			insert_at += 1

		items.insert(insert_at, JOB_CARD_SUMMARY_DETAIL_ITEM)
		changed = True

	if not _has_link_in(items, CAPACITY_PIPELINE_REPORT_ITEM["link_to"]):
		insert_at = _index_of_link(items, JOB_CARD_SUMMARY_DETAIL_ITEM["link_to"])
		if insert_at is None:
			insert_at = _index_after_reports_section(items)
		else:
			insert_at += 1

		items.insert(insert_at, CAPACITY_PIPELINE_REPORT_ITEM)
		changed = True
	elif _sync_sidebar_link(items, CAPACITY_PIPELINE_REPORT_ITEM):
		changed = True

	if changed:
		_apply_items(sidebar, items)
	return changed


def _index_after_tools_section(items):
	for index, item in enumerate(items):
		if item.get("type") == "Section Break" and item.get("label") == "Tools":
			return index + 1
	return None


def _index_after_reports_section(items):
	for index, item in enumerate(items):
		if item.get("type") == "Section Break" and item.get("label") == "Reports":
			return index + 1
	return len(items)


def _ensure_main_sidebar_item(sidebar):
	if _has_sidebar_link(sidebar, MAIN_SIDEBAR_ITEM["link_to"]):
		return False

	items = [_item_dict(row) for row in sidebar.items]
	insert_at = _index_of_link(items, "Task")
	if insert_at is None:
		insert_at = _index_after_link(items, "Project")
	if insert_at is None:
		insert_at = len(items)

	items.insert(insert_at, MAIN_SIDEBAR_ITEM)
	_apply_items(sidebar, items)
	return True


def _ensure_my_tasks_sidebar_item(sidebar):
	if _has_sidebar_link(sidebar, MY_TASKS_SIDEBAR_ITEM["link_to"]):
		return False

	items = [_item_dict(row) for row in sidebar.items]
	insert_at = _index_of_link(items, "Task")
	if insert_at is None:
		insert_at = _index_of_link(items, QR_SCAN_SIDEBAR_ITEM["link_to"])
		if insert_at is not None:
			insert_at += 1
	if insert_at is None:
		insert_at = len(items)

	items.insert(insert_at, MY_TASKS_SIDEBAR_ITEM)
	_apply_items(sidebar, items)
	return True


def _ensure_qr_scan_sidebar_item(sidebar):
	if _has_sidebar_link(sidebar, QR_SCAN_SIDEBAR_ITEM["link_to"]):
		return False

	items = [_item_dict(row) for row in sidebar.items]
	insert_at = _index_of_link(items, MAIN_SIDEBAR_ITEM["link_to"])
	if insert_at is None:
		insert_at = len(items)
	else:
		insert_at += 1

	items.insert(insert_at, QR_SCAN_SIDEBAR_ITEM)
	_apply_items(sidebar, items)
	return True


def _ensure_setup_sidebar_items(sidebar):
	items = [_item_dict(row) for row in sidebar.items]
	setup_end = _setup_section_end_index(items)
	if setup_end is None:
		return False

	changed = False
	offset = 0
	for item in SETUP_SIDEBAR_ITEMS:
		if _has_link_in(items, item["link_to"]):
			continue

		row = {
			**item,
			"link_type": "DocType",
			"type": "Link",
			"child": 1,
			"collapsible": 1,
			"indent": 0,
			"keep_closed": 0,
			"show_arrow": 0,
		}
		items.insert(setup_end + offset, row)
		offset += 1
		changed = True

	if changed:
		_apply_items(sidebar, items)
	return changed


def _setup_section_end_index(items):
	setup_start = None
	for index, item in enumerate(items):
		if item.get("type") == "Section Break" and item.get("label") == "Setup":
			setup_start = index
			continue

		if setup_start is None:
			continue

		if item.get("type") == "Section Break" and item.get("child") == 0:
			return index

	return len(items) if setup_start is not None else None


def _index_of_project_doctype_link(items):
	for index, item in enumerate(items):
		if item.get("link_to") != "Project":
			continue
		if item.get("link_type") != "DocType":
			continue
		if item.get("label") == "Project":
			return index
	return None


def _index_of_link(items, link_to):
	for index, item in enumerate(items):
		if item.get("link_to") == link_to:
			return index
	return None


def _index_after_link(items, link_to):
	index = _index_of_link(items, link_to)
	return index + 1 if index is not None else None


def _has_sidebar_link(sidebar, link_to):
	return _has_link_in([_item_dict(row) for row in sidebar.items], link_to)


def _has_link_in(items, link_to):
	return any(item.get("link_to") == link_to for item in items)


def _has_sidebar_label(items, label, link_to=None):
	for item in items:
		if item.get("label") != label:
			continue
		if link_to is not None and item.get("link_to") != link_to:
			continue
		return True
	return False


def _remove_sidebar_link(sidebar, link_to):
	items = [_item_dict(row) for row in sidebar.items]
	if not _has_link_in(items, link_to):
		return False

	items = [item for item in items if item.get("link_to") != link_to]
	_apply_items(sidebar, items)
	return True


def _sync_sidebar_link(items, template):
	"""Align an existing sidebar row with the template (e.g. clear stray icons)."""
	for item in items:
		if item.get("link_to") != template["link_to"]:
			continue

		changed = False
		for key, value in template.items():
			if item.get(key) != value:
				item[key] = value
				changed = True
		if item.get("icon"):
			item["icon"] = None
			changed = True
		return changed
	return False


def _item_dict(row):
	data = row.as_dict()
	for field in ("name", "parent", "parentfield", "parenttype", "doctype", "owner", "creation", "modified"):
		data.pop(field, None)
	return data


def _apply_items(sidebar, items):
	sidebar.items = []
	for index, item in enumerate(items, start=1):
		row = item.copy()
		row["idx"] = index
		sidebar.append("items", row)
