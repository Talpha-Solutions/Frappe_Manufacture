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
		// Units tab: this tender's manifests, and any project type but Site
		frm.set_query("manifest", "unit_types", () => ({ filters: { tender: frm.doc.name || "__none__" } }));
	},
	download_unit_workbook(frm) {
		if (frm.is_dirty()) {
			frappe.msgprint(__("Save the tender first, so the workbook has the latest units."));
			return;
		}
		window.open(`/api/method/${UNITS_METHOD}.download_unit_workbook?tender=${encodeURIComponent(frm.doc.name)}`);
	},
	unit_workbook(frm) {
		// an uploaded workbook replaces the Units table
		if (frm.doc.unit_workbook && frm.is_dirty()) frm.save().then(() => load_unit_workbook(frm));
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
		add_unit_buttons(frm);
		render_units_preview(frm);
		listen_for_unit_projects(frm);
	},
});

// ---------------------------------------------------------------- Units tab (won tenders)

function add_unit_buttons(frm) {
	if (frm.doc.status !== "Won" || frm.is_new()) return;
	const group = __("Units");
	const saved_first = (fn) => () => {
		if (frm.is_dirty()) {
			frappe.msgprint(__("Save the tender first."));
			return;
		}
		fn();
	};
	if (frm.perm[0]?.write) frm.add_custom_button(__("Add Units"), () => add_units_dialog(frm), group);
	if ((frm.doc.unit_types || []).length) {
		frm.add_custom_button(__("Preview"), saved_first(() => preview_units(frm)), group);
	}
	if (frm.doc.unit_import_status === "Ready" && frappe.model.can_create("Project")) {
		frm.add_custom_button(__("Create Projects"), saved_first(() => confirm_create_units(frm)), group);
	}
	if (frm.doc.project) {
		frm.add_custom_button(__("View Site Project"), () => frappe.set_route("Form", "Project", frm.doc.project), group);
	}
}

// add a run of apartments: one row per apartment per manifest
function add_units_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Units"),
		fields: [
			{ fieldname: "unit_type", fieldtype: "Data", label: __("Apt Type"), reqd: 1, description: __("e.g. 1B2P") },
			{ fieldname: "floor", fieldtype: "Data", label: __("Floor") },
			{ fieldtype: "Column Break" },
			{ fieldname: "numbers", fieldtype: "Data", label: __("Apt Nos"), reqd: 1, description: __("Ranges and single numbers, e.g. 101-110, 115, A1-A4") },
			{ fieldname: "unit_name", fieldtype: "Data", label: __("Unit Name"), description: __("Optional; the same for all of them") },
			{ fieldtype: "Section Break", label: __("Manifests for each apartment") },
			{
				fieldname: "manifests", fieldtype: "Table", label: __("Manifests"), reqd: 1, in_place_edit: true,
				data: [{ qty: 1 }],
				fields: [
					{ fieldname: "manifest", fieldtype: "Link", options: "Tender Manifest", label: __("Manifest"), in_list_view: 1, reqd: 1, columns: 7,
						get_query: () => ({ filters: { tender: frm.doc.name } }) },
					{ fieldname: "qty", fieldtype: "Int", label: __("Qty"), in_list_view: 1, default: 1, columns: 2 },
				],
			},
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			const numbers = expand_apt_numbers(values.numbers);
			const manifests = (values.manifests || []).filter((m) => m.manifest);
			if (!numbers.length || !manifests.length) {
				frappe.msgprint(__("Enter at least one Apt No and one manifest."));
				return;
			}
			const taken = new Set((frm.doc.unit_types || []).map((r) => (r.number || "").toUpperCase()));
			const clash = numbers.filter((n) => taken.has(n.toUpperCase()));
			if (clash.length) {
				frappe.msgprint(__("Already in the table: {0}", [clash.slice(0, 10).join(", ")]));
				return;
			}
			for (const number of numbers) {
				for (const m of manifests) {
					frm.add_child("unit_types", {
						unit_type: values.unit_type.trim(), floor: (values.floor || "").trim(), number,
						unit_name: (values.unit_name || "").trim(), manifest: m.manifest, qty: m.qty || 1,
					});
				}
			}
			frm.refresh_field("unit_types");
			dialog.hide();
			frappe.show_alert({ message: __("Added {0} apartments ({1} rows). Save to keep them.", [numbers.length, numbers.length * manifests.length]), indicator: "green" });
		},
	});
	dialog.show();
}

// "101-110, 115, A1-A4" -> ["101", ..., "110", "115", "A1", ..., "A4"]
function expand_apt_numbers(text) {
	const out = [];
	for (const part of (text || "").split(",").map((p) => p.trim()).filter(Boolean)) {
		const range = part.match(/^(\D*)(\d+)\s*-\s*\1?(\d+)$/);
		if (!range) {
			out.push(part);
			continue;
		}
		const [, prefix, from, to] = range;
		const width = from.length;
		for (let n = parseInt(from, 10); n <= parseInt(to, 10) && out.length < 5000; n++) {
			out.push(prefix + String(n).padStart(width, "0"));
		}
	}
	return [...new Set(out)];
}

