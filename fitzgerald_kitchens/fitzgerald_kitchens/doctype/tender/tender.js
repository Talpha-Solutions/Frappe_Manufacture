// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

const TENDER_METHOD = "fitzgerald_kitchens.fitzgerald_kitchens.doctype.tender.tender";
const TEMPLATE_QUERY = "fitzgerald_kitchens.fitzgerald_kitchens.doctype.tender_configuration_template.tender_configuration_template.template_query";
const EXCEL_METHOD = "fitzgerald_kitchens.fitzgerald_kitchens.doctype.tender.tender_excel.download_tender_excel";

frappe.ui.form.on("Tender", {
	setup(frm) {
		frm.set_query("party_type", () => ({ filters: { name: ["in", ["Lead", "Customer"]] } }));
		// the customer's own templates if they have any, otherwise those for everyone
		frm.set_query("template", () => ({
			query: TEMPLATE_QUERY,
			filters: { party_type: frm.doc.party_type || "", party_name: frm.doc.party_name || "" },
		}));
		// Units tab: this tender's manifests, and any project type but Site
		frm.set_query("manifest", "unit_types", () => ({ filters: { tender: frm.doc.name || "__none__" } }));
		frm.set_query("project_type", "unit_types", () => ({ filters: { name: ["!=", "Site"] } }));
	},
	party_type(frm) {
		// the party belongs to the old type
		frm.set_value("party_name", "");
	},
	refresh(frm) {
		set_unit_defaults(frm);
		// "Create a new Tender Configuration Template" from the Template field starts it for this party
		frm.set_df_property("template", "get_route_options_for_new_doc", () =>
			frm.doc.party_name ? { party_type: frm.doc.party_type, party_name: frm.doc.party_name } : {}
		);
		frm.set_df_property(
			"template",
			"filter_description",
			__("Templates for this tender's Lead or Customer, or for everyone if they don't have their own")
		);
		add_download_buttons(frm);
		render_manifests(frm);
	},
});

// the Units tab opens once the tender is won; start it with the usual company and task template
function set_unit_defaults(frm) {
	if (frm.doc.status !== "Won" || !frm.perm[0]?.write) return;
	const company = frappe.defaults.get_user_default("Company");
	if (!frm.doc.company && company) frm.set_value("company", company);
	if (!frm.doc.project_template) {
		frappe.db.exists("Project Template", "Main Development Template").then((exists) => {
			if (exists && !frm.doc.project_template) frm.set_value("project_template", "Main Development Template");
		});
	}
}

// detailed: our costing across all tender manifests; simplified: the client's copy, at tender price
function add_download_buttons(frm) {
	if (frm.is_new()) return;
	const download = (simplified) => {
		if (frm.is_dirty()) {
			frappe.msgprint(__("Save the tender first so the Excel matches what you see."));
			return;
		}
		if (!frm.doc.manifest_count) {
			frappe.msgprint(__("Add a tender manifest to this tender before downloading it."));
			return;
		}
		const args = `name=${encodeURIComponent(frm.doc.name)}&simplified=${simplified ? 1 : 0}`;
		window.open(`/api/method/${EXCEL_METHOD}?${args}`);
	};
	frm.add_custom_button(__("Detailed Excel"), () => download(false), __("Download"));
	frm.add_custom_button(__("Simplified Excel"), () => download(true), __("Download"));
}

// a manifest for this tender, starting from the tender's defaults
function new_manifest(frm) {
	frappe.new_doc("Tender Manifest", {
		tender: frm.doc.name,
		tender_name: frm.doc.tender_name,
		template: frm.doc.template,
		target_margin_pct: frm.doc.target_margin_pct,
		spec_list: frm.doc.spec_list,
	});
}

function render_manifests(frm) {
	const field = frm.fields_dict.manifests_html;
	if (!field) return;
	const container = field.$wrapper;

	if (frm.is_new()) {
		container.html(
			`<div class="text-muted" style="padding: 12px 0;">${__("Save the tender to add tender manifests.")}</div>`
		);
		return;
	}

	const requested = frm.doc.name;
	container.html(`<div class="text-muted text-center" style="padding: 20px;">${__("Loading...")}</div>`);
	frappe.call({
		method: `${TENDER_METHOD}.get_tender_manifests`,
		args: { tender: requested },
		callback(r) {
			if (requested !== frm.doc.name) return;
			const { manifests = [], totals = {} } = r.message || {};
			show_totals(frm, totals);
			container.html(manifests_html(manifests));
			container.find(".add-manifest-btn").on("click", () => new_manifest(frm));
			container.find(".manifest-row").on("click", function () {
				frappe.set_route("Form", "Tender Manifest", $(this).data("name"));
			});
		},
	});
}

