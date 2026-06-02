// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

const SITE_PROJECT_TYPE = "Site";
const KITCHEN_PROJECT_TYPE = "Kitchen";

frappe.ui.form.on("Project", {
	refresh(frm) {
		toggle_unit_tab(frm);
		toggle_parent_unit(frm);
		setup_parent_project_query(frm);
		setup_work_order_create_menu(frm);
	},
	project_type(frm) {
		toggle_unit_tab(frm);
		toggle_parent_unit(frm);
		setup_work_order_create_menu(frm);
	},
});

function is_site_project(frm) {
	return frm.doc.project_type === SITE_PROJECT_TYPE;
}

function is_kitchen_project(frm) {
	return frm.doc.project_type === KITCHEN_PROJECT_TYPE;
}

function show_parent_unit(frm) {
	return !is_site_project(frm) && !is_kitchen_project(frm);
}

function toggle_unit_tab(frm) {
	frm.toggle_display("fk_unit_tab", !is_site_project(frm));
}

function toggle_parent_unit(frm) {
	const show = show_parent_unit(frm);
	frm.toggle_display("fk_parent_unit_project", show);
	if (!show && frm.doc.fk_parent_unit_project) {
		frm.set_value("fk_parent_unit_project", null);
	}
}

function setup_parent_project_query(frm) {
	frm.set_query("fk_parent_project", () => ({
		filters: { project_type: SITE_PROJECT_TYPE },
	}));

	frm.set_query("fk_parent_unit_project", () => ({
		filters: { project_type: KITCHEN_PROJECT_TYPE },
	}));
}

function setup_work_order_create_menu(frm) {
	if (frm.is_new() || is_site_project(frm)) {
		return;
	}

	if (!frm.doc.fk_effective_bom) {
		return;
	}

	frm.add_custom_button(
		__("Work Order"),
		() => create_work_order_from_effective_bom(frm),
		__("Create")
	);
	frm.page.set_inner_btn_group_as_primary(__("Create"));
}

function create_work_order_from_effective_bom(frm) {
	if (frm.is_new()) {
		frappe.msgprint(__("Save the Project before creating a Work Order."));
		return;
	}

	if (!frm.doc.fk_effective_bom) {
		frappe.msgprint(__("Set Effective BOM on the Unit tab first."));
		return;
	}

	frappe.call({
		method: "fitzgerald_kitchens.fitzgerald_kitchens.custom.project.create_work_order",
		args: {
			project: frm.doc.name,
			bom_no: frm.doc.fk_effective_bom,
			sales_order: frm.doc.sales_order || undefined,
		},
		freeze: true,
		freeze_message: __("Creating Work Order..."),
		callback(r) {
			if (!r.message) {
				return;
			}

			frm.set_value("fk_work_order", r.message);
			frappe.show_alert({
				message: __("Work Order {0} created", [r.message]),
				indicator: "green",
			});

			frm.save().then(() => {
				frappe.set_route("Form", "Work Order", r.message);
			});
		},
	});
}
