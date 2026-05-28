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
