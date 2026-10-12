const METHOD_BASE =
	"fitzgerald_kitchens.fitzgerald_kitchens.doctype.tender_manifest.tender_manifest";
const SPEC_OPTIONS_METHOD =
	"fitzgerald_kitchens.fitzgerald_kitchens.doctype.item_spec.item_spec.get_spec_options";
const EXCEL_METHOD =
	"fitzgerald_kitchens.fitzgerald_kitchens.doctype.tender_manifest.tender_manifest_excel.download_tender_excel";

frappe.ui.form.on("Tender Manifest", {
	async refresh(frm) {
		render_top_intro(frm);
		add_download_button(frm);
		if (frm.is_new() && !frm.doc.naming_series) {
			frm.set_value("naming_series", "KC-.YYYY.-.#####");
		}
		if (frm.is_new() && !frm.doc.template) {
			await load_default_template(frm);
			// setting the template runs the template handler, which loads and renders everything
			if (frm.doc.template) return;
		}
		await load_template_cabinet_prices(frm);
		recalculate_totals_from_rows(frm);
		await render_builder(frm);
	},
	async template(frm) {
		await load_template_cabinet_prices(frm, true);
		await load_template_rows(frm, true);
		recalculate_totals_from_rows(frm);
		await render_builder(frm);
	},
	async tender(frm) {
		// a new manifest starts from its tender's defaults; anything already filled in is kept
		if (!frm.is_new() || !frm.doc.tender) return;
		const { message: t } = await frappe.db.get_value("Tender", frm.doc.tender, [
			"tender_name",
			"template",
			"target_margin_pct",
			"spec_list",
		]);
		if (!t) return;
		for (const field of ["tender_name", "template", "target_margin_pct", "spec_list"]) {
			if (!frm.doc[field] && t[field]) await frm.set_value(field, t[field]);
		}
	},
	kitchens_to_tender(frm) {
		recalculate_totals_from_rows(frm);
	},
	target_margin_pct(frm) {
		recalculate_totals_from_rows(frm);
	},
	base_units(frm) {
		recalculate_totals_from_rows(frm);
	},
	wall_units(frm) {
		recalculate_totals_from_rows(frm);
	},
	tall_units(frm) {
		recalculate_totals_from_rows(frm);
	},
	drawer_packs(frm) {
		recalculate_totals_from_rows(frm);
	},
});

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
			"Choose the items and specs for one unit. Costs roll up into the totals below."
		)}</p>`
	);
}

const TAG_COLOURS = { MATERIAL: "blue", LABOUR: "orange", INDIRECT: "gray", FIXED: "purple", SPEC: "green" };

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
			.fk-cols, .fk-row { display: grid; grid-template-columns: 2fr 3.3fr 3fr 0.9fr 1.2fr 28px; column-gap: var(--margin-sm); align-items: center; padding: 0 var(--padding-sm); }
			.fk-cols { background: var(--subtle-fg); border-bottom: 1px solid var(--border-color); padding-top: var(--padding-xs); padding-bottom: var(--padding-xs); font-size: var(--text-sm); color: var(--text-muted); border-radius: var(--border-radius-md) var(--border-radius-md) 0 0; }
			.fk-row { row-gap: var(--padding-xs); padding-top: var(--padding-sm); padding-bottom: var(--padding-sm); border-bottom: 1px solid var(--border-color); }
			.fk-row:last-child { border-bottom: none; }
			.fk-row .frappe-control.form-group { margin-bottom: 0; }
			.fk-item-ctl .awesomplete > ul { min-width: 320px !important; }
			.fk-spec-ctl .awesomplete > ul { min-width: 420px !important; }
			.fk-rate { margin-top: 2px; font-size: var(--text-xs); color: var(--text-muted); }
			.fk-rate:empty { display: none; }
			/* rate can be changed per tender: click the rate under the item */
			.fk-rate-value { cursor: pointer; border-bottom: 1px dotted var(--text-muted); }
			.fk-rate-value:hover { color: var(--text-color); }
			.fk-rate-value.edited { color: var(--text-color); font-weight: var(--weight-medium); }
			.fk-rate-reset { margin-left: 4px; cursor: pointer; }
			.fk-rate-ctl { margin-top: 2px; }
			.fk-rate-ctl input { height: 26px !important; font-size: var(--text-xs) !important; }
			.fk-label { font-size: var(--text-md); font-weight: var(--weight-medium); color: var(--text-color); line-height: 1.3; }
			.fk-sub { font-size: var(--text-sm); color: var(--text-muted); line-height: 1.3; }
			.fk-amount, .fk-cols .col-amount { text-align: right; font-variant-numeric: tabular-nums; }
			.fk-amount { color: var(--text-color); font-weight: var(--weight-medium); white-space: nowrap; }
			/* rows ticked "Exclude from Tender Price" on the template: recorded, not costed */
			.fk-excluded .fk-amount { color: var(--text-muted); font-weight: normal; }
			.fk-not-priced { text-align: right; font-size: var(--text-xs); color: var(--text-muted); white-space: nowrap; }
			.fk-remark-btn, .fk-remark-remove { width: 28px; height: 28px; padding: 0; border: none; border-radius: var(--border-radius); background: transparent; color: var(--text-muted); display: flex; align-items: center; justify-content: center; }
			.fk-remark-btn { opacity: 0; transition: opacity 0.15s; }
			.fk-row:hover .fk-remark-btn, .fk-remark-btn:focus-visible { opacity: 1; }
			.fk-remark-btn:hover, .fk-remark-remove:hover { background: var(--fg-hover-color); color: var(--text-color); }
			.fk-has-remark .fk-remark-btn { opacity: 1; color: var(--primary-color); }
			@media (hover: none) { .fk-remark-btn { opacity: 1; } }
			/* spec box: shown once the row has a spec, or when "+ Add new spec" opens it */
			.fk-spec-box { display: none; grid-column: 1 / -1; padding: var(--padding-xs) var(--padding-sm); border: 1px solid var(--border-color); border-left: 3px solid var(--primary-color); border-radius: var(--border-radius); background: var(--subtle-fg); }
			.fk-has-spec .fk-spec-box, .fk-spec-open .fk-spec-box { display: block; }
			.fk-spec-head { display: flex; align-items: center; gap: var(--margin-xs); margin-bottom: var(--padding-xs); font-size: var(--text-sm); color: var(--text-muted); font-weight: var(--weight-medium); }
			.fk-spec-title { flex: 1; }
			.fk-spec-input { min-height: 34px; height: auto; overflow-y: hidden; font-size: var(--text-sm) !important; background: var(--fg-color) !important; resize: none; }
			.fk-spec-remove { width: 24px; height: 24px; padding: 0; border: none; border-radius: var(--border-radius); background: transparent; color: var(--text-muted); display: flex; align-items: center; justify-content: center; }
			.fk-spec-remove:hover { background: var(--fg-hover-color); color: var(--text-color); }
			/* always shown under the item once it has a remark; otherwise only when opened via the button */
			.fk-remark-wrap { display: none; grid-column: 1 / -1; align-items: center; gap: var(--margin-xs); }
			.fk-remark { flex: 1; font-size: var(--text-sm) !important; }
			.fk-has-remark .fk-remark-wrap, .fk-remark-open .fk-remark-wrap, .fk-remark-wrap:focus-within { display: flex; }
			.fk-remark-remove { display: none; }
			.fk-has-remark .fk-remark-remove { display: flex; }
			/* charges have a note button next to remove, so their last column is wider */
			.fk-cols.fk-charge-cols, .fk-row.fk-charge-row { grid-template-columns: 2fr 3.3fr 3fr 0.9fr 1.2fr 60px; }
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
					<div>${__("Spec")}</div>
					<div>${escape_html(qtyLabel === "QTY" ? __("Qty") : qtyLabel)}</div>
					<div class="col-amount">${__("Cost (€)")}</div>
					<div></div>
				</div>
		`;

		for (const row of sectionRows) {
			html += `
				<div class="fk-row${row.remark ? " fk-has-remark" : ""}${row.specification ? " fk-has-spec" : ""}${row.exclude_from_price ? " fk-excluded" : ""}" data-row-key="${escape_html(get_row_key(row))}">
					<div>
						<div class="fk-label">${escape_html(row.label || "")}</div>
						<div class="fk-sub">${escape_html(row.subtitle || "")}</div>
					</div>
					<div><div class="fk-item-ctl"></div><div class="fk-rate">${rate_html(row)}</div><div class="fk-rate-ctl hide"></div></div>
					<div class="fk-spec-ctl"></div>
					<div class="fk-qty-ctl"></div>
					<div>
						<div class="fk-amount">${format_currency(flt(row.amount || 0))}</div>
						${row.exclude_from_price ? `<div class="fk-not-priced" title="${__("Shown for reference; not included in the tender price")}">${__("Not in price")}</div>` : ""}
					</div>
					<button type="button" class="fk-remark-btn" title="${__("Add / edit remark")}">${frappe.utils.icon("small-message", "sm")}</button>
					<div class="fk-spec-box">
						<div class="fk-spec-head">
							<span class="fk-spec-title"></span>
							<button type="button" class="btn btn-xs btn-default fk-spec-save">${__("Save to spec list…")}</button>
							<button type="button" class="fk-spec-remove" title="${__("Remove spec")}">${frappe.utils.icon("close", "sm")}</button>
						</div>
						<textarea class="fk-spec-input form-control" rows="1" placeholder="${__("Write the specification for this item")}">${escape_html(row.specification || "")}</textarea>
					</div>
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
	// spec boxes can only be sized once they're on the page
	$builder.find(".fk-spec-input").each((_, textarea) => fit_to_text(textarea));
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

async function load_default_template(frm) {
	const r = await frappe.call({
		method: `${METHOD_BASE}.get_default_template`,
	});
	if (r.message) {
		await frm.set_value("template", r.message);
	}
}

async function load_template_rows(frm, forceReload) {
	let rows = parse_rows(frm.doc.config_rows_json);
	if (!frm.doc.template) {
		return [];
	}
	if (rows.length && !forceReload) {
		// follow the current template's row details (group, labels, spec-only tick); in the browser
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
			for (const field of ["tag", "subtitle", "item_group", "qty_label", "exclude_from_price"]) {
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
			price_row: "",
			item_code: "",
			rate: 0,
			currency: "",
			uom: "",
			amount: 0,
			item_spec: "",
			spec_list: "",
			spec_reference: "",
			specification: "",
			spec_custom: 0,
		}));
		save_rows(frm, rows);
	}
	return rows;
}

async function load_template_cabinet_prices(frm, forceReload = false) {
	if (!frm.doc.template) {
		frm.set_value("cabinet_prices_json", "");
		return;
	}
	let cabinetPrices = parse_cabinet_prices(frm.doc.cabinet_prices_json);
	if (!Object.keys(cabinetPrices).length || forceReload) {
		const r = await frappe.call({
			method: `${METHOD_BASE}.get_template_cabinet_prices`,
			args: { template: frm.doc.template },
		});
		cabinetPrices = r.message || {};
		frm.set_value("cabinet_prices_json", JSON.stringify(cabinetPrices));
	}
}

async function bind_row_events(frm, rows, wrapper, is_current = () => true) {
	// one call per item group, all at once, rather than one per row in turn
	const groups = [...new Set(rows.map((r) => r.item_group).filter(Boolean))];
	const [specOptions, groupPrices] = await Promise.all([
		fetch_spec_options(rows.map((r) => r.item_code)),
		Promise.all(
			groups.map((item_group) =>
				frappe
					.call({ method: `${METHOD_BASE}.get_price_options`, args: { item_group } })
					.then((r) => r.message || [])
			)
		),
	]);
	if (!is_current()) return;
	const pricesByGroup = Object.fromEntries(groups.map((group, i) => [group, groupPrices[i]]));

	// rows don't depend on each other, so they're bound side by side
	const elements = wrapper.find(".fk-row").toArray();
	await Promise.all(elements.map((el) => bind_row(el)));

	async function bind_row(el) {
		const $row = $(el);
		const key = $row.attr("data-row-key");
		const row = rows.find((r) => get_row_key(r) === key);
		if (!row) return;

		// spec-only rows: any item in the group, priced for reference but kept out of the tender price
		const specOnly = !!row.exclude_from_price;
		const priceOptions = pricesByGroup[row.item_group] || [];

		const pricedCodes = [...new Set(priceOptions.map((o) => o.item_code))];

		// apply the new item to the row, refresh cost/rate, and reload its specs if the item changed
		const on_item_changed = async (itemChanged, apply) => {
			apply();
			// a different item starts from its own price
			row.list_rate = row.rate;
			row.rate_override = 0;
			$row.find(".fk-amount").text(format_currency(row.amount));
			$row.find(".fk-rate").html(rate_html(row));
			if (itemChanged) {
				const specs = (await fetch_spec_options([row.item_code]))[row.item_code] || [];
				if (row.spec_custom && row.specification) {
					// keep text written on the tender, but it no longer belongs to the old item's spec
					row.item_spec = row.spec_list = row.spec_reference = "";
				} else {
					// a different item starts with no spec; the user picks one from the list
					set_row_spec(row, null);
					$row.find(".fk-spec-input").val(row.specification);
				}
				await fill_spec_control(specControl, specs, row);
				update_spec_box($row, row, specs);
			}
			save_rows(frm, rows);
		};

		const itemControl = make_row_control($row.find(".fk-item-ctl"), {
			fieldtype: "Link",
			fieldname: "item_code",
			options: "Item",
			placeholder: __("Select item"),
			filter_description: specOnly
				? __("{0} items", [row.item_group])
				: __("{0} items with a selling price", [row.item_group]),
			// costed rows: only items with a Standard Selling price; spec-only rows: any item in the group
			get_query: () =>
				specOnly
					? { filters: { item_group: row.item_group, disabled: 0, has_variants: 0 } }
					: { filters: { name: ["in", pricedCodes.length ? pricedCodes : [""]] } },
			change: async () => {
				if (itemControl.__fk_silent) return;
				const code = itemControl.get_value() || "";
				const matches = priceOptions.filter((o) => o.item_code === code);
				if (specOnly) {
					// unpriced items are fine here; they just show no rate
					const opt = matches.find((o) => o.uom === row.uom) || matches[0];
					await on_item_changed(code !== row.item_code, () => {
						row.item_code = code;
						row.price_row = opt?.price_row || "";
						row.rate = flt(opt?.rate);
						row.currency = opt?.currency || "";
						row.uom = opt?.uom || "";
						row.amount = flt(row.qty) * flt(row.rate);
					});
					return;
				}
				const opt = matches.find((o) => o.uom === row.uom) || matches[0];
				if (code && !opt) {
					frappe.show_alert({
						message: __("{0} has no Standard Selling price in this group, so it can't be costed here.", [code]),
						indicator: "orange",
					});
					await set_silently(itemControl, row.item_code || "");
					return;
				}
				await on_item_changed(row.item_code !== (opt?.item_code || ""), () => {
					row.price_row = opt?.price_row || "";
					row.item_code = opt?.item_code || "";
					row.rate = flt(opt?.rate);
					row.currency = opt?.currency || "";
					row.uom = opt?.uom || "";
					row.amount = flt(row.qty) * flt(row.rate);
				});
			},
		});
		await set_silently(itemControl, row.item_code || "");

		const specControl = make_row_control($row.find(".fk-spec-ctl"), {
			fieldtype: "Link",
			fieldname: "item_spec",
			options: "Item Spec",
			get_query: () => {
				specControl.df.filter_description = row.item_code
					? __("Specs for {0}", [row.item_code])
					: __("Select an item first");
				return { filters: { item_code: row.item_code || "__no_item__" } };
			},
			change: async () => {
				if (specControl.__fk_silent) return;
				const value = specControl.get_value();
				let specs = specControl.__fk_specs || [];
				if (value && !specs.some((s) => s.name === value)) {
					// e.g. picked through Advanced Search, or created since the row loaded
					specs = (await fetch_spec_options([row.item_code]))[row.item_code] || [];
					specControl.__fk_specs = specs;
				}
				set_row_spec(row, specs.find((s) => s.name === value) || null);
				specInput.val(row.specification);
				update_spec_box($row, row, specs);
				save_rows(frm, rows);
			},
		});
		// the dropdown's "Create a new Item Spec" opens the spec box under the item instead of a dialog
		specControl.new_doc = () => {
			if (!row.item_code) {
				frappe.msgprint(__("Select an item for {0} first, then add its spec.", [row.label || __("this row")]));
				return;
			}
			set_row_spec(row, null);
			row.spec_custom = 1;
			set_silently(specControl, "");
			specInput.val("");
			$row.addClass("fk-spec-open");
			update_spec_box($row, row, specControl.__fk_specs || []);
			specInput.trigger("focus");
			save_rows(frm, rows);
		};
		await fill_spec_control(specControl, specOptions[row.item_code] || [], row);

		const specInput = $row.find(".fk-spec-input");
		update_spec_box($row, row, specOptions[row.item_code] || []);

		specInput.on("input", (e) => {
			const specs = specControl.__fk_specs || [];
			const linked = specs.find((s) => s.name === row.item_spec);
			row.specification = e.target.value;
			// edited away from the linked spec (or written from scratch) = specific to this tender
			row.spec_custom = linked && (linked.specification || "").trim() === row.specification.trim() ? 0 : 1;
			update_spec_box($row, row, specs);
			save_rows(frm, rows);
		});

		specInput.on("blur", () => {
			row.specification = (row.specification || "").trim();
			specInput.val(row.specification);
			if (!row.specification && !row.item_spec) row.spec_custom = 0;
			$row.removeClass("fk-spec-open");
			update_spec_box($row, row, specControl.__fk_specs || []);
			save_rows(frm, rows);
		});

		$row.find(".fk-spec-remove").on("click", async () => {
			set_row_spec(row, null);
			specInput.val("");
			$row.removeClass("fk-spec-open");
			await set_silently(specControl, "");
			update_spec_box($row, row, specControl.__fk_specs || []);
			save_rows(frm, rows);
		});

		// mousedown keeps the textarea's blur from hiding the box before the click lands
		$row.find(".fk-spec-save").on("mousedown", (e) => e.preventDefault()).on("click", () => {
			save_spec_to_list(row, specControl.__fk_specs || [], async (savedSpec) => {
				const specs = (await fetch_spec_options([row.item_code]))[row.item_code] || [];
				set_row_spec(row, specs.find((s) => s.name === savedSpec) || null);
				specInput.val(row.specification);
				await fill_spec_control(specControl, specs, row);
				update_spec_box($row, row, specs);
				save_rows(frm, rows);
			});
		});

		const qtyControl = make_row_control($row.find(".fk-qty-ctl"), {
			fieldtype: "Float",
			fieldname: "qty",
			non_negative: 1,
			change: () => {
				if (qtyControl.__fk_silent) return;
				row.qty = flt(qtyControl.get_value());
				row.amount = flt(row.qty) * flt(row.rate);
				$row.find(".fk-amount").text(format_currency(row.amount));
				save_rows(frm, rows);
			},
		});
		await set_silently(qtyControl, flt(row.qty));

		// rate: click it to change it for this tender (kept on save); "reset" goes back to the price list
		if (row.list_rate === undefined) row.list_rate = row.rate;
		const $rate = $row.find(".fk-rate");
		const $rateCtl = $row.find(".fk-rate-ctl");
		let rateControl = null;
		const apply_rate = (rate, override) => {
			row.rate = flt(rate);
			row.rate_override = override && row.rate !== flt(row.list_rate) ? 1 : 0;
			row.amount = flt(row.qty) * flt(row.rate);
			$row.find(".fk-amount").text(format_currency(row.amount));
			$rate.html(rate_html(row));
			save_rows(frm, rows);
		};
		$rate.on("click", ".fk-rate-reset", (e) => {
			e.stopPropagation();
			apply_rate(row.list_rate, false);
		});
		$rate.on("click", ".fk-rate-value", async () => {
			if (!rateControl) {
				rateControl = make_row_control($rateCtl, {
					fieldtype: "Currency",
					fieldname: "rate",
					non_negative: 1,
					change: () => {
						if (rateControl.__fk_silent) return;
						apply_rate(rateControl.get_value(), true);
					},
				});
				rateControl.$input.on("blur", () => {
					$rateCtl.addClass("hide");
					$rate.removeClass("hide");
				});
			}
			await set_silently(rateControl, flt(row.rate));
			$rate.addClass("hide");
			$rateCtl.removeClass("hide");
			rateControl.$input.trigger("focus").select();
		});

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

async function fetch_spec_options(itemCodes) {
	const codes = [...new Set(itemCodes.filter(Boolean))];
	if (!codes.length) return {};
	const r = await frappe.call({ method: SPEC_OPTIONS_METHOD, args: { item_codes: codes } });
	return r.message || {};
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

// rate under the item: click to change it; an edited rate shows the list price and a reset link
function rate_html(row) {
	if (!row.item_code) return "";
	const per = (value) => `${format_currency(flt(value), row.currency)}${row.uom ? ` / ${row.uom}` : ""}`;
	if (row.rate_override) {
		return `<span class="fk-rate-value edited" title="${__("Rate changed for this tender. Click to edit")}">${escape_html(per(row.rate))}</span>
			<span> · ${__("list {0}", [escape_html(format_currency(flt(row.list_rate), row.currency))])}</span>
			<a class="fk-rate-reset">${__("reset")}</a>`;
	}
	const label = flt(row.rate) ? per(row.rate) : __("Set rate");
	return `<span class="fk-rate-value" title="${__("Click to change the rate for this tender")}">${escape_html(label)}</span>`;
}

async function fill_spec_control(specControl, specs, row) {
	specControl.__fk_specs = specs;
	// so the Link shows "Standard Spec · N11 360" rather than the Item Spec's random name
	for (const spec of specs) {
		frappe.utils.add_link_title("Item Spec", spec.name, [spec.spec_list, spec.spec_reference].filter(Boolean).join(" · "));
	}
	const placeholder = row.spec_custom && !row.item_spec && row.specification
		? __("Custom spec (below)")
		: specs.length
			? __("No spec")
			: __("No specs for this item");
	specControl.$input.attr("placeholder", placeholder);
	await set_silently(specControl, row.item_spec || "");
}

// heading, save button and visibility of the spec box under an item
function update_spec_box($row, row, specs) {
	const source = [row.spec_list, row.spec_reference].filter(Boolean).join(" · ");
	let title;
	if (row.item_spec && !row.spec_custom) title = source;
	else if (row.item_spec) title = __("{0} — edited for this tender", [source]);
	else if (row.specification) title = __("Custom spec — not saved to a spec list");
	else title = __("New spec");

	$row.find(".fk-spec-title").text(title);
	$row.find(".fk-spec-save").toggle(!!row.spec_custom && !!(row.specification || "").trim());
	$row.toggleClass("fk-has-spec", !!row.specification);
	fit_to_text($row.find(".fk-spec-input").get(0));
}

// grow a textarea to its content (only measurable while visible)
function fit_to_text(textarea) {
	if (!textarea || !textarea.offsetParent) return;
	textarea.style.height = "auto";
	textarea.style.height = `${textarea.scrollHeight + 2}px`;
}

function set_row_spec(row, spec) {
	row.item_spec = spec?.name || "";
	row.spec_list = spec?.spec_list || "";
	row.spec_reference = spec?.spec_reference || "";
	row.specification = spec?.specification || "";
	row.spec_custom = 0;
}

// save the row's spec text as an Item Spec in a chosen spec list (new, or updating the item's spec there)
function save_spec_to_list(row, specs, on_saved) {
	if (!row.item_code) {
		frappe.msgprint(__("Select an item for {0} first, then save its spec.", [row.label || __("this row")]));
		return;
	}

	const dialog = new frappe.ui.Dialog({
		title: __("Save Spec for {0}", [row.item_code]),
		fields: [
			{
				fieldname: "spec_list",
				fieldtype: "Link",
				label: __("Spec List"),
				options: "Spec List",
				reqd: 1,
				default: row.spec_list || undefined,
				get_query: () => ({ filters: { enabled: 1 } }),
			},
			{
				fieldname: "spec_reference",
				fieldtype: "Data",
				label: __("Spec Reference"),
				default: row.spec_reference || undefined,
				description: __("Clause in the source specification, e.g. N17 410"),
			},
		],
		primary_action_label: __("Save"),
		primary_action(values) {
			const specification = (row.specification || "").trim();
			const existing = specs.find((s) => s.spec_list === values.spec_list);
			const save = () => {
				dialog.disable_primary_action();
				const request = existing
					? frappe.db.set_value("Item Spec", existing.name, {
							specification,
							spec_reference: values.spec_reference || "",
					  })
					: frappe.db.insert({
							doctype: "Item Spec",
							item_code: row.item_code,
							spec_list: values.spec_list,
							spec_reference: values.spec_reference || "",
							specification,
					  });
				request
					.then((r) => {
						dialog.hide();
						frappe.show_alert({
							message: existing ? __("Spec updated in {0}", [values.spec_list]) : __("Spec saved to {0}", [values.spec_list]),
							indicator: "green",
						});
						on_saved(existing ? existing.name : r.name);
					})
					.catch(() => dialog.enable_primary_action());
			};
			// an item has one spec per spec list, so saving to a list it already has updates that spec
			if (existing) {
				frappe.confirm(
					__("{0} already has a spec in {1}. Update it with this text?", [row.item_code, values.spec_list]),
					save
				);
			} else {
				save();
			}
		},
	});
	dialog.show();
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
	// rows excluded from the tender price keep their item and spec but add nothing to the cost
	const rowsTotal = rows.reduce((sum, row) => sum + (row.exclude_from_price ? 0 : flt(row.amount)), 0);
	const cabinetPrices = parse_cabinet_prices(frm.doc.cabinet_prices_json);
	const cabinetTotal = set_cabinet_cost_fields(frm, cabinetPrices);
	const otherCosts = parse_rows(frm.doc.other_costs_json).reduce((sum, c) => sum + flt(c.qty) * flt(c.rate), 0);
	const perKitchen = rowsTotal + cabinetTotal + otherCosts;
	const kitchens = flt(frm.doc.kitchens_to_tender || 0);
	const costBase = perKitchen * kitchens;
	const targetMarginPct = flt(frm.doc.target_margin_pct || 0);
	const marginAmount = costBase * (targetMarginPct / 100);
	const tenderPriceTotal = costBase + marginAmount;
	const tenderPricePerKitchen = kitchens ? tenderPriceTotal / kitchens : 0;
	set_if_changed(frm, "cabinets_total", cabinetTotal);
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

function set_cabinet_cost_fields(frm, cabinetPrices) {
	const cabinetMap = {
		base_units: flt(frm.doc.base_units),
		wall_units: flt(frm.doc.wall_units),
		tall_units: flt(frm.doc.tall_units),
		drawer_packs: flt(frm.doc.drawer_packs),
	};
	let total = 0;
	for (const [key, qty] of Object.entries(cabinetMap)) {
		const rate = flt(cabinetPrices[key]?.rate);
		const amount = qty * rate;
		set_if_changed(frm, `${key}_rate`, rate);
		set_if_changed(frm, `${key}_amount`, amount);
		total += amount;
	}
	return total;
}

function parse_cabinet_prices(value) {
	if (!value) return {};
	try {
		const data = JSON.parse(value);
		return data && typeof data === "object" ? data : {};
	} catch (e) {
		return {};
	}
}

function escape_html(value) {
	return frappe.utils.escape_html(value || "");
}
