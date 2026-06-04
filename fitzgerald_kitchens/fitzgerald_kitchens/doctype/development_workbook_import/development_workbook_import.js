// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

const SUCCESS_STATUSES = ["Ready", "Completed"];

frappe.ui.form.on("Development Workbook Import", {
	refresh(frm) {
		setup_import_buttons(frm);
		toggle_project_template(frm);
		toggle_log_fields(frm);
		show_status_message(frm);
		fix_legacy_log_fields(frm);
	},
	generate_tasks_from_template(frm) {
		toggle_project_template(frm);
		if (!frm.doc.generate_tasks_from_template) {
			frm.set_value("project_template", "");
		}
	},
	import_status(frm) {
		toggle_log_fields(frm);
		show_status_message(frm);
	},
});

function toggle_project_template(frm) {
	const enabled = !!frm.doc.generate_tasks_from_template;
	frm.toggle_enable("project_template", enabled);
	frm.toggle_reqd("project_template", enabled);
}

function toggle_log_fields(frm) {
	const status = frm.doc.import_status;
	const has_summary = !!(frm.doc.import_summary || "").trim();
	const has_errors = !!(frm.doc.error_log || "").trim();
	const show_summary = SUCCESS_STATUSES.includes(status) || has_summary;
	const show_errors = status === "Failed" && has_errors;

	frm.toggle_display("import_summary", show_summary);
	frm.toggle_display("error_log", show_errors);
}

function show_status_message(frm) {
	if (frm.is_new()) {
		return;
	}
	const status = frm.doc.import_status;
	if (status === "Completed") {
		frm.dashboard.set_headline_alert(__("Import completed successfully"), "green");
	} else if (status === "Ready") {
		frm.dashboard.set_headline_alert(__("Ready to import"), "blue");
	} else if (status === "Failed") {
		frm.dashboard.set_headline_alert(__("Import failed — see Errors below"), "red");
	} else if (status === "Importing") {
		frm.dashboard.set_headline_alert(__("Import in progress…"), "orange");
	}
}

function fix_legacy_log_fields(frm) {
	if (frm.is_new() || frm.is_dirty()) {
		return;
	}
	const err = (frm.doc.error_log || "").trim();
	if (!err || !SUCCESS_STATUSES.includes(frm.doc.import_status)) {
		return;
	}
	if (!err.includes("Import completed") && !err.includes("Validation passed")) {
		return;
	}
	frappe.call({
		method: "fix_legacy_log_fields",
		doc: frm.doc,
		callback() {
			frm.reload_doc();
		},
	});
}

function setup_import_buttons(frm) {
	if (frm.is_new()) {
		return;
	}

	const is_full = frm.doc.import_mode === "Full Workbook";
	const validate_label = is_full ? __("Validate Workbook") : __("Validate File");
	const run_label = is_full ? __("Run Full Import") : __("Run Import");

	frm.add_custom_button(validate_label, () => validate_workbook(frm));

	if (frm.doc.import_status === "Ready") {
		frm.add_custom_button(run_label, () => run_workbook_import(frm), __("Actions"));
	}
}

function validate_workbook(frm) {
	if (!frm.doc.import_file) {
		frappe.msgprint(__("Attach an import file first."));
		return;
	}

	if (frm.doc.import_mode === "Full Workbook") {
		const file_url = frm.doc.import_file || "";
		if (!file_url.toLowerCase().endsWith(".xlsx")) {
			frappe.msgprint(__("Full workbook import requires an .xlsx file."));
			return;
		}
	}

	if (frm.doc.generate_tasks_from_template && !frm.doc.project_template) {
		frappe.msgprint(__("Select a Project Template when Generate Tasks is enabled."));
		return;
	}

	const run_validate = () => {
	frappe.call({
		method: "validate_workbook",
		doc: frm.doc,
		freeze: true,
		freeze_message: __("Validating workbook..."),
		callback(r) {
			frm.reload_doc().then(() => {
				if (r.message?.ok) {
					frappe.show_alert({
						message: __("Validation passed"),
						indicator: "green",
					});
				} else {
					frappe.msgprint({
						title: __("Validation Failed"),
						message: (r.message?.errors || []).join("<br>"),
						indicator: "red",
					});
				}
			});
		},
	});
	};

	if (frm.is_dirty()) {
		frm.save().then(run_validate);
	} else {
		run_validate();
	}
}

function run_workbook_import(frm) {
	const prompt =
		frm.doc.import_mode === "Full Workbook"
			? __("Run full workbook import (manifests, configurations, projects)?")
			: __("Run import and create/update projects?");

	frappe.confirm(prompt, () => {
		const queue_import = () => {
			frappe.call({
				method: "run_workbook_import",
				doc: frm.doc,
				freeze: true,
				freeze_message: __("Queueing import..."),
				callback() {
					frappe.show_alert({
						message: __("Import queued. Refresh shortly to see results."),
						indicator: "blue",
					});
					setTimeout(() => frm.reload_doc(), 3000);
				},
			});
		};

		if (frm.is_dirty()) {
			frm.save().then(queue_import);
		} else {
			queue_import();
		}
	});
}
