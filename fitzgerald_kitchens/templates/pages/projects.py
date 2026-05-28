# Copyright (c) 2026, Fitzgerald Kitchens Custom Portal Pipeline
import frappe
import json
from erpnext.templates.pages.projects import get_timesheets, get_attachments

def get_context(context):
    project_user = frappe.db.get_value(
        "Project User",
        {"parent": frappe.form_dict.project, "user": frappe.session.user},
        ["user", "view_attachments", "hide_timesheets"],
        as_dict=True,
    )
    if frappe.session.user != "Administrator" and (not project_user or frappe.session.user == "Guest"):
        raise frappe.PermissionError

    context.no_cache = 1
    context.show_sidebar = True
    project = frappe.get_doc("Project", frappe.form_dict.project)
    project.has_permission("read")

    # Fetch tasks using custom query function below that grabs attachments
    project.tasks = get_custom_tasks_with_images(
        project.name, search=frappe.form_dict.get("search")
    )

    if project_user and not project_user.hide_timesheets:
        project.timesheets = get_timesheets(project.name, start=0, search=frappe.form_dict.get("search"))

    if project_user and project_user.view_attachments:
        project.attachments = get_attachments(project.name)

    context.doc = project

def get_custom_tasks_with_images(project, search=None):
    filters = {"project": project}
    if search:
        filters["subject"] = ("like", f"%{search}%")
        
    tasks = frappe.get_all(
        "Task",
        filters=filters,
        fields=["name", "subject", "status", "modified", "_assign", "exp_end_date", "is_group", "parent_task"],
        limit_page_length=200,
        order_by="modified desc"
    )
    
    # Process each individual task to pull down files matching the client script uploads
    for task in tasks:
        attachments = frappe.get_all(
            "File",
            filters={
                "attached_to_doctype": "Task",
                 "attached_to_name": task.name
            },
            fields=["file_url", "file_name", "is_private"]
        )
        
        # Keep web-compatible image variants only
        task.attached_images = [
            att for att in attachments 
            if att.file_url and att.file_url.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))
        ]
        task.image_count = len(task.attached_images)
        
    # Maintain parent-child hierarchy grouping mapping
    return build_task_hierarchy(tasks)

def build_task_hierarchy(tasks):
    """Dynamically restructures structural arrays into parent-child formats expected by task macros"""
    task_map = {t.name: t for t in tasks}
    root_tasks = []
    
    for t in tasks:
        t.children = []
        if t.parent_task and t.parent_task in task_map:
            task_map[t.parent_task].children.append(t)
        else:
            root_tasks.append(t)
            
    return root_tasks