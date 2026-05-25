// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Development Unit Stage", {
	planned_date(frm) {
		refresh_stage_schedule_display(frm);
	},
	actual_completion_date(frm) {
		refresh_stage_schedule_display(frm);
	},
	status(frm) {
		refresh_stage_schedule_display(frm);
	},
	sequence(frm) {
		refresh_stage_schedule_display(frm);
	},
});

function refresh_stage_schedule_display(frm) {
	if (!frm.fields_dict.stages) {
		return;
	}

	if (typeof schedule_apply_stage_schedule_display === "function") {
		schedule_apply_stage_schedule_display(frm);
	}
	if (typeof update_current_stage_from_stages === "function") {
		update_current_stage_from_stages(frm);
	}
}
