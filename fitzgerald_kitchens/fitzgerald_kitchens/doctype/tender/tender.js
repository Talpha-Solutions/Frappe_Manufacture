// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

const TENDER_METHOD = "fitzgerald_kitchens.fitzgerald_kitchens.doctype.tender.tender";
const TEMPLATE_QUERY = "fitzgerald_kitchens.fitzgerald_kitchens.doctype.tender_configuration_template.tender_configuration_template.template_query";
const EXCEL_METHOD = "fitzgerald_kitchens.fitzgerald_kitchens.doctype.tender.tender_excel.download_tender_excel";
// matches LOCKED_TENDER_STATUSES in tender_manifest.py: manifests are fixed while with the client or closed
const LOCKED_STATUSES = ["Submitted", "Lost", "Cancelled"];
const UNITS_METHOD = "fitzgerald_kitchens.fitzgerald_kitchens.doctype.tender.tender_units";

frappe.ui.form.on("Tender", {
	setup(frm) {
		frm.set_query("party_type", () => ({ filters: { name: ["in", ["Lead", "Customer"]] } }));
		// the customer's own templates if they have any, otherwise those for everyone
		frm.set_query("template", () => ({
			query: TEMPLATE_QUERY,
			filters: { party_type: frm.doc.party_type || "", party_name: frm.doc.party_name || "" },
		}));
	},
	party_type(frm) {
		// the party belongs to the old type
		frm.set_value("party_name", "");
	},
	refresh(frm) {
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
		render_units_preview(frm);
		listen_for_unit_projects(frm);
	},
});

// ---------------------------------------------------------------- Units tab (won tenders)
// The tab only shows the units and their projects; they're set up on the Tender Units page.

function open_units_editor(frm) {
	// a page of its own, opened in a new tab beside the tender
	window.open(`/desk/tender-units?tender=${encodeURIComponent(frm.doc.name)}`, "_blank");
}

function render_units_preview(frm) {
	const field = frm.fields_dict.units_preview_html;
	if (!field) return;
	if (frm.doc.status !== "Won") return;
	if (!(frm.doc.unit_types || []).length) {
		show_units_panel(frm, units_empty_html(frm));
		return;
	}
	if (frm.__fk_units_preview_for === frm.doc.modified) {
		show_units_panel(frm, frm.__fk_units_preview_html);
		return;
	}
	if (!frm.is_dirty()) preview_units(frm);
}

function preview_units(frm) {
	const field = frm.fields_dict.units_preview_html;
	const modified = frm.doc.modified;
	field.$wrapper.html(`<div class="text-muted text-center" style="padding: 20px;">${__("Checking the units...")}</div>`);
	frappe.call({
		method: `${UNITS_METHOD}.preview_units`,
		args: { tender: frm.doc.name },
		callback(r) {
			if (frm.doc.modified !== modified) return;
			const html = units_preview_html(r.message || {}, frm);
			frm.__fk_units_preview_for = modified;
			frm.__fk_units_preview_html = html;
			show_units_panel(frm, html);
			if ((r.message || {}).status && r.message.status !== frm.doc.unit_import_status) {
				frm.doc.unit_import_status = r.message.status;
				frm.refresh_field("unit_import_status");
			}
		},
	});
}

// put the panel on the tab and wire its buttons
function show_units_panel(frm, html) {
	const $w = frm.fields_dict.units_preview_html.$wrapper;
	$w.html(html);
	$w.find("[data-units-action]").on("click", function () {
		const action = $(this).data("units-action");
		if (action === "editor") open_units_editor(frm);
		if (action === "site") frappe.set_route("Form", "Project", frm.doc.project);
	});
}

function units_empty_html(frm) {
	return `
		<div style="text-align: center; padding: 32px 20px; color: var(--text-muted); border: 1px dashed var(--border-color); border-radius: var(--border-radius-md);">
			<p style="margin-bottom: 12px;">${__("No units yet. Set them up in the Units Editor: type them in, paste them from Excel or upload the unit workbook.")}</p>
			<button class="btn btn-sm btn-primary" data-units-action="editor">${__("Open Units Editor")}</button>
		</div>`;
}

// status line and actions above the preview
function units_actions_html(p, frm) {
	const sync = p.sync || {};
	const created = !!frm.doc.project;
	const pending = (sync.new || 0) + (sync.changed || 0);
	let status;
	if (frm.doc.unit_import_status === "Creating") status = `<span class="indicator-pill orange">${__("Creating projects…")}</span>`;
	else if (frm.doc.unit_import_status === "Failed" && created) status = `<span class="indicator-pill red">${__("Last sync failed")}</span>`;
	else if (!created) status = `<span class="indicator-pill gray">${__("Projects not created yet")}</span>`;
	else if (!pending) status = `<span class="indicator-pill green">${__("All apartments in sync")}</span>`;
	else status = `<span class="indicator-pill orange">${__("{0} to sync", [pending])}</span>`;

	const buttons = [
		`<button class="btn btn-sm btn-primary" data-units-action="editor">${__("Open Units Editor")}</button>`,
		created ? `<button class="btn btn-sm btn-default" data-units-action="site">${__("View Site Project")}</button>` : "",
	].join(" ");
	// the last create / sync run's summary
	const summary = frm.doc.unit_import_summary
		? `<div class="text-muted small" style="margin-top: 6px; white-space: pre-line;">${frappe.utils.escape_html(frm.doc.unit_import_summary)}</div>`
		: "";
	return `
		<div class="fk-units-actions">
			<div>${status}${summary}</div>
			<div class="fk-units-buttons">${buttons}</div>
		</div>`;
}

