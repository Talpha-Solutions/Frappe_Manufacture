// Tender Units: a full-width spreadsheet editor for a Won tender's apartments, without the desk sidebar.
// Save writes them to the tender's Units table (a row per apartment per manifest) with the Site Name,
// Company and Project Template; the unit workbook is downloaded and uploaded here, and the projects
// are created and synced from here. The tender's Units tab only shows the result.

const TU_METHOD = "fitzgerald_kitchens.fitzgerald_kitchens.doctype.tender.tender_units";
const TU_COLOURS = ["#4C6EF5", "#12B886", "#F59F00", "#E64980", "#7950F2", "#15AABF", "#FA5252", "#82C91E", "#FD7E14", "#868E96"];
const TU_SYNC = {
	new: { label: __("New"), colour: "blue" },
	changed: { label: __("To sync"), colour: "orange" },
	synced: { label: __("In sync"), colour: "green" },
	edited: { label: __("Edited"), colour: "purple" },
};

frappe.pages["tender-units"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Tender Units"), single_column: true, hide_sidebar: true });
	wrapper.tender_units = new TenderUnits(page, wrapper);
};

frappe.pages["tender-units"].on_page_show = function (wrapper) {
	const tender = frappe.route_options?.tender || frappe.utils.get_query_params().tender;
	frappe.route_options = null;
	if (tender && wrapper.tender_units) wrapper.tender_units.set_tender(tender);
};

