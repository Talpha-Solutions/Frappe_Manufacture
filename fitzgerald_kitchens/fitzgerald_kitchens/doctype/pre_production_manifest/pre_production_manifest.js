const METHOD_BASE =
	"fitzgerald_kitchens.fitzgerald_kitchens.doctype.pre_production_manifest.pre_production_manifest";
const EXCEL_METHOD =
	"fitzgerald_kitchens.fitzgerald_kitchens.utils.pre_production_manifest_excel.download_tender_excel";

frappe.ui.form.on("Pre Production Manifest", {
	setup(frm) {
		// the tender's party's own templates if they have any, otherwise those for everyone
		frm.set_query("template", () => ({
			query: "fitzgerald_kitchens.fitzgerald_kitchens.doctype.pre_production_manifest_template.pre_production_manifest_template.template_query",
			filters: { tender: frm.doc.pre_production_plan || "" },
		}));
	},
	async refresh(frm) {
		// "Create a new Pre Production Manifest Template" from the Template field starts it for the
		// tender's party (looked up now, as the option is used without waiting)
		load_tender_party(frm);
		frm.set_df_property("template", "get_route_options_for_new_doc", () => ({ ...(frm.__fk_tender_party || {}) }));
		frm.set_df_property(
			"template",
			"filter_description",
			__("Templates for this tender's Lead or Customer, or for everyone if they don't have their own")
		);
		render_top_intro(frm);
		add_download_button(frm);
		if (frm.is_new() && !frm.doc.naming_series) {
			frm.set_value("naming_series", "KC-.YYYY.-.#####");
		}
		recalculate_totals_from_rows(frm);
		await render_builder(frm);
	},
	async template(frm) {
		await load_template_rows(frm, true);
		recalculate_totals_from_rows(frm);
		await render_builder(frm);
	},
	async pre_production_plan(frm) {
		load_tender_party(frm);
		// a new manifest starts from its tender's defaults; anything already filled in is kept
		if (!frm.is_new() || !frm.doc.pre_production_plan) return;
		const { message: t } = await frappe.db.get_value("Pre Production Plan", frm.doc.pre_production_plan, [
			"tender_name",
			"template",
			"target_margin_pct",
		]);
		if (!t) return;
		for (const field of ["tender_name", "template", "target_margin_pct"]) {
			if (!frm.doc[field] && t[field]) await frm.set_value(field, t[field]);
		}
	},
	kitchens_to_tender(frm) {
		recalculate_totals_from_rows(frm);
	},
	target_margin_pct(frm) {
		recalculate_totals_from_rows(frm);
	},
});

async function load_tender_party(frm) {
	frm.__fk_tender_party = null;
	if (!frm.doc.pre_production_plan) return;
	const tender = frm.doc.pre_production_plan;
	const { message: t } = await frappe.db.get_value("Pre Production Plan", tender, ["party_type", "party_name"]);
	if (frm.doc.pre_production_plan !== tender || !t?.party_name) return;
	frm.__fk_tender_party = { party_type: t.party_type, party_name: t.party_name };
}

function add_download_button(frm) {
	if (frm.is_new()) return;
	const download = (simplified) => {
		// the file is built from the saved tender, so unsaved edits would be missing
		if (frm.is_dirty()) {
			frappe.msgprint(__("Save the tender first so the Excel matches what you see."));
			return;
		}
		const args = `name=${encodeURIComponent(frm.doc.name)}&simplified=${simplified ? 1 : 0}`;
		window.open(`/api/method/${EXCEL_METHOD}?${args}`);
	};
	// detailed: our costing bill; simplified: the client's copy, at tender price
	frm.add_custom_button(__("Detailed Excel"), () => download(false), __("Download"));
	frm.add_custom_button(__("Simplified Excel"), () => download(true), __("Download"));
}

function render_top_intro(frm) {
	const intro = frm.get_field("top_intro");
	if (!intro) return;
	intro.$wrapper.html(
		`<p class="text-muted" style="margin-bottom: 0;">${__(
			"Choose the items for one unit and where each one's cost comes from: a BOM for manufactured items, a price list or the last purchase rate for bought-in ones. Costs roll up into the totals below."
		)}</p>`
	);
}

const TAG_COLOURS = { MATERIAL: "blue", LABOUR: "orange", INDIRECT: "gray", FIXED: "purple" };

function title_case(value) {
	return (value || "").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
}

