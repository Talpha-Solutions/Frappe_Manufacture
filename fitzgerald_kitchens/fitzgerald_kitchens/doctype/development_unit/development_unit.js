// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Development Unit", {
	refresh(frm) {
		toggle_bom_tab_fields(frm);
		setup_qr_code_actions(frm);
		render_qr_code_preview(frm);
		setup_stage_schedule_colors(frm);
		update_current_stage_from_stages(frm);
		render_current_stage_status(frm);

		if (frm._loading_default_stages || (frm.doc.stages && frm.doc.stages.length)) {
			return;
		}
		load_default_stages(frm);
	},
	on_tab_change(frm) {
		schedule_apply_stage_schedule_display(frm);
	},
	after_save(frm) {
		render_qr_code_preview(frm);
		schedule_apply_stage_schedule_display(frm);
		render_current_stage_status(frm);
	},
	kitchen_required(frm) {
		toggle_bom_tab_fields(frm);
	},
	wardrobe_required(frm) {
		toggle_bom_tab_fields(frm);
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

function render_qr_code_preview(frm) {
	const field = frm.get_field("qr_code_preview");
	if (!field) {
		return;
	}

	if (frm.is_new()) {
		field.$wrapper.html(
			`<p class="text-muted small">${__(
				"QR code will be generated when you save this document."
			)}</p>`
		);
		return;
	}

	if (!frm.doc.qr_code_image) {
		field.$wrapper.html(
			`<p class="text-muted small">${__(
				"Save the document to generate the QR code."
			)}</p>`
		);
		return;
	}

	const image_url = frappe.urllib.get_full_url(frm.doc.qr_code_image);
	field.$wrapper.html(`
		<div style="padding: 4px 0;">
			<img
				src="${image_url}"
				alt="${__("QR Code")}"
				style="display: block; max-width: 220px; width: 100%; height: auto; border: 1px solid var(--border-color); border-radius: var(--border-radius, 6px); padding: 12px; background: #fff;"
			/>
		</div>
	`);
}

function setup_qr_code_actions(frm) {
	if (frm.is_new() || !frm.doc.qr_code_image) {
		return;
	}

	frm.add_custom_button(__("Download QR Code"), () => download_qr_code(frm), __("Actions"));
}

function download_qr_code(frm) {
	if (!frm.doc.qr_code_image) {
		frappe.msgprint(__("Save the document to generate the QR code."));
		return;
	}

	const file_url = frappe.urllib.get_full_url(frm.doc.qr_code_image);

	fetch(file_url, { credentials: "include" })
		.then((response) => {
			if (!response.ok) {
				throw new Error(__("Could not download QR code image"));
			}
			return response.blob();
		})
		.then((blob) => {
			const object_url = URL.createObjectURL(blob);
			const link = document.createElement("a");
			link.href = object_url;
			link.download = `${frm.doc.name}-qr.png`;
			document.body.appendChild(link);
			link.click();
			link.remove();
			URL.revokeObjectURL(object_url);
		})
		.catch(() => {
			frappe.msgprint(__("Could not download QR code image"));
		});
}

function toggle_bom_tab_fields(frm) {
	const show_kitchen = !!frm.doc.kitchen_required;
	const show_wardrobe = !!frm.doc.wardrobe_required;

	// Checkboxes and column break must always stay visible (hiding the column
	// break hides the entire wardrobe column including Wardrobe Required).
	frm.toggle_display("kitchen_required", true);
	frm.toggle_display("wardrobe_required", true);
	frm.toggle_display("column_break_jfcu", true);

	KITCHEN_BOM_FIELDS.forEach((fieldname) => {
		frm.toggle_display(fieldname, show_kitchen);
	});

	WARDROBE_BOM_FIELDS.forEach((fieldname) => {
		frm.toggle_display(fieldname, show_wardrobe);
	});

	frm.set_df_property("kitchen_type", "reqd", show_kitchen);
	frm.set_df_property("wardrobe_type", "reqd", show_wardrobe);
}

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
			schedule_apply_stage_schedule_display(frm);
			update_current_stage_from_stages(frm);
		},
	});
}

const STAGE_ROW_COLOR_CLASSES =
	"stage-schedule-early stage-schedule-ontime stage-schedule-late";

const STAGE_ROW_COLOR_CLASS_MAP = {
	blue: "stage-schedule-early",
	green: "stage-schedule-ontime",
	red: "stage-schedule-late",
};

function setup_stage_schedule_colors(frm) {
	frm.set_indicator_formatter("stage", (doc) =>
		get_stage_schedule_indicator(doc, frm.doc.stages)
	);
	bind_stage_schedule_grid_hooks(frm);
	schedule_apply_stage_schedule_display(frm);
}