// the totals are saved by the tender manifests, which don't change the tender's modified time, so a
// tender already open in the browser can hold old figures; show the ones the server just worked out
function show_totals(frm, totals) {
	for (const [field, value] of Object.entries(totals)) {
		if (flt(frm.doc[field], 2) === flt(value, 2)) continue;
		frm.doc[field] = value;
		frm.refresh_field(field);
	}
}

function manifests_html(manifests) {
	const esc = frappe.utils.escape_html;
	const add_btn = frappe.model.can_create("Tender Manifest")
		? `<button class="btn btn-${manifests.length ? "xs" : "sm"} btn-default add-manifest-btn">${__("+ New Tender Manifest")}</button>`
		: "";
	const style = `
		<style>
			.tender-manifest-table { width: 100%; border-collapse: collapse; font-size: var(--text-md); color: var(--text-color); }
			.tender-manifest-table thead tr { background: var(--subtle-fg); }
			.tender-manifest-table th { padding: 8px 10px; font-weight: 400; color: var(--text-muted); border-bottom: 1px solid var(--border-color); white-space: nowrap; }
			.tender-manifest-table td { padding: 9px 10px; border-bottom: 1px solid var(--border-color); }
			.tender-manifest-table tbody tr:last-child td { border-bottom: none; }
			.tender-manifest-table tr.manifest-row { cursor: pointer; }
			.tender-manifest-table tr.manifest-row:hover { background: var(--fg-hover-color); }
			.tender-manifest-table .col-num { text-align: right; font-variant-numeric: tabular-nums; }
			.tender-manifest-table tfoot td { font-weight: var(--weight-semibold); border-top: 1px solid var(--border-color); border-bottom: none; }
			.tender-manifests-footer { display: flex; justify-content: flex-end; margin-top: 10px; margin-bottom: 16px; }
		</style>
	`;

	if (!manifests.length) {
		return `${style}
			<div style="text-align: center; padding: 40px 20px; color: var(--text-muted); border: 1px dashed var(--border-color); border-radius: var(--border-radius-md); margin-bottom: 14px;">
				<p style="margin-bottom: 12px;">${__("No tender manifests yet. Add one for each unit type in this tender.")}</p>
				${add_btn}
			</div>`;
	}

	const total = (field) => manifests.reduce((sum, m) => sum + flt(m[field]), 0);
	const rows = manifests
		.map(
			(m) => `
			<tr class="manifest-row" data-name="${esc(m.name)}">
				<td>${esc(m.name)}</td>
				<td>${esc(m.tender_name || "")}</td>
				<td class="text-muted">${esc(m.template || "")}</td>
				<td class="col-num">${format_number(flt(m.kitchens_to_tender), null, 0)}</td>
				<td class="col-num">${format_currency(flt(m.total_cost_per_kitchen))}</td>
				<td class="col-num">${format_currency(flt(m.tender_price_total))}</td>
			</tr>`
		)
		.join("");

	return `${style}
		<div style="border: 1px solid var(--border-color); border-radius: var(--border-radius-md); overflow: hidden;">
			<table class="tender-manifest-table">
				<thead>
					<tr>
						<th>${__("Tender Manifest")}</th>
						<th>${__("Name")}</th>
						<th>${__("Template")}</th>
						<th class="col-num">${__("Units")}</th>
						<th class="col-num">${__("Cost / Unit")}</th>
						<th class="col-num">${__("Tender Price")}</th>
					</tr>
				</thead>
				<tbody>${rows}</tbody>
				<tfoot>
					<tr>
						<td colspan="3">${__("Total")}</td>
						<td class="col-num">${format_number(total("kitchens_to_tender"), null, 0)}</td>
						<td></td>
						<td class="col-num">${format_currency(total("tender_price_total"))}</td>
					</tr>
				</tfoot>
			</table>
		</div>
		<div class="tender-manifests-footer">${add_btn}</div>`;
}