async function render_builder(frm) {
	// several renders can start together (a new manifest's template being set, then refresh; the
	// first save, then the route change to the new name); only the latest one is shown
	const render_id = (frm.__fk_render_id || 0) + 1;
	frm.__fk_render_id = render_id;
	const is_current = () => frm.__fk_render_id === render_id;

	const wrapper = frm.get_field("configuration_builder").$wrapper;
	let rows = await load_template_rows(frm, false);
	if (!is_current()) return;
	if (!rows.length) {
		wrapper.html(
			`<div class="text-muted text-center" style="padding: 40px 20px; border: 1px dashed var(--border-color); border-radius: var(--border-radius-md);">${__(
				"Select a Template to load configuration rows."
			)}</div>`
		);
		return;
	}

	const grouped = group_by_section(rows);
	const styleBlock = `
		<style>
			.fk-section-head { display: flex; align-items: center; gap: var(--margin-sm); margin: var(--margin-lg) 0 var(--margin-sm); font-size: var(--text-base); font-weight: var(--weight-semibold); color: var(--heading-color); }
			.fk-section-head:first-child { margin-top: 0; }
			.fk-section { border: 1px solid var(--border-color); border-radius: var(--border-radius-md); background: var(--fg-color); }
			.fk-cols, .fk-row { display: grid; grid-template-columns: 1.7fr 3fr 3fr 1.3fr 0.9fr 1.1fr 28px; column-gap: var(--margin-sm); align-items: center; padding: 0 var(--padding-sm); }
			.fk-cols { background: var(--subtle-fg); border-bottom: 1px solid var(--border-color); padding-top: var(--padding-xs); padding-bottom: var(--padding-xs); font-size: var(--text-sm); color: var(--text-muted); border-radius: var(--border-radius-md) var(--border-radius-md) 0 0; }
			.fk-row { row-gap: var(--padding-xs); padding-top: var(--padding-sm); padding-bottom: var(--padding-sm); border-bottom: 1px solid var(--border-color); }
			.fk-row:last-child { border-bottom: none; }
			.fk-row .frappe-control.form-group { margin-bottom: 0; }
			.fk-item-ctl .awesomplete > ul { min-width: 320px !important; }
			/* under the rate: its unit, or the source's rate and "reset" once changed for this tender */
			.fk-rate { margin-top: 2px; font-size: var(--text-xs); color: var(--text-muted); white-space: nowrap; }
			.fk-rate:empty { display: none; }
			.fk-rate-edited input { font-weight: var(--weight-medium); }
			.fk-rate-reset { margin-left: 4px; cursor: pointer; }
			.fk-label { font-size: var(--text-md); font-weight: var(--weight-medium); color: var(--text-color); line-height: 1.3; }
			.fk-sub { font-size: var(--text-sm); color: var(--text-muted); line-height: 1.3; }
			.fk-amount, .fk-cols .col-amount { text-align: right; font-variant-numeric: tabular-nums; }
			.fk-amount { color: var(--text-color); font-weight: var(--weight-medium); white-space: nowrap; }
			.fk-cost-ctl input:disabled { color: var(--text-muted); }
			.fk-cost-hint { margin-top: 2px; font-size: var(--text-xs); color: var(--text-muted); }
			.fk-cost-hint a { color: var(--text-muted); border-bottom: 1px dotted var(--text-muted); cursor: pointer; }
			.fk-cost-hint a:hover { color: var(--text-color); }
			.fk-cost-ctl .awesomplete > ul { min-width: 320px !important; }
			.fk-remark-btn, .fk-remark-remove { width: 28px; height: 28px; padding: 0; border: none; border-radius: var(--border-radius); background: transparent; color: var(--text-muted); display: flex; align-items: center; justify-content: center; }
			.fk-remark-btn { opacity: 0; transition: opacity 0.15s; }
			.fk-row:hover .fk-remark-btn, .fk-remark-btn:focus-visible { opacity: 1; }
			.fk-remark-btn:hover, .fk-remark-remove:hover { background: var(--fg-hover-color); color: var(--text-color); }
			.fk-has-remark .fk-remark-btn { opacity: 1; color: var(--primary-color); }
			@media (hover: none) { .fk-remark-btn { opacity: 1; } }
			/* always shown under the item once it has a remark; otherwise only when opened via the button */
			.fk-remark-wrap { display: none; grid-column: 1 / -1; align-items: center; gap: var(--margin-xs); }
			.fk-remark { flex: 1; font-size: var(--text-sm) !important; }
			.fk-has-remark .fk-remark-wrap, .fk-remark-open .fk-remark-wrap, .fk-remark-wrap:focus-within { display: flex; }
			.fk-remark-remove { display: none; }
			.fk-has-remark .fk-remark-remove { display: flex; }
			/* charges have a note button next to remove, so their last column is wider */
			.fk-cols.fk-charge-cols, .fk-row.fk-charge-row { grid-template-columns: 1.7fr 3fr 3fr 1.3fr 0.9fr 1.1fr 60px; }
			.fk-charge-actions { display: flex; gap: 2px; }
			.fk-other-empty { padding: var(--padding-sm); color: var(--text-muted); font-size: var(--text-sm); }
			.fk-other-add { margin-top: var(--margin-sm); }
			.fk-charge-remove { width: 28px; height: 28px; padding: 0; border: none; border-radius: var(--border-radius); background: transparent; color: var(--text-muted); display: flex; align-items: center; justify-content: center; }
			.fk-charge-remove:hover { background: var(--fg-hover-color); color: var(--text-color); }
			.fk-footer { display: flex; justify-content: flex-end; align-items: baseline; gap: var(--margin-sm); margin-top: var(--margin-md); padding: var(--padding-sm) var(--padding-md); border: 1px solid var(--border-color); border-radius: var(--border-radius-md); background: var(--subtle-fg); }
			.fk-footer .label { color: var(--text-muted); font-size: var(--text-sm); }
			.fk-footer .value { color: var(--heading-color); font-size: var(--text-lg); font-weight: var(--weight-semibold); font-variant-numeric: tabular-nums; }
		</style>
	`;

	let html = `${styleBlock}<div class="fk-builder">`;

	for (const [sectionName, sectionRows] of Object.entries(grouped)) {
		const tag = sectionRows[0]?.tag || "";
		const qtyLabel = sectionRows[0]?.qty_label || "QTY";
		const pill = tag
			? `<span class="indicator-pill no-indicator-dot ${TAG_COLOURS[tag] || "gray"}">${escape_html(title_case(tag))}</span>`
			: "";
		html += `
			<div class="fk-section-head">${escape_html(title_case(sectionName))}${pill}</div>
			<div class="fk-section">
				<div class="fk-cols">
					<div>${__("Item")}</div>
					<div>${__("Selection")}</div>
					<div>${__("Cost From")}</div>
					<div>${__("Rate")}</div>
					<div>${escape_html(qtyLabel === "QTY" ? __("Qty") : qtyLabel)}</div>
					<div class="col-amount">${__("Cost (€)")}</div>
					<div></div>
				</div>
		`;

		for (const row of sectionRows) {
			html += `
				<div class="fk-row${row.remark ? " fk-has-remark" : ""}" data-row-key="${escape_html(get_row_key(row))}">
					<div>
						<div class="fk-label">${escape_html(row.label || "")}</div>
						<div class="fk-sub">${escape_html(row.subtitle || "")}</div>
					</div>
					<div class="fk-item-ctl"></div>
					<div><div class="fk-cost-ctl"></div><div class="fk-cost-hint"></div></div>
					<div><div class="fk-rate-ctl"></div><div class="fk-rate">${rate_html(row)}</div></div>
					<div class="fk-qty-ctl"></div>
					<div class="fk-amount">${format_currency(flt(row.amount || 0))}</div>
					<button type="button" class="fk-remark-btn" title="${__("Add / edit remark")}">${frappe.utils.icon("small-message", "sm")}</button>
					<div class="fk-remark-wrap">
						<input class="fk-remark form-control" type="text" placeholder="${__("Add a remark")}" value="${escape_html(row.remark || "")}" />
						<button type="button" class="fk-remark-remove" title="${__("Remove remark")}">${frappe.utils.icon("close", "sm")}</button>
					</div>
				</div>
			`;
		}

		html += `</div>`;
	}

	// user-added charges, per unit, counted in the tender price
	html += `
		<div class="fk-section-head">${__("Other Costs")}<span class="indicator-pill no-indicator-dot gray">${__("Per unit")}</span></div>
		<div class="fk-section">
			<div class="fk-cols fk-charge-cols">
				<div>${__("Description")}</div>
				<div>${__("Item (optional)")}</div>
				<div></div>
				<div>${__("Rate")}</div>
				<div>${__("Qty")}</div>
				<div class="col-amount">${__("Cost (€)")}</div>
				<div></div>
			</div>
			<div class="fk-other-rows"></div>
		</div>
		<div class="fk-other-add"><button type="button" class="btn btn-xs btn-default">${__("+ Add charge")}</button></div>
	`;

	html += `
		<div class="fk-footer">
			<span class="label">${__("Total per Unit")}</span>
			<span class="fk-total-per-kitchen value">${format_currency(flt(frm.doc.total_cost_per_kitchen || 0))}</span>
		</div>
	</div>`;
	// built off-screen and swapped in once every control is bound, so the builder appears whole
	// instead of filling in row by row
	const $builder = $("<div>").html(html);
	if (!wrapper.children().length) {
		wrapper.html(`<div class="text-muted text-center" style="padding: 40px 20px;">${__("Loading...")}</div>`);
	}
	await bind_row_events(frm, rows, $builder, is_current);
	if (!is_current()) return;
	render_other_costs(frm, $builder);
	wrapper.empty().append($builder);
}

