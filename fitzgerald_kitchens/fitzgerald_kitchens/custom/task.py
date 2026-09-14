import frappe
import base64
from frappe import _
from frappe.utils.file_manager import save_file

@frappe.whitelist()
def get_attached_files(doctype, name):
	return frappe.get_all(
		"File",
		filters={"attached_to_doctype": doctype, "attached_to_name": name},
		fields=["name", "file_url", "file_name"]
	)

@frappe.whitelist()
def delete_all_files(doctype, name):
	files = frappe.get_all("File", filters={"attached_to_doctype": doctype, "attached_to_name": name})
	for f in files:
		frappe.delete_doc("File", f.name)
	return True

@frappe.whitelist()
def attach_task_photo(task: str, file_url: str, filename: str | None = None) -> dict:
	"""Metadata-only step of the offline camera-photo upload: the binary file
	is expected to already exist (uploaded separately via Frappe's standard
	`upload_file` endpoint, which attaches it to this Task directly), and
	this just confirms the link and gives the offline sync ledger something
	to record. Mirrors development_unit_offline.add_evidence's two-phase
	pattern — kept small and fast through the normal JSON push pipeline,
	while the slow/flaky binary transfer gets its own retry loop client-side.
	"""
	frappe.has_permission("Task", doc=task, ptype="write", throw=True)
	exists = frappe.db.exists(
		"File",
		{
			"attached_to_doctype": "Task",
			"attached_to_name": task,
			"file_url": file_url,
		},
	)
	if not exists:
		frappe.throw(_("Uploaded file not found or not attached to this task"))
	return {"task": task, "file_url": file_url}


@frappe.whitelist()
def upload_camera_snapshot(doctype, name, filename, base64_data):
	if "," in base64_data:
		base64_data = base64_data.split(",")[1]
	
	file_content = base64.b64decode(base64_data)
	
	file_doc = save_file(
		fname=filename,
		content=file_content,
		dt=doctype,
		dn=name,
		folder="Home/Attachments",
		is_private=0
	)
	return file_doc.name
