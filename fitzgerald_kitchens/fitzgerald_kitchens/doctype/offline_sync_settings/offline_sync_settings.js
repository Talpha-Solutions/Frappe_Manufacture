// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Offline Sync Settings", {
	refresh(frm) {
		frm.set_query("ref_doctype", "doctypes", () => ({
			filters: {
				istable: 0,
				issingle: 0,
			},
		}));
		load_catalog_options(frm);

		frm.add_custom_button(__("Open Offline App"), () => {
			window.open("/offline", "_blank");
		}).addClass("btn-primary");

		frm.add_custom_button(__("Apply Phase 1 Defaults"), () => {
			frappe.call({
				method:
					"fitzgerald_kitchens.fitzgerald_kitchens.doctype.offline_sync_settings.offline_sync_settings.ensure_phase1_defaults",
				freeze: true,
				freeze_message: __("Applying Phase 1 defaults…"),
				callback(r) {
					if (!r.message) {
						return;
					}
					frappe.show_alert({
						message: __("Phase 1 ready: Customer, ToDo, and My Tasks (if Fitzgerald installed)."),
						indicator: "green",
					});
					frm.reload_doc();
				},
			});
		});
	},
});

frappe.ui.form.on("Offline Sync Feature", {
	feature(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.feature) {
			return;
		}
		let key = row.feature;
		if (key.indexOf(" — ") !== -1) {
			key = key.split(" — ")[0].trim();
			frappe.model.set_value(cdt, cdn, "feature", key);
		}
		frappe.call({
			method: "fitzgerald_kitchens.fitzgerald_kitchens.doctype.offline_sync_settings.offline_sync_settings.get_feature_details",
			args: { feature: key },
			callback(r) {
				if (!r.message) {
					return;
				}
				frappe.model.set_value(cdt, cdn, "label", r.message.label);
				frappe.model.set_value(cdt, cdn, "description", r.message.description);
				frappe.model.set_value(cdt, cdn, "route", r.message.route);
				frappe.model.set_value(cdt, cdn, "app_name", r.message.app_name);
			},
		});
	},
});

function load_catalog_options(frm) {
	frappe.call({
		method: "fitzgerald_kitchens.fitzgerald_kitchens.doctype.offline_sync_settings.offline_sync_settings.get_feature_pack_options",
		callback(r) {
			if (!r.message) {
				return;
			}
			const options = r.message.options || "";
			const grid = frm.fields_dict.features && frm.fields_dict.features.grid;
			if (!grid) {
				return;
			}
			grid.update_docfield_property("feature", "options", options);

			const lines = (r.message.features || []).map((f) => `${f.label} (${f.app_name})`);
			if (lines.length && frm.fields_dict.features) {
				frm.fields_dict.features.df.description =
					"Advanced packs — " + lines.join(" · ");
				frm.refresh_field("features");
			}
		},
	});
}