function parse_other_costs(frm) {
	return parse_rows(frm.doc.other_costs_json);
}

function save_other_costs(frm, charges) {
	if (JSON.stringify(charges) !== JSON.stringify(parse_other_costs(frm))) {
		frm.set_value("other_costs_json", JSON.stringify(charges));
	}
	recalculate_totals_from_rows(frm);
}

// Other Costs section: free rows the user adds, each a per-unit charge
function render_other_costs(frm, wrapper) {
	const charges = parse_other_costs(frm);
	const $rows = wrapper.find(".fk-other-rows").empty();
	if (!charges.length) {
		$rows.html(`<div class="fk-other-empty">${__("No other costs. Use + Add charge for anything the template doesn't cover.")}</div>`);
	}

	charges.forEach((charge, index) => {
		const $row = $(`
			<div class="fk-row fk-charge-row${charge.remark ? " fk-has-remark" : ""}">
				<div class="fk-charge-desc"></div>
				<div class="fk-charge-item"></div>
				<div></div>
				<div class="fk-charge-rate"></div>
				<div class="fk-charge-qty"></div>
				<div class="fk-amount">${format_currency(flt(charge.amount))}</div>
				<div class="fk-charge-actions">
					<button type="button" class="fk-remark-btn" title="${__("Add / edit note")}">${frappe.utils.icon("small-message", "sm")}</button>
					<button type="button" class="fk-charge-remove" title="${__("Remove charge")}">${frappe.utils.icon("close", "sm")}</button>
				</div>
				<div class="fk-remark-wrap">
					<input class="fk-remark form-control" type="text" placeholder="${__("Add a note")}" value="${escape_html(charge.remark || "")}" />
					<button type="button" class="fk-remark-remove" title="${__("Remove note")}">${frappe.utils.icon("close", "sm")}</button>
				</div>
			</div>
		`).appendTo($rows);

		const update = () => {
			charge.amount = flt(charge.qty) * flt(charge.rate);
			$row.find(".fk-amount").text(format_currency(charge.amount));
			save_other_costs(frm, charges);
		};

		const descControl = make_row_control($row.find(".fk-charge-desc"), {
			fieldtype: "Data",
			fieldname: "description",
			placeholder: __("e.g. Skip hire, out-of-hours fitting"),
			change: () => {
				if (descControl.__fk_silent) return;
				charge.description = descControl.get_value() || "";
				save_other_costs(frm, charges);
			},
		});
		const rateControl = make_row_control($row.find(".fk-charge-rate"), {
			fieldtype: "Currency",
			fieldname: "rate",
			non_negative: 1,
			change: () => {
				if (rateControl.__fk_silent) return;
				charge.rate = flt(rateControl.get_value());
				update();
			},
		});
		const qtyControl = make_row_control($row.find(".fk-charge-qty"), {
			fieldtype: "Float",
			fieldname: "qty",
			non_negative: 1,
			change: () => {
				if (qtyControl.__fk_silent) return;
				charge.qty = flt(qtyControl.get_value());
				update();
			},
		});
		const itemControl = make_row_control($row.find(".fk-charge-item"), {
			fieldtype: "Link",
			fieldname: "item_code",
			options: "Item",
			placeholder: __("Optional"),
			get_query: () => ({ filters: { disabled: 0, has_variants: 0 } }),
			change: async () => {
				if (itemControl.__fk_silent) return;
				charge.item_code = itemControl.get_value() || "";
				if (charge.item_code) {
					// fill the description and rate from the item; both stay editable
					const [item, price] = await Promise.all([
						frappe.db.get_value("Item", charge.item_code, "item_name"),
						frappe.db.get_value(
							"Item Price",
							{ item_code: charge.item_code, price_list: "Standard Selling" },
							"price_list_rate"
						),
					]);
					if (!charge.description) {
						charge.description = item.message?.item_name || charge.item_code;
						await set_silently(descControl, charge.description);
					}
					if (price.message?.price_list_rate != null) {
						charge.rate = flt(price.message.price_list_rate);
						await set_silently(rateControl, charge.rate);
					}
				}
				update();
			},
		});

		set_silently(descControl, charge.description || "");
		set_silently(itemControl, charge.item_code || "");
		set_silently(rateControl, flt(charge.rate));
		set_silently(qtyControl, flt(charge.qty));

		// note: same behaviour as the remarks on template rows
		const note = $row.find(".fk-remark");
		$row.find(".fk-remark-btn").on("click", () => {
			$row.addClass("fk-remark-open");
			note.trigger("focus");
		});
		note.on("input", (e) => {
			charge.remark = e.target.value;
			save_other_costs(frm, charges);
		});
		note.on("blur", () => {
			charge.remark = (charge.remark || "").trim();
			note.val(charge.remark);
			$row.removeClass("fk-remark-open").toggleClass("fk-has-remark", !!charge.remark);
			save_other_costs(frm, charges);
		});
		$row.find(".fk-remark-remove").on("click", () => {
			charge.remark = "";
			note.val("");
			$row.removeClass("fk-remark-open fk-has-remark");
			save_other_costs(frm, charges);
		});

		$row.find(".fk-charge-remove").on("click", () => {
			charges.splice(index, 1);
			save_other_costs(frm, charges);
			render_other_costs(frm, wrapper);
		});
	});

	wrapper
		.find(".fk-other-add button")
		.off("click")
		.on("click", () => {
			charges.push({ description: "", item_code: "", qty: 1, rate: 0, amount: 0 });
			save_other_costs(frm, charges);
			render_other_costs(frm, wrapper);
			wrapper.find(".fk-other-rows .fk-row:last .fk-charge-desc input").trigger("focus");
		});
}

