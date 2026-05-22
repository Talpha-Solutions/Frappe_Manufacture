// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Development Unit", {
	refresh(frm) {
		if (frm._loading_default_stages || (frm.doc.stages && frm.doc.stages.length)) {
			return;
		}
		load_default_stages(frm);
	},
	kitchen_type(frm) {
		load_kitchen_bom_from_mapping(frm);
	},
	kitchen_specification(frm) {
		load_kitchen_bom_from_mapping(frm);
	},
	wardrobe_type(frm) {
		load_wardrobe_bom_from_mapping(frm);
	},
	wardrobe_specification(frm) {
		load_wardrobe_bom_from_mapping(frm);
	},
});

function load_default_stages(frm) {
	frm._loading_default_stages = true;

	frappe.call({
		method:
			"fitzgerald_kitchens.fitzgerald_kitchens.doctype.development_unit.development_unit.get_default_stages",
		freeze: true,
		freeze_message: __("Loading standard stages..."),
		callback(r) {
			frm._loading_default_stages = false;

			if (frm.doc.stages && frm.doc.stages.length) {
				return;
			}

			if (!r.message || !r.message.length) {
				return;
			}

			r.message.forEach((row) => {
				const child = frm.add_child("stages");
				Object.assign(child, row);
			});
			frm.refresh_field("stages");
		},
	});
}

function load_kitchen_bom_from_mapping(frm) {
	if (!frm.doc.kitchen_type || !frm.doc.kitchen_specification) {
		return;
	}

	frappe.call({
		method:
			"fitzgerald_kitchens.fitzgerald_kitchens.doctype.development_unit.development_unit.get_kitchen_bom_from_mapping",
		args: {
			kitchen_type: frm.doc.kitchen_type,
			kitchen_specification: frm.doc.kitchen_specification,
		},
		callback(r) {
			const mapping = r.message;
			if (!mapping || !mapping.kitchen_bom) {
				frappe.show_alert({
					message: __("No Kitchen BOM Mapping found for this combination"),
					indicator: "orange",
				});
				return;
			}

			frm.set_value("kitchen_bom", mapping.kitchen_bom);
			if (mapping.kitchen_item) {
				frm.set_value("kitchen_item", mapping.kitchen_item);
			}
		},
	});
}

function load_wardrobe_bom_from_mapping(frm) {
	if (!frm.doc.wardrobe_type || !frm.doc.wardrobe_specification) {
		return;
	}

	frappe.call({
		method:
			"fitzgerald_kitchens.fitzgerald_kitchens.doctype.development_unit.development_unit.get_wardrobe_bom_from_mapping",
		args: {
			wardrobe_type: frm.doc.wardrobe_type,
			wardrobe_specification: frm.doc.wardrobe_specification,
		},
		callback(r) {
			const mapping = r.message;
			if (!mapping || !mapping.wardrobe_bom) {
				frappe.show_alert({
					message: __("No Wardrobe BOM Mapping found for this combination"),
					indicator: "orange",
				});
				return;
			}

			frm.set_value("wardrobe_bom", mapping.wardrobe_bom);
			if (mapping.wardrobe_item) {
				frm.set_value("wardrobe_item", mapping.wardrobe_item);
			}
		},
	});
}
