import os
from collections import OrderedDict, defaultdict

import frappe
from frappe import _
from frappe.utils import format_datetime, get_datetime, pretty_date


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg"}

ALL_TASK_TYPES = [
	"Survey",
	"Delivery",
	"Despatch",
	"Assembly",
	"Manufacture",
	"Export",
	"Drawing",
	"Fitting",
	"Handover",
]

FOCUS_STAGES = ["Despatch", "Delivery", "Fitting", "Handover"]

PROJECT_TYPE_FILTERS = [
	{"key": "all", "label": _("All units")},
	{"key": "kitchens", "label": _("Kitchens")},
	{"key": "wardrobes", "label": _("Wardrobes")},
	{"key": "utilities", "label": _("Utilities")},
	{"key": "vanity", "label": _("Vanity unit")},
	{"key": "pantry", "label": _("Pantry")},
]

_TASK_TYPE_LOOKUP = {name.lower(): name for name in ALL_TASK_TYPES}


def get_context(context):
	"""Web page controller for /project_photos — all projects, units grouped by task type."""

	context.no_cache = 1

	if frappe.session.user == "Guest":
		frappe.throw(_("You need to be logged in to view project photos."), frappe.PermissionError)

	context.project_type_filters = PROJECT_TYPE_FILTERS
	context.focus_stages = FOCUS_STAGES
	context.dashboard_stats = {
		"total_projects": 0,
		"total_units": 0,
		"total_photos": 0,
		"last_upload": "-",
	}
	context.stage_totals = []
	context.units = []

	projects = _get_readable_projects()
	context.dashboard_stats["total_projects"] = len(projects)

	if not projects:
		return context

	project_names = [row.name for row in projects]

	units_map = OrderedDict()
	for project in projects:
		project_type = _get_project_type_label(project)
		project_name = _clean_label(project.get("project_name")) or project.name

		units_map[project.name] = {
			"project": project.name,
			"project_name": project_name,
			"project_type": project_type,
			"display_name": _format_project_display_name(project_name, project_type),
			"category": _category_from_project_type(project_type),
			"stage_map": OrderedDict(
				(stage, _empty_stage_cell(stage)) for stage in FOCUS_STAGES
			),
			"total_photos": 0,
			"last_upload_dt": None,
		}

	tasks = _get_tasks_for_projects(project_names)
	task_names = [task.name for task in tasks] if tasks else []
	files_by_task = _get_task_files(task_names)
	if tasks:
		_add_task_field_uploads(tasks, files_by_task)

	stage_totals_map = {stage: 0 for stage in FOCUS_STAGES}
	latest_global_upload_dt = None
	total_photos = 0

	for task in tasks or []:
		unit = units_map.get(task.project)
		if not unit:
			continue

		task_type = _normalize_task_type(task.get("type"))
		if task_type not in FOCUS_STAGES:
			continue

		photos = files_by_task.get(task.name, [])
		if not photos:
			continue

		stage_cell = unit["stage_map"][task_type]

		stage_cell["photos"].extend(photos)
		stage_cell["count"] += len(photos)

		unit["total_photos"] += len(photos)
		total_photos += len(photos)
		stage_totals_map[task_type] += len(photos)

		latest_task_dt = _latest_photo_datetime(photos)
		unit["last_upload_dt"] = _max_datetime(unit["last_upload_dt"], latest_task_dt)
		latest_global_upload_dt = _max_datetime(latest_global_upload_dt, latest_task_dt)

	units = []

	for unit in units_map.values():
		stages = []

		for stage_name in FOCUS_STAGES:
			cell = unit["stage_map"][stage_name]
			cell["photos"] = sorted(
				cell["photos"],
				key=lambda row: row.get("creation_dt") or get_datetime("1900-01-01"),
				reverse=True,
			)
			cell["latest_url"] = cell["photos"][0]["url"] if cell["photos"] else ""
			cell["preview_photos"] = cell["photos"][:4]
			cell["blank_slots"] = list(range(max(0, 4 - len(cell["preview_photos"]))))
			cell["gallery_images"] = [
				{
					"file_url": photo.get("original_url") or photo.get("url"),
					"file_name": photo.get("file_name") or "",
				}
				for photo in cell["photos"]
			]
			stages.append(cell)

		units.append(
			{
				"display_name": unit["display_name"],
				"project_name": unit["project_name"],
				"project_type": unit["project_type"],
				"project": unit["project"],
				"category": unit["category"],
				"total_photos": unit["total_photos"],
				"last_upload": _pretty_upload_date(unit["last_upload_dt"]),
				"last_upload_dt": unit["last_upload_dt"],
				"stages": stages,
			}
		)

	units.sort(
		key=lambda row: (
			row.get("last_upload_dt") or get_datetime("1900-01-01"),
			row.get("project_name") or "",
		),
		reverse=True,
	)

	context.units = units
	context.stage_totals = [
		{"stage": stage, "count": stage_totals_map[stage]} for stage in FOCUS_STAGES
	]
	context.dashboard_stats = {
		"total_projects": len(projects),
		"total_units": len(units),
		"total_photos": total_photos,
		"last_upload": _pretty_upload_date(latest_global_upload_dt),
	}

	return context


def _get_readable_projects():
	fields = ["name", "project_name", "status", "customer"]
	meta = frappe.get_meta("Project")
	if meta.has_field("project_type"):
		fields.append("project_type")

	try:
		return frappe.get_list(
			"Project",
			fields=fields,
			filters={"status": ["!=", "Cancelled"]},
			order_by="modified desc",
			limit_page_length=500,
		)
	except frappe.PermissionError:
		return []