async function load_template_rows(frm, forceReload) {
	let rows = parse_rows(frm.doc.config_rows_json);
	if (!frm.doc.template) {
		return [];
	}
	if (rows.length && !forceReload) {
		// follow the current template's row details (group, labels); in the browser
		// only, so opening a tender doesn't mark it changed. The server applies the same on save.
		const r = await frappe.call({
			method: `${METHOD_BASE}.get_template_rows`,
			args: { template: frm.doc.template },
		});
		const current = {};
		for (const t of r.message || []) current[get_row_key(t)] = t;
		for (const row of rows) {
			const t = current[get_row_key(row)];
			if (!t) continue;
			for (const field of ["tag", "subtitle", "item_group", "qty_label"]) {
				row[field] = t[field];
			}
		}
	}
	if (!rows.length || forceReload) {
		const r = await frappe.call({
			method: `${METHOD_BASE}.get_template_rows`,
			args: { template: frm.doc.template },
		});
		rows = (r.message || []).map((row) => ({
			...row,
			item_code: "",
			cost_from: "",
			bom: "",
			price_row: "",
			price_list: "",
			rate: 0,
			list_rate: 0,
			rate_override: 0,
			currency: "",
			uom: "",
			amount: 0,
		}));
		save_rows(frm, rows);
	}
	return rows;
}

