frappe.listview_settings["BOM Cost Calculator"] = {
	add_fields: ["status"],
	get_indicator: function (doc) {
		return [__("Draft"), "blue", "status,=,Draft"];
	},
};
