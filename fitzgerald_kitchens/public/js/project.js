// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

const SITE_PROJECT_TYPE = "Site";
const KITCHEN_PROJECT_TYPE = "Kitchen";

const PROJECT_NAMING_SERIES = {
	[SITE_PROJECT_TYPE]: "PROJ-.####",
	Kitchen: "UNIT-KIT-.#####",
	Robe: "UNIT-ROB-.#####",
	Utility: "UNIT-UTL-.#####",
	"Vanity Unit": "UNIT-VAN-.#####",
	Pantry: "UNIT-PAN-.#####",
	Unit: "UNIT-UNT-.#####",
};

frappe.ui.form.on("Project", {
	refresh(frm) {
		toggle_unit_tab(frm);
		toggle_parent_unit(frm);
		setup_parent_project_query(frm);
	},
	project_type(frm) {
		toggle_unit_tab(frm);
		toggle_parent_unit(frm);
		apply_default_naming_series(frm);
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

function apply_default_naming_series(frm) {
	if (!frm.is_new() || !frm.doc.project_type) {
		return;
	}
	const series = PROJECT_NAMING_SERIES[frm.doc.project_type] || "UNIT-UNT-.#####";
	if (frm.doc.naming_series !== series) {
		frm.set_value("naming_series", series);
	}
}