async function bind_row_events(frm, rows, wrapper, is_current = () => true) {
	// every row's cost options in one call
	const costOptions = await fetch_cost_options(rows.map((r) => r.item_code));
	if (!is_current()) return;

	// rows don't depend on each other, so they're bound side by side
	const rematched = [];
	const elements = wrapper.find(".fk-row").toArray();
	await Promise.all(elements.map((el) => bind_row(el)));
	if (rematched.length) {
		save_rows(frm, rows);
		frappe.show_alert({
			message: __("Cost source updated to suit the item for: {0}. Save to keep it.", [rematched.join(", ")]),
			indicator: "orange",
		}, 10);
	}

	async function bind_row(el) {
		const $row = $(el);
		const key = $row.attr("data-row-key");
		const row = rows.find((r) => get_row_key(r) === key);
		if (!row) return;

		let rateControl = null;
		const show_cost = () => {
			row.amount = flt(row.qty) * flt(row.rate);
			$row.find(".fk-amount").text(format_currency(row.amount));
			$row.find(".fk-rate").html(rate_html(row));
			$row.find(".fk-rate-ctl").toggleClass("fk-rate-edited", !!row.rate_override);
			if (rateControl) {
				set_silently(rateControl, flt(row.rate));
				rateControl.$input.prop("disabled", !row.item_code);
			}
		};

		// an item that has changed type since the row was costed (e.g. now Manufacture, but the row
		// still uses a selling price) moves to its default source; the server does the same on save
		const options = costOptions[row.item_code];
		if (row.item_code && options && (options.manufactured ? !row.bom : !!row.bom)) {
			const choice = default_cost_choice(cost_choices({ item_code: row.item_code }, options));
			if (choice.value || cost_value(row)) {
				apply_cost_choice(row, choice);
				show_cost();
				rematched.push(row.label);
			}
		}

		// Cost From: a Link, like any other in Frappe (search, "Create a new …", Advanced Search):
		// a manufactured item's BOMs, or a bought-in item's prices in any price list. A bought-in
		// item can use its last purchase rate instead, from the link under it.
		const is_manufactured = () => !!costOptions[row.item_code]?.manufactured;
		const $hint = $row.find(".fk-cost-hint");
		const costControl = make_row_control($row.find(".fk-cost-ctl"), {
			fieldtype: "Link",
			fieldname: "cost_source",
			options: "BOM",
			get_query: () =>
				is_manufactured()
					? { query: `${METHOD_BASE}.bom_query`, filters: { item: row.item_code || "" } }
					: { query: `${METHOD_BASE}.item_price_query`, filters: { item_code: row.item_code || "" } },
			// a new BOM or price starts for this row's item
			get_route_options_for_new_doc: () =>
				is_manufactured()
					? { item: row.item_code }
					: { item_code: row.item_code, price_list: "Standard Buying" },
			change: async () => {
				if (costControl.__fk_silent) return;
				const value = costControl.get_value() || "";
				if (value === ((is_manufactured() ? row.bom : row.price_row) || "")) return;
				if (!value) {
					apply_cost_choice(row, { value: "" });
				} else {
					// e.g. a BOM or price created from the dropdown since the row loaded
					let choice = find_cost_choice(row, costOptions[row.item_code], value);
					if (!choice) {
						Object.assign(costOptions, await fetch_cost_options([row.item_code]));
						choice = find_cost_choice(row, costOptions[row.item_code], value);
					}
					if (!choice) {
						frappe.show_alert({
							message: is_manufactured()
								? __("BOM {0} isn't submitted and active, so it can't cost this row yet. Submit it, then pick it here.", [value])
								: __("{0} isn't a price of {1}.", [value, row.item_code]),
							indicator: "orange",
						}, 8);
						await refresh_cost_control();
						return;
					}
					apply_cost_choice(row, choice);
				}
				await refresh_cost_control();
				show_cost();
				save_rows(frm, rows);
			},
		});
		// Item Price names are random, so the link (and each option in its dropdown) shows
		// "Standard Buying · € 120.00 / Nos" instead
		costControl.is_title_link = () => costControl.df.options === "Item Price";
		const merge_duplicates = costControl.merge_duplicates.bind(costControl);
		costControl.merge_duplicates = (results) =>
			merge_duplicates(results).map((d) =>
				costControl.df.options === "Item Price" && d.description ? { ...d, label: d.description, description: "" } : d
			);

		const refresh_cost_control = async () => {
			const options = costOptions[row.item_code];
			const manufactured = is_manufactured();
			costControl.df.options = manufactured ? "BOM" : "Item Price";
			costControl.df.filter_description = manufactured
				? __("Submitted, active BOMs of {0}", [row.item_code])
				: __("Prices of {0} in any price list", [row.item_code]);
			for (const price of options?.prices || []) {
				frappe.utils.add_link_title("Item Price", price.price_row, cost_label(price.price_list, price.rate, price.currency, price.uom || options.stock_uom));
			}
			const lpr = options && cost_label(__("Last purchase rate"), options.last_purchase_rate, default_currency(), options.stock_uom);
			let placeholder = __("Select an item first");
			if (row.item_code && manufactured) placeholder = options?.boms.length ? __("Select BOM") : __("No active BOM yet");
			else if (row.item_code && row.cost_from === "Last Purchase Rate") placeholder = lpr;
			else if (row.item_code) placeholder = __("Select price");
			costControl.$input.attr("placeholder", placeholder).prop("disabled", !row.item_code);
			await set_silently(costControl, (manufactured ? row.bom : row.price_row) || "");

			// a bought-in item can be costed at its last purchase rate instead of a price
			const offer_lpr = row.item_code && options && !manufactured && row.cost_from !== "Last Purchase Rate";
			$hint.toggle(!!offer_lpr).html(
				offer_lpr
					? `<a class="fk-use-lpr">${__("Use last purchase rate")}</a> <span>(${
							flt(options.last_purchase_rate) ? escape_html(format_currency(options.last_purchase_rate, default_currency())) : __("none yet")
					  })</span>`
					: ""
			);
		};
		$hint.on("click", ".fk-use-lpr", async () => {
			const choice = find_cost_choice(row, costOptions[row.item_code], "lpr");
			if (!choice) return;
			apply_cost_choice(row, choice);
			await refresh_cost_control();
			show_cost();
			save_rows(frm, rows);
		});
		await refresh_cost_control();

		const itemControl = make_row_control($row.find(".fk-item-ctl"), {
			fieldtype: "Link",
			fieldname: "item_code",
			options: "Item",
			placeholder: __("Select item"),
			filter_description: __("{0} items", [row.item_group]),
			get_query: () => ({ filters: { item_group: row.item_group, disabled: 0, has_variants: 0 } }),
			change: async () => {
				if (itemControl.__fk_silent) return;
				const code = itemControl.get_value() || "";
				if (code === (row.item_code || "")) return;
				if (code && !costOptions[code]) Object.assign(costOptions, await fetch_cost_options([code]));
				row.item_code = code;
				// a different item starts from its own default cost source (and its own rate)
				apply_cost_choice(row, default_cost_choice(cost_choices({ item_code: code }, costOptions[code])));
				await refresh_cost_control();
				show_cost();
				save_rows(frm, rows);
			},
		});
		await set_silently(itemControl, row.item_code || "");

		const qtyControl = make_row_control($row.find(".fk-qty-ctl"), {
			fieldtype: "Float",
			fieldname: "qty",
			non_negative: 1,
			change: () => {
				if (qtyControl.__fk_silent) return;
				row.qty = flt(qtyControl.get_value());
				show_cost();
				save_rows(frm, rows);
			},
		});
		await set_silently(qtyControl, flt(row.qty));

		// rate: change it for this tender (kept on save); "reset" goes back to the cost source's rate
		if (row.list_rate === undefined) row.list_rate = row.rate;
		const apply_rate = (rate, override) => {
			row.rate = flt(rate);
			row.rate_override = override && row.rate !== flt(row.list_rate) ? 1 : 0;
			show_cost();
			save_rows(frm, rows);
		};
		rateControl = make_row_control($row.find(".fk-rate-ctl"), {
			fieldtype: "Currency",
			fieldname: "rate",
			non_negative: 1,
			change: () => {
				if (rateControl.__fk_silent) return;
				apply_rate(rateControl.get_value(), true);
			},
		});
		$row.find(".fk-rate").on("click", ".fk-rate-reset", () => apply_rate(row.list_rate, false));
		show_cost();

		const remark = $row.find(".fk-remark");
		$row.find(".fk-remark-btn").on("click", () => {
			$row.addClass("fk-remark-open");
			remark.trigger("focus");
		});

		remark.on("input", (e) => {
			row.remark = e.target.value;
			save_rows(frm, rows);
		});

		remark.on("blur", () => {
			row.remark = (row.remark || "").trim();
			remark.val(row.remark);
			$row.removeClass("fk-remark-open").toggleClass("fk-has-remark", !!row.remark);
			save_rows(frm, rows);
		});

		$row.find(".fk-remark-remove").on("click", () => {
			row.remark = "";
			remark.val("");
			$row.removeClass("fk-remark-open fk-has-remark");
			save_rows(frm, rows);
		});
	}
}