function bind_stage_schedule_grid_hooks(frm) {
	if (!frm._stage_schedule_grid_hooks_bound) {
		$(frm.wrapper).on("grid-row-render", (e, grid_row) => {
			if (grid_row?.doc?.parentfield !== "stages") {
				return;
			}
			apply_stage_row_color(grid_row, frm.doc.stages || []);
			refresh_stage_cell(grid_row);
		});
		frm._stage_schedule_grid_hooks_bound = true;
	}

	const grid = frm.fields_dict.stages?.grid;
	if (!grid || frm._stage_schedule_grid_change_bound) {
		return;
	}

	grid.wrapper.on("change.stage_schedule", () => {
		schedule_apply_stage_schedule_display(frm);
	});
	frm._stage_schedule_grid_change_bound = true;
}

function schedule_apply_stage_schedule_display(frm, attempt = 0) {
	clearTimeout(frm._stage_schedule_display_timer);
	const delay = attempt === 0 ? 0 : 150;

	frm._stage_schedule_display_timer = setTimeout(() => {
		bind_stage_schedule_grid_hooks(frm);
		apply_stage_row_colors(frm);
		refresh_stage_column_display(frm);
		render_current_stage_status(frm);

		const grid = frm.fields_dict.stages?.grid;
		const has_rows = grid?.grid_rows?.some((row) => row?.doc);
		if (!has_rows && attempt < 8) {
			schedule_apply_stage_schedule_display(frm, attempt + 1);
		}
	}, delay);
}

function stage_sort_key(doc) {
	return [cint(doc.sequence), cint(doc.idx)];
}

const ONGOING_STAGE_GAP_FRACTION = 0.5;

function gap_fill_fraction(status) {
	if (status === "Ongoing") {
		return ONGOING_STAGE_GAP_FRACTION;
	}
	return 0;
}

function next_non_cancelled_index(sorted_stages, after_index) {
	for (let index = after_index + 1; index < sorted_stages.length; index += 1) {
		if (sorted_stages[index].status !== "Cancelled") {
			return index;
		}
	}
	return null;
}

function get_stage_progress_percentage(stages) {
	const sorted = sort_stages(stages || []);
	if (!sorted.length) {
		return 0;
	}

	let last_completed_index = -1;
	sorted.forEach((row, index) => {
		if (row.status === "Completed") {
			last_completed_index = index;
		}
	});

	if (last_completed_index === -1) {
		const next_index = next_non_cancelled_index(sorted, -1);
		if (next_index === null) {
			return 0;
		}
		const next_row = sorted[next_index];
		const ceiling = flt(next_row.progress_percentage);
		const gap = Math.max(0, ceiling);
		return Math.min(100, gap * gap_fill_fraction(next_row.status));
	}

	const base = flt(sorted[last_completed_index].progress_percentage);
	const next_index = next_non_cancelled_index(sorted, last_completed_index);
	if (next_index === null) {
		return Math.min(100, base);
	}

	const next_row = sorted[next_index];
	const next_pct = flt(next_row.progress_percentage);
	const gap = Math.max(0, next_pct - base);
	return Math.min(100, base + gap * gap_fill_fraction(next_row.status));
}

function sort_stages(stages) {
	return [...stages].sort((a, b) => {
		const a_key = stage_sort_key(a);
		const b_key = stage_sort_key(b);
		if (a_key[0] !== b_key[0]) {
			return a_key[0] - b_key[0];
		}
		return a_key[1] - b_key[1];
	});
}

function update_current_stage_from_stages(frm) {
	const stages = frm.doc.stages || [];
	if (!stages.length) {
		return;
	}

	const sorted = sort_stages(stages);
	let last_completed_index = -1;

	sorted.forEach((row, index) => {
		if (row.status === "Completed") {
			last_completed_index = index;
		}
	});

	let current;
	if (last_completed_index === -1) {
		current = sorted[0];
	} else if (last_completed_index + 1 < sorted.length) {
		current = sorted[last_completed_index + 1];
	} else {
		current = sorted[last_completed_index];
	}

	if (!current?.stage) {
		return;
	}

	const progress = get_stage_progress_percentage(stages);
	if (frm.doc.current_stage !== current.stage) {
		frm.set_value("current_stage", current.stage);
	}
	if (frm.fields_dict.current_stage_progress && frm.doc.current_stage_progress !== progress) {
		frm.set_value("current_stage_progress", progress);
	}
	render_current_stage_status(frm);
}

function get_current_stage_row_from_frm(frm) {
	const stages = frm.doc.stages || [];
	if (!stages.length) {
		return null;
	}

	if (frm.doc.current_stage) {
		const match = stages.find((row) => row.stage === frm.doc.current_stage);
		if (match) {
			return match;
		}
	}

	const sorted = sort_stages(stages);
	let last_completed_index = -1;

	sorted.forEach((row, index) => {
		if (row.status === "Completed") {
			last_completed_index = index;
		}
	});

	if (last_completed_index === -1) {
		return sorted[0];
	}
	if (last_completed_index + 1 < sorted.length) {
		return sorted[last_completed_index + 1];
	}
	return sorted[last_completed_index];
}

function get_schedule_status_label(indicator) {
	return (
		{
			blue: __("Early"),
			green: __("On Time"),
			red: __("Late"),
		}[indicator] || ""
	);
}

