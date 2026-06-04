const METHOD_BASE =
	"fitzgerald_kitchens.fitzgerald_kitchens.doctype.kitchen_configuration.kitchen_configuration";

frappe.ui.form.on("Kitchen Configuration", {
	async refresh(frm) {
		render_top_intro(frm);
		if (frm.is_new() && !frm.doc.template) {
			await load_default_template(frm);
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

function render_top_intro(frm) {
	const intro = frm.get_field("top_intro");
	if (!intro) return;
	intro.$wrapper.html(`
		<div style="margin-bottom:8px;">
			<div style="font-size:22px;font-weight:800;line-height:1.2;color:#111827;">Kitchen configuration</div>
			<div style="font-size:13px;color:#6b7280;margin-top:3px;">Choose specs for one kitchen unit - costs roll up to the right</div>
		</div>
	`);
}

async function render_builder(frm) {
	const wrapper = frm.get_field("configuration_builder").$wrapper;
	let rows = await load_template_rows(frm, false);
	if (!rows.length) {
		wrapper.html(
			`<div style="padding:12px;border:1px dashed #d1d5db;border-radius:8px;color:#6b7280;">Select a Template to load configuration rows.</div>`
		);
		return;
	}

	const grouped = group_by_section(rows);
	const styleBlock = `
		<style>
			.fk-builder { background: #f8f9fb; border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px; }
			.fk-section { background: #fff; border: 1px solid #e8ecf1; border-radius: 10px; padding: 12px; margin-top: 10px; }
			.fk-section-title { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
			.fk-title-text { font-size: 12px; letter-spacing: 0.4px; font-weight: 800; color: #4b5563; }
			.fk-tag { font-size: 10px; font-weight: 700; color: #2563eb; background: #e8f0ff; padding: 2px 8px; border-radius: 12px; }
			.fk-cols { display: grid; grid-template-columns: 2.2fr 5fr 1fr 1fr; gap: 10px; font-size: 11px; font-weight: 700; color: #6b7280; padding-bottom: 6px; border-bottom: 1px solid #f1f3f5; }
			.fk-row { display: grid; grid-template-columns: 2.2fr 5fr 1fr 1fr; gap: 10px; align-items: center; padding: 8px 0; border-bottom: 1px solid #f5f6f7; }
			.fk-row:last-child { border-bottom: none; }
			.fk-label { font-size: 14px; font-weight: 600; color: #1f2937; line-height: 1.2; }
			.fk-sub { font-size: 11px; color: #8b95a7; margin-top: 2px; line-height: 1.2; }
			.fk-item-select, .fk-qty { height: 36px !important; border-radius: 8px !important; border-color: #d7dde6 !important; background: #fff !important; }
			.fk-amount { font-weight: 700; color: #111827; text-align: right; }
			.fk-footer { display: flex; justify-content: flex-end; margin-top: 12px; font-size: 13px; font-weight: 700; color: #111827; }
			.fk-footer .value { margin-left: 6px; }
		</style>
	`;

	let html = `${styleBlock}<div class="fk-builder"><div class="fk-config-grid" style="display:flex;flex-direction:column;gap:8px;">`;

	for (const [sectionName, sectionRows] of Object.entries(grouped)) {
		const tag = sectionRows[0]?.tag || "";
		const qtyLabel = sectionRows[0]?.qty_label || "QTY";
		html += `
			<div class="fk-section">
				<div class="fk-section-title">
					<div class="fk-title-text">${escape_html(sectionName)}</div>
					${tag ? `<span class="fk-tag">${escape_html(tag)}</span>` : ""}
				</div>
				<div class="fk-cols">
					<div>ITEM</div>
					<div>SELECTION</div>
					<div>${escape_html(qtyLabel)}</div>
					<div style="text-align:right;">€ COST</div>
				</div>
		`;

		for (const row of sectionRows) {
			html += `
				<div class="fk-row" data-row-key="${escape_html(get_row_key(row))}">
					<div>
						<div class="fk-label">${escape_html(row.label || "")}</div>
						<div class="fk-sub">${escape_html(row.subtitle || "")}</div>
					</div>
					<div><select class="fk-item-select form-control"><option value="">Select item</option></select></div>
					<div><input class="fk-qty form-control" type="number" min="0" step="0.01" value="${flt(row.qty)}" /></div>
					<div class="fk-amount">${format_currency(flt(row.amount || 0))}</div>
				</div>
			`;
		}

		html += `</div>`;
	}

	html += `<div class="fk-footer">
		Total / Kitchen: <span class="fk-total-per-kitchen value">${format_currency(flt(frm.doc.total_cost_per_kitchen || 0))}</span>
			</div>
	</div></div>`;
	wrapper.html(html);

	await bind_row_events(frm, rows, wrapper);
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

async function bind_row_events(frm, rows, wrapper) {
	const elements = wrapper.find(".fk-row").toArray();
	for (const el of elements) {
		const $row = $(el);
		const key = $row.attr("data-row-key");
		const row = rows.find((r) => get_row_key(r) === key);
		if (!row) continue;

		const select = $row.find(".fk-item-select");
		const r = await frappe.call({
			method: `${METHOD_BASE}.get_price_options`,
			args: { item_group: row.item_group },
		});
		const options = r.message || [];
		for (const opt of options) {
			const selected = row.price_row === opt.price_row ? "selected" : "";
			const formattedRate = format_currency(flt(opt.rate), opt.currency);
			const text = `${opt.item_name || opt.item_code} - ${formattedRate}${opt.uom ? `/${opt.uom}` : ""}`;
			select.append(
				`<option value="${escape_html(opt.price_row)}" data-item="${escape_html(opt.item_code)}" data-rate="${flt(opt.rate)}" data-currency="${escape_html(opt.currency || "")}" data-uom="${escape_html(opt.uom || "")}" ${selected}>${escape_html(text)}</option>`
			);
		}

		select.on("change", () => {
			const selected = select.find("option:selected");
			row.price_row = selected.val() || "";
			row.item_code = selected.attr("data-item") || "";
			row.rate = flt(selected.attr("data-rate"));
			row.currency = selected.attr("data-currency") || "";
			row.uom = selected.attr("data-uom") || "";
			row.amount = flt(row.qty) * flt(row.rate);
			$row.find(".fk-amount").text(format_currency(row.amount));
			save_rows(frm, rows);
		});

		$row.find(".fk-qty").on("input", (e) => {
			row.qty = flt(e.target.value);
			row.amount = flt(row.qty) * flt(row.rate);
			$row.find(".fk-amount").text(format_currency(row.amount));
			save_rows(frm, rows);
		});
	}
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
	frm.set_value("config_rows_json", JSON.stringify(rows));
	recalculate_totals_from_rows(frm);
}

function recalculate_totals_from_rows(frm) {
	const rows = parse_rows(frm.doc.config_rows_json);
	const rowsTotal = rows.reduce((sum, row) => sum + flt(row.amount), 0);
	const cabinetPrices = parse_cabinet_prices(frm.doc.cabinet_prices_json);
	const cabinetTotal = set_cabinet_cost_fields(frm, cabinetPrices);
	const perKitchen = rowsTotal + cabinetTotal;
	const kitchens = flt(frm.doc.kitchens_to_tender || 0);
	const costBase = perKitchen * kitchens;
	const targetMarginPct = flt(frm.doc.target_margin_pct || 0);
	const marginAmount = costBase * (targetMarginPct / 100);
	const tenderPriceTotal = costBase + marginAmount;
	const tenderPricePerKitchen = kitchens ? tenderPriceTotal / kitchens : 0;
	frm.set_value("cabinets_total", cabinetTotal);
	frm.set_value("total_cost_per_kitchen", perKitchen);
	frm.set_value("grand_total_cost", costBase);
	frm.set_value("cost_base", costBase);
	frm.set_value("margin_amount", marginAmount);
	frm.set_value("tender_price_total", tenderPriceTotal);
	frm.set_value("tender_price_per_kitchen", tenderPricePerKitchen);
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
		frm.set_value(`${key}_rate`, rate);
		frm.set_value(`${key}_amount`, amount);
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
