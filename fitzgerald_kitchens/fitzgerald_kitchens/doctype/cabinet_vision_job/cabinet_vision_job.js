// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

const CV_JOB_METHOD = "fitzgerald_kitchens.fitzgerald_kitchens.doctype.cabinet_vision_job.cabinet_vision_job";

frappe.ui.form.on("Cabinet Vision Job", {
	refresh(frm) {
		frm.add_custom_button(__("Download Export Script"), () => {
			window.open(`/api/method/${CV_JOB_METHOD}.download_export_script`);
		}, __("Cabinet Vision"));

		if (!frm.is_new()) {
			frm.add_custom_button(__("Cabinets"), () => {
				frappe.set_route("List", "Cabinet Vision Cabinet", { job: frm.doc.name });
			}, __("View"));
		}

		if (!frm.is_new() && frm.doc.export_file) {
			const label = frm.doc.import_status === "Imported" ? __("Import Again") : __("Import");
			frm.add_custom_button(label, () => import_export(frm)).addClass("btn-primary");
		}

		if (frm.is_new() || !frm.doc.export_file) {
			frm.set_intro(
				__("Run the export script (Cabinet Vision → Download Export Script) on the restored report database, attach the JSON file it makes to Export File, save, then click Import."),
				"blue"
			);
		} else if (frm.doc.import_status === "Failed") {
			frm.set_intro(__("The last import failed. Check the export file and try again."), "red");
		}
	},

	export_file(frm) {
		if (frm.doc.export_file && !frm.is_new()) {
			frm.save().then(() => import_export(frm));
		}
	},
});

function import_export(frm) {
	const run = () =>
		frappe
			.call({
				method: `${CV_JOB_METHOD}.import_export_file`,
				args: { job: frm.doc.name },
				freeze: true,
				freeze_message: __("Importing from Cabinet Vision..."),
			})
			.then((r) => {
				frm.reload_doc();
				if (r.message) frappe.show_alert({ message: r.message.summary, indicator: "green" }, 8);
			});

	if (frm.doc.import_status === "Imported") {
		frappe.confirm(
			__("Replace this job's rooms, cabinets and parts with the ones in the attached file? Cabinets with a BOM are kept."),
			run
		);
	} else {
		run();
	}
}