function load_unit_workbook(frm) {
	frappe.call({
		method: `${UNITS_METHOD}.upload_unit_workbook`,
		args: { tender: frm.doc.name },
		freeze: true,
		freeze_message: __("Reading the workbook..."),
		callback(r) {
			const result = r.message || {};
			if ((result.errors || []).length) {
				frappe.msgprint({
					title: __("The workbook wasn't loaded"),
					message: `<p>${__("The Units table is unchanged. Fix these in the workbook and attach it again:")}</p><ul>${result.errors.slice(0, 30).map((e) => `<li>${e}</li>`).join("")}</ul>`,
					indicator: "red",
				});
				return;
			}
			frappe.show_alert({ message: __("Loaded {0} rows into the Units table.", [result.loaded]), indicator: "green" });
			frm.__fk_units_preview_for = null;
			frm.reload_doc();
		},
	});
}

function render_units_preview(frm) {
	const field = frm.fields_dict.units_preview_html;
	if (!field) return;
	if (frm.doc.status !== "Won" || !(frm.doc.unit_types || []).length) {
		field.$wrapper.html(
			`<div class="text-muted" style="padding: 8px 0;">${__("Add units with Units → Add Units, or download the workbook, fill it in and attach it above.")}</div>`
		);
		return;
	}
	if (frm.__fk_units_preview_for === frm.doc.modified) {
		field.$wrapper.html(frm.__fk_units_preview_html);
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
			const html = units_preview_html(r.message || {});
			frm.__fk_units_preview_for = modified;
			frm.__fk_units_preview_html = html;
			field.$wrapper.html(html);
			if ((r.message || {}).status && r.message.status !== frm.doc.unit_import_status) {
				frm.doc.unit_import_status = r.message.status;
				frm.refresh_field("unit_import_status");
				frm.clear_custom_buttons();
				frm.refresh();
			}
		},
	});
}

function units_preview_html(p) {
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
		</style>`;
	const messages = [
		...(p.errors || []).map((m) => `<div class="fk-units-msg error">${m}</div>`),
		...(p.warnings || []).map((m) => `<div class="fk-units-msg warning">${m}</div>`),
	].join("");
	if (!(p.types || []).length) return `${style}<div class="fk-units">${messages}</div>`;

	const card = (value, label) => `<div class="fk-units-card"><div class="value">${esc(String(value))}</div><div class="label">${esc(label)}</div></div>`;
	const cards = [
		card(p.site_name, p.site_exists ? __("Site (exists, updated)") : __("Site (new)")),
		card(p.types.length, __("Apartment types")),
		card((p.apartments || []).length, __("Apartments")),
		...Object.entries(p.project_counts || {}).map(([pt, n]) => card(n, __("{0} projects", [__(pt)]))),
	].join("");
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
			return `<tr><td>${esc(a.number)}</td><td>${esc(a.floor || "")}</td><td>${esc(a.name || "")}</td>${cells}</tr>`;
		}).join("");
		const more = apartments.length > shown.length ? `<div class="text-muted" style="padding: 6px 12px;">${__("and {0} more", [apartments.length - shown.length])}</div>` : "";
		return `
			<div class="fk-units-type">
				<div class="fk-units-type-head"><span>${esc(t.code || __("(no type)"))}</span><span class="text-muted">${__("{0} apartments", [t.apartments])}</span></div>
				<table class="fk-units-table"><thead><tr><th>${__("Project Type")}</th><th>${__("Manifest")}</th><th class="num">${__("Apartments")}</th></tr></thead><tbody>${used}</tbody></table>
				<details class="fk-units-list"><summary>${__("Show apartments")}</summary>
					<table class="fk-units-table"><thead><tr><th>${__("Apt No")}</th><th>${__("Floor")}</th><th>${__("Unit Name")}</th>${(p.project_types || []).map((pt) => `<th>${esc(__(pt))}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table>${more}
				</details>
			</div>`;
	}).join("");
	return `${style}<div class="fk-units">${messages}${lead}<div class="fk-units-cards">${cards}</div>${types}</div>`;
}

function confirm_create_units(frm) {
	frappe.confirm(
		__("Create the site, apartment types and apartment projects from the Units table? Existing projects with the same Apt No are updated."),
		() => frappe.call({
			method: `${UNITS_METHOD}.create_unit_projects`,
			args: { tender: frm.doc.name },
			freeze: true,
			freeze_message: __("Starting..."),
			callback() {
				frappe.show_alert({ message: __("Creating the unit projects. This page updates when it's done."), indicator: "blue" });
				frm.reload_doc();
			},
		})
	);
}

function listen_for_unit_projects(frm) {
	if (frm.__fk_units_listening) return;
	frm.__fk_units_listening = true;
	frappe.realtime.on("tender_units_done", (data) => {
		if (!data || data.tender !== frm.doc.name) return;
		frappe.show_alert({
			message: data.ok ? data.summary : __("Creating the unit projects failed; see the summary on the Units tab."),
			indicator: data.ok ? "green" : "red",
		}, 10);
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
