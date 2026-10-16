const METHOD_BASE =
	"fitzgerald_kitchens.fitzgerald_kitchens.doctype.tender_configuration_template.tender_configuration_template";

const CABINET_PRICE_FIELDS = [
	"base_units_price_row",
	"wall_units_price_row",
	"tall_units_price_row",
	"drawer_packs_price_row",
];

frappe.ui.form.on("Tender Configuration Template", {
	setup(frm) {
		frm.set_query("party_type", () => ({ filters: { name: ["in", ["Lead", "Customer"]] } }));
		for (const fieldname of CABINET_PRICE_FIELDS) {
			frm.set_query(fieldname, () => ({
				query: `${METHOD_BASE}.get_item_price_list`,
			}));
		}
	},
	async refresh(frm) {
		frm.__fk_party_type = frm.doc.party_type;
		add_party_template_button(frm);
		add_get_from_template_button(frm);
		set_rows_table_full_width(frm);
		await render_cabinet_price_reference(frm);
	},
	party_type(frm) {
		// only when the type changes from one to another: a new template started from a tender's
		// Template field arrives with both filled in
		if (frm.__fk_party_type && frm.__fk_party_type !== frm.doc.party_type) frm.set_value("party_name", "");
		frm.__fk_party_type = frm.doc.party_type;
	},
	is_template(frm) {
		// a base template is for everyone
		if (frm.doc.is_template) {
			frm.set_value("party_type", "");
			frm.set_value("party_name", "");
		}
	},
});

const ROW_FIELDS = ["section", "tag", "label", "subtitle", "item_group", "qty_label", "default_qty", "exclude_from_price"];

// fill this template's rows from a base template (Is Template); the user reviews them, then saves
function add_get_from_template_button(frm) {
	if (!frm.perm[0]?.write) return;
	frm.add_custom_button(__("Get from Template"), () => get_from_template_dialog(frm), __("Actions"));
}

async function get_from_template_dialog(frm) {
	const templates = await frappe.db.get_list("Tender Configuration Template", {
		filters: { is_template: 1, name: ["!=", frm.doc.name || ""] },
		fields: ["name"],
		order_by: "name asc",
		limit: 100,
	});
	if (!templates.length) {
		frappe.msgprint(__("There are no base templates yet. Tick Is Template on a template to offer it here."));
		return;
	}
	// a new template starts with one blank row; that doesn't count
	const is_blank = (row) => !row.label && !row.item_group;
	const has_rows = (frm.doc.rows || []).some((row) => !is_blank(row));
	const dialog = new frappe.ui.Dialog({
		title: __("Get from Template"),
		fields: [
			{
				fieldname: "template",
				fieldtype: "Select",
				label: __("Template"),
				reqd: 1,
				options: templates.map((t) => t.name).join("\n"),
				default: templates[0].name,
				onchange: () => show_preview(),
			},
			{ fieldname: "preview", fieldtype: "HTML" },
			{
				fieldname: "replace",
				fieldtype: "Check",
				label: __("Replace the rows already here"),
				default: has_rows ? 0 : 1,
				hidden: !has_rows,
				description: __("Unticked, the template's rows are added after the existing ones"),
			},
		],
		primary_action_label: __("Get Rows"),
		async primary_action({ template, replace }) {
			const source = await frappe.db.get_doc("Tender Configuration Template", template);
			if (replace) frm.clear_table("rows");
			else {
				frm.doc.rows = (frm.doc.rows || []).filter((row) => !is_blank(row));
				frm.doc.rows.forEach((row, i) => (row.idx = i + 1));
			}
			for (const row of source.rows || []) {
				const child = frm.add_child("rows");
				for (const field of ROW_FIELDS) child[field] = row[field];
			}
			frm.refresh_field("rows");
			// the cabinet prices only where this template has none yet
			for (const field of CABINET_PRICE_FIELDS) {
				if (!frm.doc[field] && source[field]) await frm.set_value(field, source[field]);
			}
			if (!frm.doc.based_on && !frm.doc.is_template) await frm.set_value("based_on", template);
			dialog.hide();
			frappe.show_alert({
				message: __("Added {0} rows from {1}. Review them, then save.", [(source.rows || []).length, template]),
				indicator: "green",
			});
		},
	});

	// what the chosen template holds, by section
	async function show_preview() {
		const template = dialog.get_value("template");
		const wrapper = dialog.fields_dict.preview.$wrapper;
		if (!template) return wrapper.empty();
		const source = await frappe.db.get_doc("Tender Configuration Template", template);
		if (dialog.get_value("template") !== template) return;
		const sections = {};
		for (const row of source.rows || []) (sections[row.section || __("Other")] ||= []).push(row.label);
		const esc = frappe.utils.escape_html;
		wrapper.html(`
			<div class="text-muted small" style="margin-bottom: var(--margin-sm);">
				${__("{0} rows", [(source.rows || []).length])}
			</div>
			${Object.entries(sections)
				.map(([section, labels]) => `<div class="small" style="margin-bottom: 4px;"><b>${esc(section)}</b>: ${labels.map(esc).join(", ")}</div>`)
				.join("")}
		`);
	}
	dialog.show();
	show_preview();
}

// copy a base template for a Lead or Customer, who can then have their own labels, rows and items
function add_party_template_button(frm) {
	if (frm.is_new() || !frm.doc.is_template || !frappe.model.can_create("Tender Configuration Template")) return;
	frm.add_custom_button(
		__("Create Party Template"),
		() => {
			if (frm.is_dirty()) {
				frappe.msgprint(__("Save the template first."));
				return;
			}
			const suggest_name = async () => {
				const party_type = dialog.get_value("party_type");
				const party_name = dialog.get_value("party_name");
				if (!party_type || !party_name) return;
				const fields = party_type === "Customer" ? ["customer_name"] : ["company_name", "lead_name"];
				const { message: p = {} } = await frappe.db.get_value(party_type, party_name, fields);
				const title = p.customer_name || p.company_name || p.lead_name || party_name;
				dialog.set_value("template_name", `${frm.doc.template_name} - ${title}`);
			};
			const dialog = new frappe.ui.Dialog({
				title: __("Create Party Template"),
				fields: [
					{ fieldname: "party_type", fieldtype: "Select", label: __("Party Type"), options: "Customer\nLead", default: "Customer", reqd: 1,
						onchange: () => dialog.set_value("party_name", "") },
					{ fieldname: "party_name", fieldtype: "Dynamic Link", label: __("Party"), options: "party_type", reqd: 1, onchange: suggest_name,
						// look in the Party Type chosen above
						get_options: () => dialog.get_value("party_type") },
					{ fieldname: "template_name", fieldtype: "Data", label: __("Template Name"), reqd: 1 },
					{ fieldtype: "HTML", options: `<p class="text-muted small">${__("Copies this template's rows and cabinet prices. Edit the copy for them; this template isn't changed.")}</p>` },
				],
				primary_action_label: __("Create"),
				primary_action({ party_type, party_name, template_name }) {
					frappe
						.xcall(`${METHOD_BASE}.create_party_template`, { template: frm.doc.name, party_type, party_name, template_name })
						.then((name) => {
							dialog.hide();
							frappe.show_alert({ message: __("Created {0}", [name]), indicator: "green" });
							frappe.set_route("Form", "Tender Configuration Template", name);
						});
				},
			});
			dialog.show();
		},
		__("Actions")
	);
}

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