def _get_project_type_label(project):
	return _clean_label(project.get("project_type"))


def _format_project_display_name(project_name, project_type):
	if project_type:
		return f"{project_name} - {project_type}"
	return project_name


def _category_from_project_type(project_type):
	return _detect_category(project_type)


def _get_tasks_for_projects(project_names):
	if not project_names:
		return []

	task_meta = frappe.get_meta("Task")

	fields = [
		"name",
		"subject",
		"project",
		"type",
		"status",
		"creation",
		"modified",
	]

	optional_fields = ["custom_uploader_target", "custom_file_upload"]
	for fieldname in optional_fields:
		if task_meta.has_field(fieldname):
			fields.append(fieldname)

	return frappe.get_list(
		"Task",
		filters={"project": ["in", project_names]},
		fields=fields,
		order_by="modified desc",
		limit_page_length=5000,
	)


def _empty_stage_cell(task_type):
	return {
		"task_type": task_type,
		"count": 0,
		"photos": [],
		"latest_url": "",
		"preview_photos": [],
		"blank_slots": list(range(4)),
		"gallery_images": [],
	}


def _normalize_task_type(value):
	value = _clean_label(value)
	if not value:
		return None

	lower = value.lower()
	if lower in _TASK_TYPE_LOOKUP:
		return _TASK_TYPE_LOOKUP[lower]

	if lower.startswith("despatch") or lower.startswith("dispatch"):
		return "Despatch"

	for task_type in ALL_TASK_TYPES:
		if lower == task_type.lower() or lower.endswith(f" {task_type.lower()}"):
			return task_type
		if task_type.lower() in lower:
			return task_type

	return None


def _get_task_files(task_names):
	files_by_task = defaultdict(list)

	if not task_names:
		return files_by_task

	file_fields = [
		"name",
		"file_name",
		"file_url",
		"attached_to_name",
		"creation",
		"modified",
	]

	file_meta = frappe.get_meta("File")
	for optional_field in ("thumbnail_url", "file_type", "mime_type"):
		if file_meta.has_field(optional_field):
			file_fields.append(optional_field)

	file_rows = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "Task",
			"attached_to_name": ["in", task_names],
			"is_folder": 0,
		},
		fields=file_fields,
		order_by="creation desc",
		limit_page_length=5000,
	)

	seen = set()

	for file_doc in file_rows:
		url = file_doc.get("file_url")
		task_name = file_doc.get("attached_to_name")

		if not url or not task_name:
			continue

		if not _is_image_file(url, file_doc.get("file_name")):
			continue

		key = (task_name, url)
		if key in seen:
			continue

		seen.add(key)

		files_by_task[task_name].append(
			{
				"name": file_doc.get("name"),
				"file_name": file_doc.get("file_name") or os.path.basename(url),
				"url": file_doc.get("thumbnail_url") or url,
				"original_url": url,
				"creation": file_doc.get("creation"),
				"creation_dt": _to_datetime(file_doc.get("creation")),
			}
		)

	return files_by_task


def _add_task_field_uploads(tasks, files_by_task):
	for task in tasks:
		url = task.get("custom_file_upload")
		if not url or not _is_image_file(url):
			continue

		existing_urls = {
			row.get("original_url") or row.get("url")
			for row in files_by_task.get(task.name, [])
		}

		if url in existing_urls:
			continue

		files_by_task[task.name].append(
			{
				"name": "",
				"file_name": os.path.basename(url),
				"url": url,
				"original_url": url,
				"creation": task.get("modified") or task.get("creation"),
				"creation_dt": _to_datetime(task.get("modified") or task.get("creation")),
			}
		)


def _is_image_file(url, file_name=None):
	text = (file_name or url or "").lower().split("?")[0]
	extension = os.path.splitext(text)[1]
	return extension in IMAGE_EXTENSIONS


def _clean_label(value):
	if value is None:
		return ""
	return str(value).strip()


def _detect_category(project_type):
	project_type = _clean_label(project_type).lower()

	if project_type in ("kitchen", "kitchens"):
		return "kitchens"
	if project_type in ("wardrobe", "wardrobes"):
		return "wardrobes"
	if project_type in ("utility", "utilities"):
		return "utilities"
	if project_type in ("vanity unit", "vanity"):
		return "vanity"
	if project_type in ("pantry",):
		return "pantry"

	if "kitchen" in project_type:
		return "kitchens"
	if "wardrobe" in project_type:
		return "wardrobes"
	if "utility" in project_type:
		return "utilities"
	if "vanity" in project_type:
		return "vanity"
	if "pantry" in project_type:
		return "pantry"

	return "other"


def _latest_photo_datetime(photos):
	latest = None
	for photo in photos:
		latest = _max_datetime(latest, photo.get("creation_dt"))
	return latest


def _max_datetime(left, right):
	left_dt = _to_datetime(left)
	right_dt = _to_datetime(right)

	if not left_dt:
		return right_dt
	if not right_dt:
		return left_dt
	return max(left_dt, right_dt)


def _to_datetime(value):
	if not value:
		return None
	try:
		return get_datetime(value)
	except Exception:
		return None


def _pretty_upload_date(value):
	value = _to_datetime(value)
	if not value:
		return "-"
	return pretty_date(value)


def _format_datetime(value):
	value = _to_datetime(value)
	if not value:
		return "-"
	return format_datetime(value, "dd MMM yyyy, hh:mm a")
