// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

// BR-PPP-07: blue = early, green = on time, red = late
const SPO_SCHEDULE_COLOURS = { Early: "blue", "On Time": "green", Late: "red" };

frappe.query_reports["Site Project Overview"] = {
	filters: [
		{
			fieldname: "site_project",
			label: __("Site Project"),
			fieldtype: "Link",
			options: "Project",
			reqd: 1,
			get_query: () => ({ filters: { project_type: "Site" } }),
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "schedule") {
			const colour = SPO_SCHEDULE_COLOURS[data.schedule] || "gray";
			return `<span class="indicator-pill no-indicator-dot ${colour}">${value}</span>`;
		}
		return value;
	},
};
