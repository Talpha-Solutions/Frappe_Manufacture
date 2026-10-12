// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

const TENDER_METHOD = "fitzgerald_kitchens.fitzgerald_kitchens.doctype.tender.tender";
const EXCEL_METHOD = "fitzgerald_kitchens.fitzgerald_kitchens.doctype.tender.tender_excel.download_tender_excel";

frappe.ui.form.on("Tender", {
	refresh(frm) {
		add_status_button(frm);
		add_download_buttons(frm);
		render_manifests(frm);
	},
});

// status is read-only on the form and changed here, like Set Project Status on Project
function add_status_button(frm) {
	if (frm.is_new() || !frm.perm[0]?.write) return;
	frm.add_custom_button(__("Set Tender Status"), () => status_dialog(frm), __("Actions"));
}

function status_dialog(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save the tender first."));
		return;
	}
	const options = (frappe.meta.get_docfield("Tender", "status").options || "")
		.split("\n")
		.filter((status) => status && status !== frm.doc.status);
	const dialog = new frappe.ui.Dialog({
		title: __("Set Tender Status"),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "current",
				options: `<p class="text-muted">${__("Current status: {0}", [`<b>${__(frm.doc.status)}</b>`])}</p>`,
			},
			{ fieldname: "status", fieldtype: "Select", label: __("New Status"), reqd: 1, options: options.join("\n") },
		],
		primary_action_label: __("Set Status"),
		primary_action({ status }) {
			dialog.hide();
			frappe
				.xcall(`${TENDER_METHOD}.set_tender_status`, { tender: frm.doc.name, status })
				.then(() => {
					frappe.show_alert({ message: __("Tender status set to {0}", [__(status)]), indicator: "green" });
					frm.reload_doc();
				});
		},
	});
	dialog.show();
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