function units_preview_html(p, frm) {
	const esc = frappe.utils.escape_html;
	const style = `
		<style>
			.fk-units { font-size: var(--text-md); color: var(--text-color); }
			.fk-units-cards { display: flex; flex-wrap: wrap; gap: var(--margin-sm); margin-bottom: var(--margin-md); }
			.fk-units-card { border: 1px solid var(--border-color); border-radius: var(--border-radius-md); padding: 10px 14px; min-width: 120px; }
			.fk-units-card .value { font-size: var(--text-xl); font-weight: var(--weight-semibold); }
			.fk-units-card .label { color: var(--text-muted); font-size: var(--text-sm); }
			.fk-units-msg { border-radius: var(--border-radius-md); padding: 8px 12px; margin-bottom: var(--margin-sm); }
			.fk-units-msg.error { background: var(--red-50); color: var(--red-700); }
			.fk-units-msg.warning { background: var(--yellow-50); color: var(--yellow-800); }
			.fk-units-type { border: 1px solid var(--border-color); border-radius: var(--border-radius-md); margin-bottom: var(--margin-md); overflow: hidden; }
			.fk-units-type-head { background: var(--subtle-fg); padding: 8px 12px; font-weight: var(--weight-semibold); display: flex; justify-content: space-between; }
			.fk-units-table { width: 100%; border-collapse: collapse; }
			.fk-units-table th { color: var(--text-muted); font-weight: 400; text-align: left; padding: 6px 12px; border-bottom: 1px solid var(--border-color); }
			.fk-units-table td { padding: 6px 12px; border-bottom: 1px solid var(--border-color); }
			.fk-units-table tr:last-child td { border-bottom: none; }
			.fk-units-table .num { text-align: right; font-variant-numeric: tabular-nums; }
			.fk-units-list summary { cursor: pointer; padding: 8px 12px; color: var(--text-muted); }
			.fk-units-actions { display: flex; justify-content: space-between; align-items: center; gap: var(--margin-sm); flex-wrap: wrap;
				padding: 10px 12px; border: 1px solid var(--border-color); border-radius: var(--border-radius-md); margin-bottom: var(--margin-md); }
			.fk-units-buttons { display: flex; gap: var(--margin-xs); flex-wrap: wrap; }
		</style>`;
	const messages = [
		...(p.errors || []).map((m) => `<div class="fk-units-msg error">${m}</div>`),
		...(p.warnings || []).map((m) => `<div class="fk-units-msg warning">${m}</div>`),
	].join("");
	const actions = units_actions_html(p, frm);
	if (!(p.types || []).length) return `${style}<div class="fk-units">${actions}${messages}</div>`;

	const card = (value, label) => `<div class="fk-units-card"><div class="value">${esc(String(value))}</div><div class="label">${esc(label)}</div></div>`;
	const cards = [
		card(p.site_name, p.site_exists ? __("Site (exists, updated)") : __("Site (new)")),
		card(p.types.length, __("Apartment types")),
		card((p.apartments || []).length, __("Apartments")),
		...Object.entries(p.project_counts || {}).map(([pt, n]) => card(n, __("{0} projects", [__(pt)]))),
		...(frm.doc.project ? [card((p.sync || {}).synced || 0, __("In sync")), card(((p.sync || {}).changed || 0) + ((p.sync || {}).new || 0), __("To sync"))] : []),
	].join("");
	const orphans = (p.not_in_table || []).length
		? `<div class="fk-units-msg warning">${__("Projects exist for apartments no longer in the table (kept, not deleted): {0}", [p.not_in_table.map(esc).join(", ")])}</div>`
		: "";
	const lead = p.party_is_lead
		? `<div class="fk-units-msg warning">${__("{0} is a Lead; it will be converted to a Customer when the projects are created.", [esc(p.party || "")])}</div>`
		: "";
	const manifest_link = (m) => `<a href="/desk/tender-manifest/${encodeURIComponent(m.manifest)}">${esc(m.manifest)}</a> <span class="text-muted">${esc(m.manifest_name || "")}</span>`;

	const types = p.types.map((t) => {
		const used = t.manifests.map((m) => `
			<tr><td>${esc(__(m.project_type))}</td><td>${manifest_link(m)}</td><td class="num">${m.apartments}</td></tr>`).join("");
		const apartments = (p.apartments || []).filter((a) => a.type === t.code);
		const shown = apartments.slice(0, 200);
		const rows = shown.map((a) => {
			const cells = (p.project_types || []).map((pt) => {
				const r = a.rows.find((x) => x.project_type === pt);
				return `<td>${r ? `${esc(r.manifest)}${r.qty > 1 ? ` × ${r.qty}` : ""}` : ""}</td>`;
			}).join("");
			const pill = {
				synced: `<span class="indicator-pill green">${__("In sync")}</span>`,
				changed: `<span class="indicator-pill orange" title="${esc((a.changes || []).join(", "))}">${__("Changed")}</span>`,
				new: `<span class="indicator-pill blue">${__("New")}</span>`,
			}[a.sync];
			const changes = a.sync === "changed" ? `<div class="text-muted small">${esc((a.changes || []).join(", "))}</div>` : "";
			const state = frm.doc.project ? `<td>${pill || ""}${changes}</td>` : "";
			return `<tr><td>${esc(a.number)}</td><td>${esc(a.floor || "")}</td><td>${esc(a.name || "")}</td>${cells}${state}</tr>`;
		}).join("");
		const more = apartments.length > shown.length ? `<div class="text-muted" style="padding: 6px 12px;">${__("and {0} more", [apartments.length - shown.length])}</div>` : "";
		return `
			<div class="fk-units-type">
				<div class="fk-units-type-head"><span>${esc(t.code || __("(no type)"))}</span><span class="text-muted">${__("{0} apartments", [t.apartments])}</span></div>
				<table class="fk-units-table"><thead><tr><th>${__("Project Type")}</th><th>${__("Manifest")}</th><th class="num">${__("Apartments")}</th></tr></thead><tbody>${used}</tbody></table>
				<details class="fk-units-list"><summary>${__("Show apartments")}</summary>
					<table class="fk-units-table"><thead><tr><th>${__("Apt No")}</th><th>${__("Floor")}</th><th>${__("Unit Name")}</th>${(p.project_types || []).map((pt) => `<th>${esc(__(pt))}</th>`).join("")}${frm.doc.project ? `<th>${__("Status")}</th>` : ""}</tr></thead><tbody>${rows}</tbody></table>${more}
				</details>
			</div>`;
	}).join("");
	// each manifest's tendered Units against how many the apartments use
	const allocation = (p.allocation || []).length ? `
		<div class="fk-units-type">
			<div class="fk-units-type-head"><span>${__("Manifests: tendered vs in the units")}</span></div>
			<table class="fk-units-table">
				<thead><tr><th>${__("Manifest")}</th><th>${__("Project Type")}</th><th class="num">${__("Tendered")}</th>
					<th class="num">${__("In the units")}</th><th class="num">${__("Apartments")}</th><th></th></tr></thead>
				<tbody>${p.allocation.map((m) => {
					const diff = m.allocated - m.tendered;
					const pill = diff === 0
						? `<span class="indicator-pill green">${__("Matches")}</span>`
						: `<span class="indicator-pill orange">${diff < 0 ? __("{0} short", [-diff]) : __("{0} over", [diff])}</span>`;
					return `<tr><td>${manifest_link({ manifest: m.manifest, manifest_name: m.label.split(" · ").slice(1).join(" · ") })}</td>
						<td>${esc(__(m.project_type))}</td><td class="num">${m.tendered}</td><td class="num">${m.allocated}</td>
						<td class="num">${m.apartments}</td><td>${pill}</td></tr>`;
				}).join("")}</tbody>
			</table>
		</div>` : "";
	return `${style}<div class="fk-units">${actions}${messages}${lead}${orphans}<div class="fk-units-cards">${cards}</div>${allocation}${types}</div>`;
}