// {item_code: {stock_uom, boms, prices, last_purchase_rate}} for the given items
async function fetch_cost_options(itemCodes) {
	const codes = [...new Set(itemCodes.filter(Boolean))];
	if (!codes.length) return {};
	const r = await frappe.call({ method: `${METHOD_BASE}.get_cost_options`, args: { item_codes: codes } });
	return r.message || {};
}

function default_currency() {
	return frappe.defaults.get_default("currency") || frappe.boot.sysdefaults?.currency || "";
}

// the Cost From choices for a row's item: its BOMs if it's manufactured (Default Material Request
// Type "Manufacture"), otherwise each price list it has a price in and its last purchase rate
function cost_choices(row, options) {
	if (!row.item_code) return [{ value: "", label: __("Select an item first") }];
	const money = (rate, currency, uom) => `${format_currency(flt(rate), currency)}${uom ? ` / ${uom}` : ""}`;
	const choices = [];
	if (options?.manufactured) {
		for (const bom of options.boms) {
			choices.push({
				value: `bom:${bom.name}`,
				label: `${bom.name}${bom.is_default ? ` (${__("default")})` : ""} · ${money(bom.unit_cost, bom.currency, options.stock_uom)}`,
				cost_from: "BOM",
				bom: bom.name,
				rate: bom.unit_cost,
				currency: bom.currency,
				uom: options.stock_uom,
				is_default: bom.is_default,
			});
		}
	} else if (options) {
		for (const price of options.prices) {
			choices.push({
				value: `price:${price.price_row}`,
				label: `${price.price_list} · ${money(price.rate, price.currency, price.uom)}`,
				cost_from: "Price List",
				price_row: price.price_row,
				price_list: price.price_list,
				rate: price.rate,
				currency: price.currency,
				uom: price.uom || options.stock_uom,
				buying: price.buying,
			});
		}
		choices.push({
			value: "lpr",
			label: `${__("Last Purchase Rate")} · ${
				options.last_purchase_rate ? money(options.last_purchase_rate, default_currency(), options.stock_uom) : __("none yet")
			}`,
			cost_from: "Last Purchase Rate",
			rate: options.last_purchase_rate,
			currency: default_currency(),
			uom: options.stock_uom,
		});
	}
	// keep what the row already uses, even if it's no longer offered (e.g. a price on an item that has
	// since got a BOM), so opening the manifest never changes its cost
	const current = cost_value(row);
	if (current && !choices.some((c) => c.value === current)) {
		choices.unshift({
			value: current,
			label: `${row.bom || row.price_list || __(row.cost_from)} · ${money(row.list_rate ?? row.rate, row.currency, row.uom)}`,
			cost_from: row.cost_from || (row.bom ? "BOM" : "Price List"),
			bom: row.bom,
			price_row: row.price_row,
			price_list: row.price_list,
			rate: row.list_rate ?? row.rate,
			currency: row.currency,
			uom: row.uom,
		});
	}
	if (!current) {
		const label = options?.manufactured && !options.boms.length ? __("No active BOM yet") : __("Not costed");
		choices.unshift({ value: "", label });
	}
	return choices;
}

