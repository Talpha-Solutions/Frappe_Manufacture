app_name = "fitzgerald_kitchens"
app_title = "fitzgerald_kitchens"
app_publisher = "talpha solutions"
app_description = "kitchen app"
app_email = "prageeth@talphasolutions.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "fitzgerald_kitchens",
# 		"logo": "/assets/fitzgerald_kitchens/logo.png",
# 		"title": "fitzgerald_kitchens",
# 		"route": "/fitzgerald_kitchens",
# 		"has_permission": "fitzgerald_kitchens.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/fitzgerald_kitchens/css/fitzgerald_kitchens.css"
# app_include_js = "/assets/fitzgerald_kitchens/js/fitzgerald_kitchens.js"

# include js, css files in header of web template
web_include_css = "/assets/fitzgerald_kitchens/css/portal_sidebar.css"
web_include_js = "/assets/fitzgerald_kitchens/js/portal_tracker_state.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "fitzgerald_kitchens/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"Project": "public/js/project.js",
	"Task": "public/js/task.js",
}
doctype_list_js = {
	"Development Stage": "fitzgerald_kitchens/doctype/development_stage/development_stage_list.js",
	"BOM Cost Calculator": "fitzgerald_kitchens/doctype/bom_cost_calculator/bom_cost_calculator_list.js",
}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "fitzgerald_kitchens/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Portal sidebar on all customer/supplier portal routes
# ------------------
update_website_context = [
	"fitzgerald_kitchens.website.portal_context.update_website_context",
]

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "fitzgerald_kitchens.utils.jinja_methods",
# 	"filters": "fitzgerald_kitchens.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "fitzgerald_kitchens.install.before_install"
before_migrate = "fitzgerald_kitchens.migrate.before_migrate"
after_install = "fitzgerald_kitchens.setup.install.after_install"
after_migrate = [
	"fitzgerald_kitchens.migrate.after_migrate",
	"fitzgerald_kitchens.setup.install.after_install",
]

# Uninstallation
# ------------

# before_uninstall = "fitzgerald_kitchens.uninstall.before_uninstall"
# after_uninstall = "fitzgerald_kitchens.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "fitzgerald_kitchens.utils.before_app_install"
# after_app_install = "fitzgerald_kitchens.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "fitzgerald_kitchens.utils.before_app_uninstall"
# after_app_uninstall = "fitzgerald_kitchens.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "fitzgerald_kitchens.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"fitzgerald_kitchens.tasks.all"
# 	],
# 	"daily": [
# 		"fitzgerald_kitchens.tasks.daily"
# 	],
# 	"hourly": [
# 		"fitzgerald_kitchens.tasks.hourly"
# 	],
# 	"weekly": [
# 		"fitzgerald_kitchens.tasks.weekly"
# 	],
# 	"monthly": [
# 		"fitzgerald_kitchens.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "fitzgerald_kitchens.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "fitzgerald_kitchens.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "fitzgerald_kitchens.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "fitzgerald_kitchens.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["fitzgerald_kitchens.utils.before_request"]
# after_request = ["fitzgerald_kitchens.utils.after_request"]

# Job Events
# ----------
# before_job = ["fitzgerald_kitchens.utils.before_job"]
# after_job = ["fitzgerald_kitchens.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"fitzgerald_kitchens.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Fixtures
# --------
# Imported from fitzgerald_kitchens/fixtures/*.json on bench migrate.
# Re-export after desk edits: bench --site <site> export-fixtures --app fitzgerald_kitchens
fixtures = [
	{
		"dt": "Development Stage",
	},
	{
		"dt": "Development Stage Settings",
		"filters": [["name", "=", "Development Stage Settings"]],
	},
	{
		"dt": "Workspace Sidebar",
		"filters": [["name", "in", ["Projects"]]],
	},
	{
		"dt": "Custom Field",
		"filters": [["fieldname", "in", ["custom_file_upload", "custom_uploader_target"]]],
	},
	{
		"dt": "Property Setter",
		"filters": [["doc_type", "=", "Task"], ["property", "in", ["max_attachments", "field_order", "fieldtype"]]],
	},
]

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

from fitzgerald_kitchens.setup.project_website_list import (
	patch_project_website_list,
	patch_project_website_tasks,
)

patch_project_website_list()
patch_project_website_tasks()

# Website Portal Sidebar
portal_menu_items = [
	{"title": "Projects Overview", "route": "/project", "role": "Customer"},
	{"title": "Projects Photos", "route": "/project_photos", "role": "Customer"},
	{"title": "Request for Quotations", "route": "/rfq", "role": "Supplier"},
	{"title": "Supplier Quotation", "route": "/supplier-quotations", "role": "Supplier"},
	{"title": "Purchase Orders", "route": "/purchase-orders", "role": "Supplier"},
	{"title": "Purchase Invoices", "route": "/purchase-invoices", "role": "Supplier"},
	{"title": "Quotations", "route": "/quotations", "role": "Customer"},
	{"title": "Orders", "route": "/orders", "role": "Customer"},
	{"title": "Invoices", "route": "/invoices", "role": "Customer"},
	{"title": "Shipments", "route": "/shipments", "role": "Customer"},
	{"title": "Issues", "route": "/issues", "role": "Customer"},
	{"title": "Addresses", "route": "/addresses", "role": "Customer"},
	{"title": "Timesheets", "route": "/timesheets", "role": "Customer"},
	{"title": "Material Request", "route": "/material-requests", "role": "Customer"},
]