function listen_for_unit_projects(frm) {
	if (frm.__fk_units_listening) return;
	frm.__fk_units_listening = true;
	frappe.realtime.on("tender_units_done", (data) => {
		if (!data || data.tender !== frm.doc.name) return;
		// the Tender Units page that started the run shows the alert; here the tab just catches up
		frm.__fk_units_preview_for = null;
		frm.reload_doc();
	});
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
			container.html(manifests_html(manifests, LOCKED_STATUSES.includes(frm.doc.status)));
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

function manifests_html(manifests, locked) {
	const esc = frappe.utils.escape_html;
	const add_btn = frappe.model.can_create("Tender Manifest") && !locked
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
				<td>${esc(__(m.project_type || "Kitchen"))}</td>
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
						<th>${__("Type")}</th>
						<th>${__("Template")}</th>
						<th class="col-num">${__("Units")}</th>
						<th class="col-num">${__("Cost / Unit")}</th>
						<th class="col-num">${__("Tender Price")}</th>
					</tr>
				</thead>
				<tbody>${rows}</tbody>
				<tfoot>
					<tr>
						<td colspan="4">${__("Total")}</td>
						<td class="col-num">${format_number(total("kitchens_to_tender"), null, 0)}</td>
						<td></td>
						<td class="col-num">${format_currency(total("tender_price_total"))}</td>
					</tr>
				</tfoot>
			</table>
		</div>
		<div class="tender-manifests-footer">${add_btn}</div>`;
}