function build_schedule_pill(label, indicator, options = {}) {
	const color = indicator || "gray";
	const text = frappe.utils.escape_html(label);
	const inner = `<span>${text}</span>`;

	if (options.href) {
		return `<a href="${options.href}" class="indicator-pill ${color} ellipsis current-stage-pill" style="color: inherit; text-decoration: none;">${inner}</a>`;
	}

	return `<span class="indicator-pill ${color} ellipsis current-stage-pill">${inner}</span>`;
}

function render_current_stage_status(frm) {
	const field = frm.get_field("current_stage");
	if (!field) {
		return;
	}

	const stage_row = get_current_stage_row_from_frm(frm);
	const stage_name = frm.doc.current_stage;
	const all_stages = frm.doc.stages || [];
	const indicator = stage_row ? get_stage_schedule_indicator(stage_row, all_stages) : "";
	const status_label = get_schedule_status_label(indicator);

	if (frm.fields_dict.current_stage_progress) {
		const progress = get_stage_progress_percentage(all_stages);
		if (frm.doc.current_stage_progress !== progress) {
			frm.set_value("current_stage_progress", progress);
		}
	}

	const $wrapper = field.$wrapper;
	const $value = $wrapper.find(".control-value, .like-disabled-input").first();
	if (!$value.length) {
		return;
	}

	$wrapper.addClass("current-stage-pill-field");

	if (!stage_name) {
		$value.html(`<span class="indicator-pill gray ellipsis"><span>${__("—")}</span></span>`);
		return;
	}

	const href = `/app/development-stage/${encodeURIComponent(stage_name)}`;
	const pills = [build_schedule_pill(stage_name, indicator, { href })];

	if (status_label && indicator) {
		pills.push(build_schedule_pill(status_label, indicator));
	}

	$value.html(
		`<div class="current-stage-pill-group">${pills.join("")}</div>`
	);
}

function is_later_stage(row, other) {
	const row_key = stage_sort_key(row);
	const other_key = stage_sort_key(other);
	return other_key[0] > row_key[0] || (other_key[0] === row_key[0] && other_key[1] > row_key[1]);
}

function has_later_completed_stage(doc, all_stages) {
	if (!all_stages?.length) {
		return false;
	}

	if (doc.status !== "Not Started" && doc.status !== "Ongoing") {
		return false;
	}

	return all_stages.some(
		(other) =>
			other.name !== doc.name &&
			is_later_stage(doc, other) &&
			other.status === "Completed"
	);
}

function get_stage_schedule_indicator(doc, all_stages) {
	if (has_later_completed_stage(doc, all_stages)) {
		return "red";
	}

	if (!doc?.planned_date) {
		return "";
	}

	const planned = frappe.datetime.str_to_obj(doc.planned_date);
	let compare;

	if (doc.status === "Completed" && doc.actual_completion_date) {
		compare = frappe.datetime.str_to_obj(doc.actual_completion_date);
	} else {
		compare = frappe.datetime.str_to_obj(frappe.datetime.get_today());
	}

	const day_diff = frappe.datetime.get_day_diff(compare, planned);
	if (day_diff < 0) {
		return "blue";
	}
	if (day_diff > 0) {
		return "red";
	}
	return "green";
}

function apply_stage_row_color(grid_row, all_stages) {
	if (!grid_row?.wrapper || !grid_row.doc) {
		return;
	}

	const indicator = get_stage_schedule_indicator(grid_row.doc, all_stages);
	const css_class = STAGE_ROW_COLOR_CLASS_MAP[indicator] || "";
	grid_row.wrapper
		.removeClass(STAGE_ROW_COLOR_CLASSES)
		.toggleClass(css_class, !!css_class);
}

function refresh_stage_cell(grid_row) {
	if (!grid_row?.doc?.stage) {
		return;
	}

	const df =
		grid_row.docfields?.find((field) => field.fieldname === "stage") ||
		frappe.meta.get_docfield("Development Unit Stage", "stage");

	if (!df || !grid_row.refresh_field) {
		return;
	}

	const txt = frappe.format(grid_row.doc.stage, df, null, grid_row.doc);
	grid_row.refresh_field("stage", txt);
}

function refresh_stage_column_display(frm) {
	const grid = frm.fields_dict.stages?.grid;
	if (!grid?.grid_rows?.length) {
		return;
	}

	grid.grid_rows.forEach((grid_row) => refresh_stage_cell(grid_row));
}

function apply_stage_row_colors(frm) {
	const grid = frm.fields_dict.stages?.grid;
	if (!grid?.grid_rows?.length) {
		return;
	}

	const all_stages = frm.doc.stages || [];
	grid.grid_rows.forEach((grid_row) => apply_stage_row_color(grid_row, all_stages));
}

function load_kitchen_bom_from_mapping(frm) {
	if (!frm.doc.kitchen_required || !frm.doc.kitchen_type || !frm.doc.kitchen_specification) {
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
	if (!frm.doc.wardrobe_required || !frm.doc.wardrobe_type || !frm.doc.wardrobe_specification) {
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