class TenderUnits {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = wrapper;
		this.apts = [];
		this.selected = new Set();
		this.next_id = 1;
		this.dirty = false;
		// one line above everything: the tender, then its site name, company and project template
		this.$top = $(`<div class="fk-tu-top"><div class="fk-tu-setting fk-tu-tender"></div><div class="fk-tu-setup"></div></div>`).appendTo(page.main);
		this.make_toolbar();
		this.$body = $(`<div class="fk-tu"></div>`).appendTo(page.main);
		this.add_styles();
		this.render();
		frappe.realtime.on("tender_units_done", (data) => {
			if (!data || !this.data || data.tender !== this.data.tender.name) return;
			frappe.show_alert({
				message: data.ok ? data.summary : __("Creating the unit projects failed; see the summary on the tender's Units tab."),
				indicator: data.ok ? "green" : "red",
			}, 10);
			this.load();
		});
		$(window).on("beforeunload.fk_tender_units", () => (this.dirty ? true : undefined));
	}

	// ------------------------------------------------------------ toolbar and loading

	make_toolbar() {
		this.tender_field = frappe.ui.form.make_control({
			df: {
				fieldtype: "Link",
				fieldname: "tender",
				options: "Tender",
				label: __("Tender"),
				get_query: () => ({ filters: { status: "Won" } }),
				change: () => {
					const value = this.tender_field.get_value();
					if (value && value !== this.data?.tender.name) this.set_tender(value);
				},
			},
			parent: this.$top.find(".fk-tu-tender"),
			render_input: true,
		});
		this.page.set_primary_action(__("Save"), () => this.save(), "save");
		this.page.add_inner_button(__("Open Tender"), () => this.data && frappe.set_route("Form", "Tender", this.data.tender.name));
		this.page.add_menu_item(__("Reload"), () => this.confirm_discard(() => this.load()));
		this.page.add_inner_button(__("Download"), () => this.download_workbook(), __("Workbook"));
		this.page.add_inner_button(__("Upload"), () => this.upload_workbook(), __("Workbook"));
	}

	// ------------------------------------------------------------ workbook

	download_workbook() {
		if (!this.data) return;
		if (this.dirty) return frappe.msgprint(__("Save first, so the workbook has your latest changes."));
		window.open(`/api/method/${TU_METHOD}.download_unit_workbook?tender=${encodeURIComponent(this.data.tender.name)}`);
	}

	// the file is attached to the tender, then its Units sheet replaces the units here
	upload_workbook() {
		if (!this.data?.tender.can_write) return;
		this.confirm_discard(() => new frappe.ui.FileUploader({
			doctype: "Tender",
			docname: this.data.tender.name,
			restrictions: { allowed_file_types: [".xlsx"] },
			on_success: (file) => frappe.call({
				method: `${TU_METHOD}.upload_unit_workbook`,
				args: { tender: this.data.tender.name, file_url: file.file_url },
				freeze: true,
				freeze_message: __("Reading the workbook..."),
				callback: (r) => {
					const res = r.message || {};
					if ((res.errors || []).length) {
						frappe.msgprint({
							title: __("The workbook wasn't loaded"),
							indicator: "red",
							message: `<p>${__("The units are unchanged. Fix these in the workbook and upload it again:")}</p>
								<ul>${res.errors.slice(0, 30).map((e) => `<li>${e}</li>`).join("")}</ul>`,
						});
						return;
					}
					frappe.show_alert({ message: __("Loaded {0} apartments from the workbook.", [res.loaded]), indicator: "green" });
					this.set_dirty(false);
					this.load();
				},
			}),
		}));
	}

	set_tender(name) {
		if (this.data?.tender.name === name) return;
		this.confirm_discard(() => {
			this.tender_field.set_value(name);
			this.load(name);
		}, () => this.tender_field.set_value(this.data?.tender.name || ""));
	}

	confirm_discard(proceed, cancel) {
		if (!this.dirty) return proceed();
		frappe.confirm(__("You have unsaved changes. Discard them?"), proceed, cancel);
	}

	load(name) {
		name = name || this.data?.tender.name;
		if (!name) return;
		frappe.call({
			method: `${TU_METHOD}.get_unit_editor`,
			args: { tender: name },
			freeze: true,
			callback: (r) => this.set_data(r.message),
			error: () => {
				this.data = null;
				this.render();
			},
		});
	}

	set_data(data) {
		this.data = data;
		this.apts = (data.apartments || []).map((a) => ({ ...a, _id: this.next_id++ }));
		const t = data.tender;
		this.settings = { site_name: t.unit_site_name || "", company: t.company || "", project_template: t.project_template || "" };
		this.selected.clear();
		this.set_dirty(false);
		this.page.set_title(__("Tender Units") + ` · ${frappe.utils.escape_html(data.tender.tender_name || data.tender.name)}`);
		this.update_actions();
		this.render();
	}

	set_dirty(dirty) {
		if (dirty && this.dirty) return;
		this.dirty = dirty;
		if (dirty) this.page.set_indicator(__("Not Saved"), "orange");
		else if (this.data) this.page.set_indicator(...this.status_indicator());
		else this.page.clear_indicator();
		this.update_actions();
	}

	status_indicator() {
		const t = this.data.tender;
		const pending = (this.data.sync?.new || 0) + (this.data.sync?.changed || 0);
		if (t.status === "Creating") return [__("Creating projects…"), "orange"];
		if (t.status === "Failed" && t.project) return [__("Last sync failed"), "red"];
		if (!t.project) return [__("Projects not created yet"), "gray"];
		return pending ? [__("{0} to sync", [pending]), "orange"] : [__("All in sync"), "green"];
	}

	update_actions() {
		const t = this.data?.tender;
		this.page.btn_primary.toggle(!!t?.can_write);
		this.page.remove_inner_button(__("Create Projects"));
		this.page.remove_inner_button(__("Sync Projects"));
		this.page.remove_inner_button(__("View Site Project"));
		if (!t) return;
		const pending = (this.data.sync?.new || 0) + (this.data.sync?.changed || 0);
		if (t.can_create_projects && t.status !== "Creating" && (!t.project || pending || this.dirty)) {
			const label = t.project ? __("Sync Projects") : __("Create Projects");
			this.page.add_inner_button(label, () => this.create_projects(!!t.project));
		}
		if (t.project) this.page.add_inner_button(__("View Site Project"), () => frappe.set_route("Form", "Project", t.project));
	}

	save(after) {
		if (!this.data) return;
		frappe.call({
			method: `${TU_METHOD}.save_unit_editor`,
			args: { tender: this.data.tender.name, apartments: JSON.stringify(this.payload()), settings: JSON.stringify(this.settings) },
			freeze: true,
			freeze_message: __("Saving..."),
			callback: (r) => {
				const res = r.message;
				if (!res.ok) {
					this.save_errors = res.errors;
					this.render_messages();
					frappe.msgprint({
						title: __("Not saved"),
						indicator: "red",
						message: `<ul>${res.errors.slice(0, 20).map((e) => `<li>${e}</li>`).join("")}</ul>` +
							(res.errors.length > 20 ? `<p>${__("…and {0} more.", [res.errors.length - 20])}</p>` : ""),
					});
					return;
				}
				this.save_errors = null;
				this.set_data(res);
				frappe.show_alert({ message: __("Saved"), indicator: "green" });
				after && after();
			},
		});
	}

	payload() {
		return this.sorted(this.apts).map((a) => ({
			number: a.number, type: a.type, floor: a.floor, name: a.name,
			manifests: Object.fromEntries(Object.entries(a.manifests || {}).filter(([, m]) => m && m.manifest)),
		}));
	}

	create_projects(syncing) {
		// the page can be saved with no apartments, but there's nothing to create from it
		if (!this.apts.length) return frappe.msgprint(__("Add the apartments first: there are no units to create projects for."));
		const { issues, counts } = this.checks();
		if (issues.length) {
			return frappe.msgprint({ title: __("Fix these first"), indicator: "red", message: `<ul>${issues.map((i) => `<li>${i}</li>`).join("")}</ul>` });
		}
		const off = counts.filter((c) => !c.ok).map((c) => `<li>${c.text}</li>`).join("");
		const go = () => frappe.confirm(
			(off ? `<p><b>${__("These don't match the tender:")}</b></p><ul>${off}</ul><p>${__("Go ahead anyway?")}</p>` : "") +
			(syncing
				? __("Update the projects to match these apartments, and create projects for new ones? Projects for apartments no longer here are kept.")
				: __("Create the site, apartment types and apartment projects from these apartments?")),
			() => frappe.call({
				method: `${TU_METHOD}.create_unit_projects`,
				args: { tender: this.data.tender.name },
				freeze: true,
				freeze_message: __("Starting..."),
				callback: () => {
					frappe.show_alert({ message: __("Working on the unit projects. This page updates when it's done."), indicator: "blue" });
					this.load();
				},
			})
		);
		if (this.dirty) frappe.confirm(__("Save your changes first?"), () => this.save(go));
		else go();
	}

	// ------------------------------------------------------------ model helpers

	touch(apt) {
		apt.sync = "edited";
		apt.changes = [];
		this.set_dirty(true);
	}

	types() {
		return [...new Set(this.apts.map((a) => a.type).filter(Boolean))].sort();
	}

	colour(type) {
		const i = this.types().indexOf(type);
		return i < 0 ? "var(--gray-400)" : TU_COLOURS[i % TU_COLOURS.length];
	}

	manifests_for(project_type) {
		return (this.data?.manifests || []).filter((m) => m.project_type === project_type);
	}

	// a manifest typed or pasted by name, label or tender manifest name
	find_manifest(project_type, text) {
		text = (text || "").trim().toLowerCase();
		if (!text) return null;
		const list = this.manifests_for(project_type);
		return (list.find((m) => m.name.toLowerCase() === text) ||
			list.find((m) => m.label.toLowerCase() === text) ||
			list.find((m) => m.label.toLowerCase().includes(text)) || {}).name || null;
	}

	sorted(apts) {
		return [...apts].sort((a, b) => compare_floor(b.floor, a.floor) || natural(a.number, b.number));
	}

	// ------------------------------------------------------------ rendering

	render() {
		if (!this.data) {
			this.$top.find(".fk-tu-setup").empty();
			this.$body.html(`<div class="fk-tu-empty">
				<p>${__("Pick a Won tender above to set up its apartments.")}</p></div>`);
			return;
		}
		const t = this.data.tender;
		this.$body.html(`
			<div class="fk-tu-dashboard"></div>
			<div class="fk-tu-head">
				<div class="fk-tu-facts">
					<span class="text-muted">${frappe.utils.escape_html(t.party || "")}${t.party_type === "Lead" ? ` (${__("Lead")}, ${__("converted to a Customer when the projects are created")})` : ""}</span>
					<span class="fk-tu-counts"></span>
				</div>
			</div>
			<div class="fk-tu-messages"></div>
			<div class="fk-tu-view"></div>`);
		if (!this.data.manifests.length) {
			this.$body.find(".fk-tu-view").html(`<div class="fk-tu-empty">${__("This tender has no manifests yet.")}</div>`);
			return;
		}
		this.render_setup();
		this.render_messages();
		this.render_counts();
		this.render_grid();
	}

	// Site Name, Company and Project Template: what Create Projects builds with, saved with the units
	render_setup() {
		const t = this.data.tender;
		const $setup = this.$top.find(".fk-tu-setup").empty();
		// Site Name and Company come from the tender (set when it's won) and are shown, not changed, here
		const fields = [
			{ fieldname: "site_name", fieldtype: "Data", label: __("Site Name"), read_only: 1 },
			{ fieldname: "company", fieldtype: "Link", options: "Company", label: __("Company"), read_only: 1 },
			{ fieldname: "project_template", fieldtype: "Link", options: "Project Template", label: __("Project Template"), read_only: t.can_write ? 0 : 1 },
		];
		if (!this.settings.site_name) this.settings.site_name = t.site_name || "";
		for (const df of fields) {
			const control = frappe.ui.form.make_control({
				df: { ...df, change: () => {
					const value = control.get_value() || "";
					if (value === this.settings[df.fieldname]) return;
					this.settings[df.fieldname] = value;
					this.set_dirty(true);
				} },
				parent: $(`<div class="fk-tu-setting"></div>`).appendTo($setup),
				render_input: true,
			});
			control.set_value(this.settings[df.fieldname]);
		}
	}

	// what's wrong with the apartments as they are on screen (Save would refuse these), and the counts
	// against the tender: apartments vs Number of Units, and each manifest's tendered Units vs the units' Qty
	checks() {
		const issues = [], seen = {}, esc = frappe.utils.escape_html;
		this.apts.forEach((a, i) => {
			const label = a.number ? __("Apt {0}", [esc(a.number)]) : __("Row {0}", [i + 1]);
			if (!a.number) issues.push(__("{0} has no Apt No.", [label]));
			else if (seen[a.number.toUpperCase()]) issues.push(__("Apt No {0} is used twice.", [esc(a.number)]));
			if (a.number) seen[a.number.toUpperCase()] = true;
			if (!a.type) issues.push(__("{0} has no Apt Type.", [label]));
			if (!a.manifests?.Kitchen?.manifest) issues.push(__("{0} has no Kitchen manifest.", [label]));
		});
		const target = this.data.tender.number_of_units;
		const counts = [];
		if (target) {
			counts.push({ ok: this.apts.length === target, text: __("{0} apartments; the tender has {1} units.", [this.apts.length, target]) });
		}
		const allocation = this.data.manifests.map((m) => {
			let allocated = 0, apartments = 0;
			for (const a of this.apts) {
				const row = a.manifests?.[m.project_type];
				if (row?.manifest === m.name) {
					allocated += row.qty || 1;
					apartments += 1;
				}
			}
			return { ...m, allocated, apartments };
		});
		for (const m of allocation) {
			counts.push({ ok: m.allocated === m.tendered, text: __("{0}: {1} in the units, {2} tendered.", [esc(m.label), m.allocated, m.tendered]) });
		}
		return { issues, counts, allocation };
	}

	render_dashboard() {
		const { issues, counts, allocation } = this.checks();
		const esc = frappe.utils.escape_html;
		const off = counts.filter((c) => !c.ok).length;
		const rows = allocation.map((m) => {
			const diff = m.allocated - m.tendered;
			const pct = m.tendered ? Math.min(100, Math.round((m.allocated / m.tendered) * 100)) : m.allocated ? 100 : 0;
			const state = diff === 0 ? "ok" : "warn";
			const status = diff === 0 ? __("Matches") : diff < 0 ? __("{0} short", [-diff]) : __("{0} over", [diff]);
			return `<tr>
				<td>${esc(m.label)}</td>
				<td class="text-muted">${esc(m.project_type)}</td>
				<td class="num">${m.tendered}</td>
				<td class="num">${m.allocated}</td>
				<td class="num text-muted">${m.apartments}</td>
				<td class="fk-tu-bar-cell"><div class="fk-tu-bar ${state}"><i style="width:${pct}%"></i></div></td>
				<td><span class="indicator-pill ${diff === 0 ? "green" : "orange"}">${status}</span></td>
			</tr>`;
		}).join("");
		const issue_list = issues.length ? `
			<div class="fk-tu-issues">
				<b>${__("To fix")}:</b> ${issues.slice(0, 6).join(" · ")}${issues.length > 6 ? ` · ${__("and {0} more", [issues.length - 6])}` : ""}
			</div>` : "";
		this.$body.find(".fk-tu-dashboard").html(`
			${issue_list}
			<details class="fk-tu-allocation" ${this.allocation_open ?? off ? "open" : ""}>
				<summary>${__("Manifests: tendered vs in the units")}</summary>
				<table>
					<thead><tr><th>${__("Manifest")}</th><th>${__("Project Type")}</th><th class="num">${__("Tendered")}</th>
						<th class="num">${__("In the units")}</th><th class="num">${__("Apartments")}</th><th></th><th></th></tr></thead>
					<tbody>${rows}</tbody>
				</table>
			</details>`);
		this.$body.find(".fk-tu-allocation").on("toggle", (e) => (this.allocation_open = e.currentTarget.open));
	}

	render_counts() {
		this.render_dashboard();
		const n = this.apts.length;
		const target = this.data.tender.number_of_units;
		const mismatch = target && n !== target;
		this.$body.find(".fk-tu-counts").html(
			`<span class="${mismatch ? "text-warning" : ""}">${__("{0} apartments", [n])}${target ? ` / ${target}` : ""}</span>
			${this.types().map((type) => `<span class="fk-tu-type"><i style="background:${this.colour(type)}"></i>${frappe.utils.escape_html(type)}
				<span class="text-muted">${this.apts.filter((a) => a.type === type).length}</span></span>`).join("")}`
		);
	}

	render_messages() {
		const d = this.data;
		const errors = this.save_errors || (this.dirty ? [] : d.errors || []);
		// the counts against the tender are on the dashboard, live
		const warnings = this.dirty ? [] : (d.warnings || []).filter((w) => !(d.count_warnings || []).includes(w));
		const list = (items, cls) => items.length ? `<div class="alert ${cls}"><ul>${items.slice(0, 10).map((e) => `<li>${e}</li>`).join("")}
			${items.length > 10 ? `<li>${__("…and {0} more.", [items.length - 10])}</li>` : ""}</ul></div>` : "";
		const t = d.tender;
		const last_run = t.summary && !this.dirty
			? `<div class="alert ${t.status === "Failed" ? "alert-danger" : "alert-info"}"><b>${__("Last run")}:</b> ${frappe.utils.escape_html(t.summary)}</div>` : "";
		const gone = !this.dirty && d.not_in_table?.length
			? `<div class="alert alert-warning">${__("These projects no longer have a unit here: {0}. Sync keeps them.", [d.not_in_table.map(frappe.utils.escape_html).join(", ")])}</div>` : "";
		this.$body.find(".fk-tu-messages").html(last_run + list(errors, "alert-danger") + list(warnings, "alert-warning") + gone);
	}

	sync_badge(apt) {
		const s = TU_SYNC[apt.sync];
		if (!s || (!this.data.tender.project && apt.sync !== "edited")) return "";
		const title = (apt.changes || []).join(", ");
		return `<span class="indicator-pill ${s.colour} fk-tu-sync" title="${frappe.utils.escape_html(title)}">${s.label}</span>`;
	}

	// ------------------------------------------------------------ grid view

	grid_columns() {
		const cols = [
			{ key: "type", label: __("Apt Type") },
			{ key: "floor", label: __("Floor") },
			{ key: "number", label: __("Apt No") },
			{ key: "name", label: __("Unit Name") },
		];
		for (const pt of this.data.project_types) {
			cols.push({ key: `m:${pt}`, label: __("{0} Manifest", [pt]), pt, kind: "manifest" });
			cols.push({ key: `q:${pt}`, label: __("{0} Qty", [pt]), pt, kind: "qty" });
		}
		return cols;
	}

	cell_value(apt, col) {
		if (col.kind === "manifest") return apt.manifests?.[col.pt]?.manifest || "";
		if (col.kind === "qty") return apt.manifests?.[col.pt]?.manifest ? apt.manifests[col.pt].qty || 1 : "";
		return apt[col.key] || "";
	}

	set_cell(apt, col, value) {
		value = (value ?? "").toString().trim();
		const before = JSON.stringify([apt.type, apt.floor, apt.number, apt.name, apt.manifests]);
		apt.manifests = apt.manifests || {};
		if (col.kind === "manifest") {
			const name = value ? this.find_manifest(col.pt, value) : null;
			if (value && !name) return false;
			if (!name) delete apt.manifests[col.pt];
			else apt.manifests[col.pt] = { manifest: name, qty: apt.manifests[col.pt]?.qty || 1 };
		} else if (col.kind === "qty") {
			const qty = parseInt(value, 10);
			if (apt.manifests[col.pt] && qty > 0) apt.manifests[col.pt].qty = qty;
		} else {
			apt[col.key] = value;
		}
		// moving through a cell with Enter fires change too; only a real change marks the apartment edited
		if (JSON.stringify([apt.type, apt.floor, apt.number, apt.name, apt.manifests]) !== before) this.touch(apt);
		return true;
	}

	render_grid() {
		const keep = this.grid_order?.length === this.apts.length && this.grid_order.every((id) => this.apts.some((a) => a._id === id));
		if (!keep) {
			// back to floor order (and no sorted heading) when apartments come or go
			this.grid_order = this.sorted(this.apts).map((a) => a._id);
			this.grid_sort = null;
		}
		const rows = this.grid_order.map((id) => this.apts.find((a) => a._id === id));
		const cols = this.grid_columns();
		const can_write = this.data.tender.can_write;
		const dis = can_write ? "" : "disabled";
		const cell = (apt, col, r, c) => {
			const value = apt ? this.cell_value(apt, col) : "";
			if (col.kind === "manifest") {
				return `<select class="fk-tu-cell" data-r="${r}" data-c="${c}" ${dis}>
					<option value=""></option>
					${this.manifests_for(col.pt).map((m) => `<option value="${frappe.utils.escape_html(m.name)}" ${m.name === value ? "selected" : ""}>${frappe.utils.escape_html(m.label)}</option>`).join("")}
				</select>`;
			}
			return `<input class="fk-tu-cell ${col.kind === "qty" ? "fk-tu-qty" : ""}" data-r="${r}" data-c="${c}" value="${frappe.utils.escape_html(value)}" ${dis}>`;
		};
		const sort = this.grid_sort || {};
		const arrow = (c) => (sort.c === c ? (sort.desc ? " ↓" : " ↑") : "");
		// the view element is reused, so drop the last render's delegated handlers
		const $view = this.$body.find(".fk-tu-view").off().html(`
			${can_write ? `<div class="fk-tu-hint text-muted small">
				${__("Paste cells from Excel (rows are added as needed). <b>Ctrl+D</b> copies a cell down to the ticked rows below it (or the next row). Tick rows to delete them. Click a heading to sort.")}
			</div>` : ""}
			<div class="fk-tu-grid-wrap">
				<table class="fk-tu-grid">
					<thead><tr>
						<th class="fk-tu-check"><input type="checkbox" data-act="check-all"></th>
						<th class="fk-tu-idx">#</th>
						${cols.map((col, c) => `<th class="fk-tu-sort ${col.kind === "qty" ? "fk-tu-qtycol" : ""}" data-sort="${c}">${frappe.utils.escape_html(col.label)}${arrow(c)}</th>`).join("")}
						<th>${__("Status")}</th>
					</tr></thead>
					<tbody>${rows.map((apt, r) => `
						<tr data-id="${apt._id}" class="${this.selected.has(apt._id) ? "selected" : ""}">
							<td class="fk-tu-check"><input type="checkbox" data-row-check="${apt._id}" ${this.selected.has(apt._id) ? "checked" : ""}></td>
							<td class="fk-tu-idx"><i style="background:${this.colour(apt.type)}"></i>${r + 1}</td>
							${cols.map((col, c) => `<td>${cell(apt, col, r, c)}</td>`).join("")}
							<td class="fk-tu-status">${this.sync_badge(apt)}</td>
						</tr>`).join("")}
					</tbody>
				</table>
				${rows.length ? "" : `<div class="fk-tu-empty">${__("No apartments yet. Add a row, or paste them from Excel.")}</div>`}
			</div>
			${can_write ? `<div class="fk-tu-footer">
				<button class="btn btn-xs btn-danger hidden" data-act="delete-rows"></button>
				<button class="btn btn-xs btn-secondary" data-act="add-row">${__("Add Row")}</button>
			</div>` : ""}`);
		this.bind_grid($view, rows, cols);
	}

	// focus a grid cell after a re-render
	focus_cell(r, c) {
		this.$body.find(`.fk-tu-cell[data-r=${r}][data-c=${c}]`).trigger("focus").trigger("select");
	}

	bind_grid($view, rows, cols) {
		const status = (apt) => $view.find(`tr[data-id=${apt._id}] .fk-tu-status`).html(this.sync_badge(apt));
		$view.on("change", ".fk-tu-cell", (e) => {
			const el = e.currentTarget;
			const r = Number(el.dataset.r), col = cols[el.dataset.c];
			const apt = rows[r];
			if (!this.set_cell(apt, col, el.value)) {
				frappe.show_alert({ message: __("{0} isn't a {1} manifest on this tender.", [el.value, col.pt]), indicator: "red" });
			}
			// keep the row's dependent cells (qty, colour, counts) in step
			$view.find(`.fk-tu-cell[data-r=${r}]`).each((i, x) => $(x).val(this.cell_value(apt, cols[x.dataset.c])));
			$view.find(`tr[data-id=${apt._id}] .fk-tu-idx i`).css("background", this.colour(apt.type));
			status(apt);
			this.render_counts();
		});
		$view.on("keydown", ".fk-tu-cell", (e) => {
			const r = Number(e.currentTarget.dataset.r), c = Number(e.currentTarget.dataset.c);
			if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "d") {
				e.preventDefault();
				$(e.currentTarget).trigger("change");
				return this.fill_down(rows, cols, r, c);
			}
			const move = { Enter: 1, ArrowDown: 1, ArrowUp: -1 }[e.key];
			if (!move || (e.currentTarget.tagName === "SELECT" && e.key !== "Enter")) return;
			e.preventDefault();
			$(e.currentTarget).trigger("change");
			$view.find(`.fk-tu-cell[data-r=${r + (e.shiftKey && e.key === "Enter" ? -1 : move)}][data-c=${c}]`).trigger("focus").trigger("select");
		});
		// the ticked rows go with the footer's Delete (shown once rows are ticked, like a child table),
		// or the Delete key on a tick box / Ctrl+Delete anywhere in the grid
		const delete_ticked = () => {
			const ids = rows.filter((a) => this.selected.has(a._id)).map((a) => a._id);
			if (!ids.length) return;
			frappe.confirm(__("Delete {0} apartment(s)?", [ids.length]), () => {
				this.apts = this.apts.filter((a) => !ids.includes(a._id));
				ids.forEach((id) => this.selected.delete(id));
				this.set_dirty(true);
				this.render();
			});
		};
		const show_delete = () => {
			const n = rows.filter((a) => this.selected.has(a._id)).length;
			$view.find("[data-act=delete-rows]").toggleClass("hidden", !n).text(n > 1 ? __("Delete {0} rows", [n]) : __("Delete"));
			$view.find("[data-act=check-all]").prop("checked", n > 0 && n === rows.length);
		};
		show_delete();
		$view.find("[data-act=delete-rows]").on("click", delete_ticked);
		$view.on("keydown", (e) => {
			if (e.key !== "Delete" || !(e.target.type === "checkbox" || e.ctrlKey || e.metaKey)) return;
			e.preventDefault();
			delete_ticked();
		});
		$view.on("paste", ".fk-tu-cell", (e) => {
			const text = (e.originalEvent.clipboardData || window.clipboardData).getData("text");
			if (!/[\t\n]/.test(text.trim())) return;
			e.preventDefault();
			this.paste(text, Number(e.currentTarget.dataset.r), Number(e.currentTarget.dataset.c), rows, cols);
		});
		// a new, empty row at the bottom, like a child table's Add Row
		$view.find("[data-act=add-row]").on("click", () => {
			const apt = { _id: this.next_id++, type: "", floor: "", number: "", name: "", manifests: {} };
			this.touch(apt);
			this.apts.push(apt);
			this.grid_order.push(apt._id);
			this.render_grid();
			this.render_counts();
			// straight into its first cell
			this.focus_cell(rows.length, 0);
			this.$body.find(".fk-tu-grid-wrap").scrollTop(1e6);
		});
		$view.find("[data-act=check-all]").on("change", (e) => {
			rows.forEach((a) => (e.currentTarget.checked ? this.selected.add(a._id) : this.selected.delete(a._id)));
			this.render_grid();
		});
		$view.on("change", "[data-row-check]", (e) => {
			const id = Number(e.currentTarget.dataset.rowCheck);
			e.currentTarget.checked ? this.selected.add(id) : this.selected.delete(id);
			$(e.currentTarget).closest("tr").toggleClass("selected", e.currentTarget.checked);
			show_delete();
		});
		// a heading sorts by its column; again to reverse
		$view.find("[data-sort]").on("click", (e) => {
			const c = Number(e.currentTarget.dataset.sort), col = cols[c];
			const desc = this.grid_sort?.c === c ? !this.grid_sort.desc : false;
			this.grid_sort = { c, desc };
			const cmp = col.key === "floor" ? compare_floor : natural;
			this.grid_order = [...rows]
				.sort((a, b) => (desc ? -1 : 1) * cmp(String(this.cell_value(a, col)), String(this.cell_value(b, col))) || natural(a.number, b.number))
				.map((a) => a._id);
			this.render_grid();
		});
	}

	// Ctrl+D: copy the cell down to the ticked rows below it, or to the next row (and move there)
	fill_down(rows, cols, r, c) {
		const col = cols[c];
		if (!rows[r]) return;
		if (col.key === "number") return frappe.show_alert({ message: __("Apt No can't be copied down; each apartment needs its own."), indicator: "orange" });
		const value = this.cell_value(rows[r], col);
		const ticked = rows.slice(r + 1).filter((a) => this.selected.has(a._id));
		const targets = ticked.length ? ticked : rows.slice(r + 1, r + 2);
		if (!targets.length) return;
		targets.forEach((a) => this.set_cell(a, col, value));
		this.render_grid();
		this.render_counts();
		this.focus_cell(ticked.length ? r : r + 1, c);
	}

	paste(text, r0, c0, rows, cols) {
		const lines = text.replace(/\r/g, "").replace(/\n$/, "").split("\n").map((l) => l.split("\t"));
		const bad = [];
		lines.forEach((cells, i) => {
			let apt = rows[r0 + i];
			if (!apt) {
				apt = { _id: this.next_id++, number: "", type: "", floor: "", name: "", manifests: {} };
				this.apts.push(apt);
				this.grid_order.push(apt._id);
				rows.push(apt);
			}
			cells.forEach((value, j) => {
				const col = cols[c0 + j];
				if (col && !this.set_cell(apt, col, value)) bad.push(value);
			});
		});
		this.render_grid();
		this.render_counts();
		if (bad.length) frappe.msgprint(__("These manifests weren't recognised and were left empty: {0}", [[...new Set(bad)].map(frappe.utils.escape_html).join(", ")]));
	}

	add_styles() {
		if (document.getElementById("fk-tu-styles")) return;
		$(`<style id="fk-tu-styles">
			.fk-tu { padding: var(--padding-md) 0; }
			.fk-tu-empty { padding: 40px; text-align: center; color: var(--text-muted); }
			.fk-tu-top { display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-start; padding-top: var(--padding-md); }
			.fk-tu-setup { display: contents; }
			.fk-tu-top .control-value { color: var(--text-color); }
			.fk-tu-setting { width: 280px; }
			.fk-tu-setting .form-group { margin-bottom: 8px; }
			.fk-tu-dashboard { margin-bottom: 12px; }
			.fk-tu-issues { background: var(--red-50); color: var(--red-700); border-radius: var(--border-radius-md); padding: 6px 12px; margin-bottom: 8px; font-size: var(--text-sm); }
			.fk-tu-allocation { border: 1px solid var(--border-color); border-radius: var(--border-radius-md); background: var(--card-bg); }
			.fk-tu-allocation summary { cursor: pointer; padding: 8px 12px; font-weight: 600; font-size: var(--text-sm); }
			.fk-tu-allocation table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
			.fk-tu-allocation th { color: var(--text-muted); font-weight: 400; text-align: left; padding: 6px 12px; border-top: 1px solid var(--border-color); }
			.fk-tu-allocation td { padding: 6px 12px; border-top: 1px solid var(--border-color); }
			.fk-tu-allocation .num { text-align: right; font-variant-numeric: tabular-nums; }
			.fk-tu-bar-cell { width: 160px; }
			.fk-tu-bar { height: 6px; border-radius: 3px; background: var(--gray-200); overflow: hidden; }
			.fk-tu-bar i { display: block; height: 100%; background: var(--green-500); }
			.fk-tu-bar.warn i { background: var(--orange-500); }
			.fk-tu-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
			.fk-tu-facts { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
			.fk-tu-counts { display: inline-flex; gap: 12px; flex-wrap: wrap; }
			.fk-tu-type i, .fk-tu-idx i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 4px; vertical-align: middle; }
			.fk-tu-messages .alert { padding: 8px 12px; margin-bottom: 8px; }
			.fk-tu-messages ul { margin: 0; padding-left: 18px; }
			.fk-tu-hint { margin-bottom: 8px; }
			.fk-tu-grid th.fk-tu-sort { cursor: pointer; user-select: none; }
			.fk-tu-grid th.fk-tu-sort:hover { color: var(--text-color); background: var(--fg-hover-color); }
			.fk-tu-footer { margin-top: 8px; display: flex; gap: 6px; }
			.fk-tu-grid-wrap { overflow: auto; max-height: calc(100vh - 260px); border: 1px solid var(--border-color); border-radius: var(--border-radius-md); }
			.fk-tu-grid { border-collapse: collapse; width: 100%; font-size: var(--text-sm); }
			.fk-tu-grid th { position: sticky; top: 0; z-index: 1; background: var(--subtle-fg); padding: 6px 8px; text-align: left; white-space: nowrap;
				border-bottom: 1px solid var(--border-color); font-weight: 600; }
			.fk-tu-grid td { border-bottom: 1px solid var(--border-color); border-right: 1px solid var(--border-color); padding: 0; }
			.fk-tu-grid tr.selected td { background: var(--subtle-accent); }
			.fk-tu-grid .fk-tu-check, .fk-tu-grid .fk-tu-idx { padding: 0 6px; width: 1%; white-space: nowrap; color: var(--text-muted); }
			.fk-tu-cell { display: block; width: 100%; height: 32px; box-sizing: border-box; min-width: 80px; border: 0; border-radius: 0;
				background: transparent; padding: 5px 8px; outline: none; }
			select.fk-tu-cell { min-width: 240px; }
			.fk-tu-grid th.fk-tu-qtycol { width: 90px; }
			.fk-tu-cell.fk-tu-qty { min-width: 70px; text-align: right; }
			.fk-tu-cell:focus { box-shadow: inset 0 0 0 2px var(--primary); background: var(--card-bg); }
			.fk-tu-status { padding: 0 6px !important; white-space: nowrap; }
			.page-container[data-page-route="tender-units"] .container { max-width: none; padding-left: 24px; padding-right: 24px; }
		</style>`).appendTo("head");
	}
}

// ------------------------------------------------------------ plain helpers

function natural(a, b) {
	return (a || "").localeCompare(b || "", undefined, { numeric: true, sensitivity: "base" });
}

// floors compare as numbers when they are numbers ("10" after "9"), otherwise as text; no floor sorts lowest
function compare_floor(a, b) {
	if (!a !== !b) return a ? 1 : -1;
	const na = Number(a), nb = Number(b);
	if (!isNaN(na) && !isNaN(nb)) return na - nb;
	return natural(a, b);
}