// "Standard Buying · € 120.00 / Nos"
function cost_label(source, rate, currency, uom) {
	return `${source} · ${format_currency(flt(rate), currency)}${uom ? ` / ${uom}` : ""}`;
}

// the choice for a BOM name, an Item Price name or "lpr", from the item's cost options
function find_cost_choice(row, options, value) {
	if (!options) return null;
	const key = value === "lpr" ? "lpr" : options.manufactured ? `bom:${value}` : `price:${value}`;
	return cost_choices({ item_code: row.item_code }, options).find((c) => c.value === key) || null;
}

// the row's current choice, as a Cost From value
function cost_value(row) {
	if (row.bom) return `bom:${row.bom}`;
	if (row.price_row) return `price:${row.price_row}`;
	if (row.cost_from === "Last Purchase Rate") return "lpr";
	return "";
}

// for a newly picked item: its default BOM; else a buying price, its last purchase rate, any price
function default_cost_choice(choices) {
	const real = choices.filter((c) => c.value);
	return (
		real.find((c) => c.bom && c.is_default) ||
		real.find((c) => c.bom) ||
		real.find((c) => c.price_row && c.buying) ||
		real.find((c) => c.value === "lpr" && flt(c.rate)) ||
		real.find((c) => c.price_row) ||
		real.find((c) => c.value === "lpr") || { value: "" }
	);
}

