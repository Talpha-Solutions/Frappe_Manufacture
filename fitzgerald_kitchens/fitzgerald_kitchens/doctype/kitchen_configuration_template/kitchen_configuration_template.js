const METHOD_BASE =
	"fitzgerald_kitchens.fitzgerald_kitchens.doctype.kitchen_configuration_template.kitchen_configuration_template";

const CABINET_PRICE_FIELDS = [
	"base_units_price_row",
	"wall_units_price_row",
	"tall_units_price_row",
	"drawer_packs_price_row",
];

frappe.ui.form.on("Kitchen Configuration Template", {
	setup(frm) {
		for (const fieldname of CABINET_PRICE_FIELDS) {
			frm.set_query(fieldname, () => ({
				query: `${METHOD_BASE}.get_item_price_list`,
			}));
		}
	},
	async refresh(frm) {
		set_rows_table_full_width(frm);
		await render_cabinet_price_reference(frm);
	},
});

function set_rows_table_full_width(frm) {
	const field = frm.fields_dict.rows;
	if (!field?.$wrapper) return;

	const $wrapper = field.$wrapper;
	const $section = $wrapper.closest(".form-section");
	if (!$section.length) return;

	const $sectionBody = $section.find(".section-body").first();
	const $column = $wrapper.closest(".form-column");

	if ($column.length && $sectionBody.length && $column.parent()[0] !== $sectionBody[0]) {
		$sectionBody.append($column);
	}

	$section.find(".form-column").removeClass("col-sm-6").addClass("col-sm-12");
	$section.find(".form-grid").css({ width: "100%", "max-width": "100%" });
}

async function render_cabinet_price_reference(frm) {
	const htmlField = frm.get_field("cabinet_price_options_html");
	if (!htmlField) return;

	htmlField.$wrapper.html(
		`<div style="padding:8px;color:#6b7280;font-size:12px;">Loading item prices...</div>`
	);

	const r = await frappe.call({
		method: `${METHOD_BASE}.get_all_item_price_options`,
	});
	const options = r.message || [];
	if (!options.length) {
		htmlField.$wrapper.html(
			`<div style="padding:8px;color:#6b7280;font-size:12px;">No item prices found.</div>`
		);
		return;
	}

	let rowsHtml = "";
	for (const opt of options) {
		const formattedRate = format_currency(flt(opt.rate), opt.currency);
		rowsHtml += `
			<tr>
				<td>${escape_html(opt.item_name || opt.item_code)}</td>
				<td>${escape_html(opt.item_group || "")}</td>
				<td>${escape_html(opt.price_list || "")}</td>
				<td style="text-align:right;">${escape_html(formattedRate)}</td>
				<td>${escape_html(opt.uom || "")}</td>
				<td style="color:#6b7280;font-size:11px;">${escape_html(opt.price_row)}</td>
			</tr>
		`;
	}

	htmlField.$wrapper.html(`
		<div style="margin-top:8px;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;">
			<div style="padding:8px 12px;background:#f8f9fb;font-size:12px;font-weight:700;color:#4b5563;">
				All item prices (one row per price — select from the fields above)
			</div>
			<div style="max-height:220px;overflow:auto;">
				<table class="table table-bordered" style="margin:0;font-size:12px;">
					<thead>
						<tr>
							<th>Item</th>
							<th>Item Group</th>
							<th>Price List</th>
							<th style="text-align:right;">Rate</th>
							<th>UOM</th>
							<th>Item Price ID</th>
						</tr>
					</thead>
					<tbody>${rowsHtml}</tbody>
				</table>
			</div>
		</div>
	`);
}

function escape_html(value) {
	return frappe.utils.escape_html(value || "");
}
