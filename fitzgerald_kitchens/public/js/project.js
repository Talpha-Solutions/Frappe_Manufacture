// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Project", {
	refresh(frm) {
		toggle_bom_tab_fields(frm);
		setup_work_order_create_menu(frm);
	},
	kitchen_required(frm) {
		toggle_bom_tab_fields(frm);
		if (!frm.is_new()) {
			frm.refresh();
		}
	},
	wardrobe_required(frm) {
		toggle_bom_tab_fields(frm);
		if (!frm.is_new()) {
			frm.refresh();
		}
	},
	kitchen_bom(frm) {
		if (!frm.is_new()) {
			frm.refresh();
		}
	},
	wardrobe_bom(frm) {
		if (!frm.is_new()) {
			frm.refresh();
		}
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

const KITCHEN_BOM_FIELDS = [
	"kitchen_type",
	"kitchen_specification",
	"kitchen_item",
	"kitchen_bom",
	"kitchen_work_order",
];

const WARDROBE_BOM_FIELDS = [
	"wardrobe_type",
	"wardrobe_specification",
	"wardrobe_item",
	"wardrobe_bom",
	"wardrobe_work_order",
];

const KITCHEN_WO_CONFIG = {
	bom_field: "kitchen_bom",
	item_field: "kitchen_item",
	work_order_field: "kitchen_work_order",
	button_label: __("Kitchen Work Order"),
	method: "fitzgerald_kitchens.fitzgerald_kitchens.custom.project.create_kitchen_work_order",
};

const WARDROBE_WO_CONFIG = {
	bom_field: "wardrobe_bom",
	item_field: "wardrobe_item",
	work_order_field: "wardrobe_work_order",
	button_label: __("Wardrobe Work Order"),
	method: "fitzgerald_kitchens.fitzgerald_kitchens.custom.project.create_wardrobe_work_order",
};

function toggle_bom_tab_fields(frm) {
	const show_kitchen = !!frm.doc.kitchen_required;
	const show_wardrobe = !!frm.doc.wardrobe_required;

	frm.toggle_display("kitchen_required", true);
	frm.toggle_display("wardrobe_required", true);
	frm.toggle_display("fk_bom_column_break_kitchen", true);
	frm.toggle_display("fk_bom_column_break_wardrobe", true);

	KITCHEN_BOM_FIELDS.forEach((fieldname) => {
		frm.toggle_display(fieldname, show_kitchen);
	});

	WARDROBE_BOM_FIELDS.forEach((fieldname) => {
		frm.toggle_display(fieldname, show_wardrobe);
	});

	frm.set_df_property("kitchen_type", "reqd", show_kitchen);
	frm.set_df_property("wardrobe_type", "reqd", show_wardrobe);
}

function setup_work_order_create_menu(frm) {
	if (frm.is_new()) {
		return;
	}

	const has_kitchen = frm.doc.kitchen_required && frm.doc.kitchen_bom;
	const has_wardrobe = frm.doc.wardrobe_required && frm.doc.wardrobe_bom;

	if (!has_kitchen && !has_wardrobe) {
		return;
	}

	let added = false;

	if (has_kitchen) {
		frm.add_custom_button(
			__("Kitchen Work Order"),
			() => create_work_order_from_bom(frm, KITCHEN_WO_CONFIG),
			__("Create")
		);
		added = true;
	}

	if (has_wardrobe) {
		frm.add_custom_button(
			__("Wardrobe Work Order"),
			() => create_work_order_from_bom(frm, WARDROBE_WO_CONFIG),
			__("Create")
		);
		added = true;
	}

	if (added) {
		frm.page.set_inner_btn_group_as_primary(__("Create"));
	}
}

function create_work_order_from_bom(frm, config) {
	if (frm.is_new()) {
		frappe.msgprint(__("Save the Project before creating a Work Order."));
		return;
	}

	if (!frm.doc[config.bom_field]) {
		frappe.msgprint(__("Select a BOM first."));
		return;
	}

	frappe.call({
		method: config.method,
		args: {
			project: frm.doc.name,
			bom_no: frm.doc[config.bom_field],
			item: frm.doc[config.item_field] || undefined,
			sales_order: frm.doc.sales_order || undefined,
		},
		freeze: true,
		freeze_message: __("Creating {0}...", [config.button_label]),
		callback(r) {
			if (!r.message) {
				return;
			}

			frm.set_value(config.work_order_field, r.message);
			frappe.show_alert({
				message: __("{0} {1} created", [config.button_label, r.message]),
				indicator: "green",
			});

			frm.save().then(() => {
				frappe.set_route("Form", "Work Order", r.message);
			});
		},
	});
}

function load_kitchen_bom_from_mapping(frm) {
	if (!frm.doc.kitchen_required || !frm.doc.kitchen_type || !frm.doc.kitchen_specification) {
		return;
	}

	frappe.call({
		method:
			"fitzgerald_kitchens.fitzgerald_kitchens.custom.project.get_kitchen_bom_from_mapping",
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
	if (!frm.doc.wardrobe_required || !frm.doc.wardrobe_type || !frm.doc.wardrobe_specification) {
		return;
	}

	frappe.call({
		method:
			"fitzgerald_kitchens.fitzgerald_kitchens.custom.project.get_wardrobe_bom_from_mapping",
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