function apply_cost_choice(row, choice) {
	row.cost_from = choice.cost_from || "";
	row.bom = choice.bom || "";
	row.price_row = choice.price_row || "";
	row.price_list = choice.price_list || "";
	row.currency = choice.currency || "";
	row.uom = choice.uom || "";
	row.list_rate = flt(choice.rate);
	row.rate = row.list_rate;
	row.rate_override = 0;
}

function make_row_control($parent, df) {
	const control = frappe.ui.form.make_control({
		df,
		parent: $parent.get(0),
		render_input: true,
		only_input: true,
		// keep Link fields' open / clear buttons, which only_input would otherwise drop
		with_link_btn: df.fieldtype === "Link",
	});
	control.refresh();
	return control;
}

// set a control's value from code without running its change handler
async function set_silently(control, value) {
	control.__fk_silent = true;
	try {
		await control.set_value(value);
	} finally {
		control.__fk_silent = false;
	}
}

// under the rate: its unit; once changed for this tender, the cost source's rate and a reset link
function rate_html(row) {
	if (!row.item_code) return "";
	if (row.rate_override) {
		return `<span title="${__("Rate changed for this tender")}">${__("was {0}", [escape_html(format_currency(flt(row.list_rate), row.currency))])}</span>
			<a class="fk-rate-reset">${__("reset")}</a>`;
	}
	return row.uom ? escape_html(__("per {0}", [row.uom])) : "";
}

function get_row_key(row) {
	return `${row.section || ""}::${row.label || ""}`;
}

function group_by_section(rows) {
	const grouped = {};
	for (const row of rows) {
		const key = row.section || "ITEMS";
		if (!grouped[key]) grouped[key] = [];
		grouped[key].push(row);
	}
	return grouped;
}

function parse_rows(value) {
	if (!value) return [];
	try {
		const rows = JSON.parse(value);
		return Array.isArray(rows) ? rows : [];
	} catch (e) {
		return [];
	}
}

function save_rows(frm, rows) {
	// the server stores this JSON with Python's spacing, so compare parsed rows, not strings
	if (JSON.stringify(rows) !== JSON.stringify(parse_rows(frm.doc.config_rows_json))) {
		frm.set_value("config_rows_json", JSON.stringify(rows));
	}
	recalculate_totals_from_rows(frm);
}

// JS float maths gives e.g. 14204.699999999999 where the saved value is 14204.7; writing that
// back marks a freshly loaded form as "Not Saved", so round to the field's precision and skip no-ops
function set_if_changed(frm, fieldname, value) {
	const prec = precision(fieldname, frm.doc);
	value = flt(value, prec);
	if (flt(frm.doc[fieldname], prec) !== value) {
		frm.set_value(fieldname, value);
	}
}

function recalculate_totals_from_rows(frm) {
	const rows = parse_rows(frm.doc.config_rows_json);
	const rowsTotal = rows.reduce((sum, row) => sum + flt(row.amount), 0);
	const otherCosts = parse_rows(frm.doc.other_costs_json).reduce((sum, c) => sum + flt(c.qty) * flt(c.rate), 0);
	const perKitchen = rowsTotal + otherCosts;
	const kitchens = flt(frm.doc.kitchens_to_tender || 0);
	const costBase = perKitchen * kitchens;
	const targetMarginPct = flt(frm.doc.target_margin_pct || 0);
	const marginAmount = costBase * (targetMarginPct / 100);
	const tenderPriceTotal = costBase + marginAmount;
	const tenderPricePerKitchen = kitchens ? tenderPriceTotal / kitchens : 0;
	set_if_changed(frm, "other_costs_total", otherCosts);
	set_if_changed(frm, "total_cost_per_kitchen", perKitchen);
	set_if_changed(frm, "grand_total_cost", costBase);
	set_if_changed(frm, "cost_base", costBase);
	set_if_changed(frm, "margin_amount", marginAmount);
	set_if_changed(frm, "tender_price_total", tenderPriceTotal);
	set_if_changed(frm, "tender_price_per_kitchen", tenderPricePerKitchen);
	const wrapper = frm.get_field("configuration_builder").$wrapper;
	wrapper.find(".fk-total-per-kitchen").text(format_currency(perKitchen));
}

function escape_html(value) {
	return frappe.utils.escape_html(value || "");
}
