// Tender Units: a full-width spreadsheet editor for a Won tender's apartments, without the desk sidebar.
// Save writes them to the tender's Units table (a row per apartment per manifest).

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
		this.tender_field = this.page.add_field({
			fieldtype: "Link",
			fieldname: "tender",
			options: "Tender",
			label: __("Tender"),
			get_query: () => ({ filters: { status: "Won" } }),
			change: () => {
				const value = this.tender_field.get_value();
				if (value && value !== this.data?.tender.name) this.set_tender(value);
			},
		});
		this.page.set_primary_action(__("Save"), () => this.save(), "save");
		this.page.add_inner_button(__("Open Tender"), () => this.data && frappe.set_route("Form", "Tender", this.data.tender.name));
		this.page.add_menu_item(__("Reload"), () => this.confirm_discard(() => this.load()));
		this.page.add_menu_item(__("Download Workbook"), () => {
			if (this.data) open_url_post(`/api/method/${TU_METHOD}.download_unit_workbook`, { tender: this.data.tender.name });
		});
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
			args: { tender: this.data.tender.name, apartments: JSON.stringify(this.payload()) },
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
		const go = () => frappe.confirm(
			syncing
				? __("Update the projects to match these apartments, and create projects for new ones? Projects for apartments no longer here are kept.")
				: __("Create the site, apartment types and apartment projects from these apartments?"),
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
			this.$body.html(`<div class="fk-tu-empty">
				<p>${__("Pick a Won tender above to set up its apartments.")}</p></div>`);
			return;
		}
		const t = this.data.tender;
		this.$body.html(`
			<div class="fk-tu-head">
				<div class="fk-tu-facts">
					<span><b>${frappe.utils.escape_html(t.site_name || "")}</b></span>
					<span class="text-muted">${frappe.utils.escape_html(t.party || "")}${t.party_type === "Lead" ? ` (${__("Lead")})` : ""}</span>
					<span class="fk-tu-counts"></span>
				</div>
			</div>
			<div class="fk-tu-messages"></div>
			<div class="fk-tu-view"></div>`);
		if (!this.data.manifests.length) {
			this.$body.find(".fk-tu-view").html(`<div class="fk-tu-empty">${__("This tender has no manifests yet.")}</div>`);
			return;
		}
		this.render_messages();
		this.render_counts();
		this.render_grid();
	}

	render_counts() {
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
		const warnings = this.dirty ? [] : d.warnings || [];
		const list = (items, cls) => items.length ? `<div class="alert ${cls}"><ul>${items.slice(0, 10).map((e) => `<li>${e}</li>`).join("")}
			${items.length > 10 ? `<li>${__("…and {0} more.", [items.length - 10])}</li>` : ""}</ul></div>` : "";
		const gone = !this.dirty && d.not_in_table?.length
			? `<div class="alert alert-warning">${__("Projects exist for apartments that aren't here any more: {0}. Sync keeps them.", [d.not_in_table.map(frappe.utils.escape_html).join(", ")])}</div>` : "";
		this.$body.find(".fk-tu-messages").html(list(errors, "alert-danger") + list(warnings, "alert-warning") + gone);
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
		this.grid_order = this.grid_order?.length === this.apts.length && this.grid_order.every((id) => this.apts.some((a) => a._id === id))
			? this.grid_order : this.sorted(this.apts).map((a) => a._id);
		const rows = this.grid_order.map((id) => this.apts.find((a) => a._id === id));
		const cols = this.grid_columns();
		const can_write = this.data.tender.can_write;
		const dis = can_write ? "" : "disabled";
		const cell = (apt, col, r, c) => {
			const value = this.cell_value(apt, col);
			if (col.kind === "manifest") {
				return `<select class="fk-tu-cell" data-r="${r}" data-c="${c}" ${dis}>
					<option value=""></option>
					${this.manifests_for(col.pt).map((m) => `<option value="${frappe.utils.escape_html(m.name)}" ${m.name === value ? "selected" : ""}>${frappe.utils.escape_html(m.label)}</option>`).join("")}
				</select>`;
			}
			return `<input class="fk-tu-cell ${col.kind === "qty" ? "fk-tu-qty" : ""}" data-r="${r}" data-c="${c}" value="${frappe.utils.escape_html(value)}" ${dis}>`;
		};
		// the view element is reused, so drop the last render's delegated handlers
		const $view = this.$body.find(".fk-tu-view").off().html(`
			${can_write ? `<div class="fk-tu-tools">
				<button class="btn btn-xs btn-default" data-act="add-apartments">${__("Add Apartments")}</button>
				<button class="btn btn-xs btn-default" data-act="add-row">${__("Add Row")}</button>
				<button class="btn btn-xs btn-default" data-act="fill-down">${__("Fill Down")}</button>
				<button class="btn btn-xs btn-default" data-act="delete-rows">${__("Delete Rows")}</button>
				<button class="btn btn-xs btn-default" data-act="sort">${__("Sort by Floor")}</button>
				<span class="text-muted small">${__("Paste cells from Excel; Fill Down copies the cell you're in to the ticked rows below it; Enter and arrows move between rows.")}</span>
			</div>` : ""}
			<div class="fk-tu-grid-wrap">
				<table class="fk-tu-grid">
					<thead><tr>
						<th class="fk-tu-check"><input type="checkbox" data-act="check-all"></th>
						<th class="fk-tu-idx">#</th>
						${cols.map((c) => `<th>${frappe.utils.escape_html(c.label)}</th>`).join("")}
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
				${rows.length ? "" : `<div class="fk-tu-empty">${__("No apartments yet. Use Add Apartments, or paste from Excel into the first cell.")}</div>`}
			</div>`);
		this.bind_grid($view, rows, cols);
	}

	bind_grid($view, rows, cols) {
		const status = (apt) => $view.find(`tr[data-id=${apt._id}] .fk-tu-status`).html(this.sync_badge(apt));
		$view.on("change", ".fk-tu-cell", (e) => {
			const el = e.currentTarget;
			const apt = rows[el.dataset.r], col = cols[el.dataset.c];
			if (!this.set_cell(apt, col, el.value)) {
				frappe.show_alert({ message: __("{0} isn't a {1} manifest on this tender.", [el.value, col.pt]), indicator: "red" });
			}
			// keep the row's dependent cells (qty, colour, counts) in step
			$view.find(`.fk-tu-cell[data-r=${el.dataset.r}]`).each((i, x) => $(x).val(this.cell_value(apt, cols[x.dataset.c])));
			$view.find(`tr[data-id=${apt._id}] .fk-tu-idx i`).css("background", this.colour(apt.type));
			status(apt);
			this.render_counts();
		});
		$view.on("focus", ".fk-tu-cell", (e) => (this.grid_focus = { r: Number(e.currentTarget.dataset.r), c: Number(e.currentTarget.dataset.c) }));
		$view.on("keydown", ".fk-tu-cell", (e) => {
			const r = Number(e.currentTarget.dataset.r), c = Number(e.currentTarget.dataset.c);
			const move = { Enter: 1, ArrowDown: 1, ArrowUp: -1 }[e.key];
			if (!move || (e.currentTarget.tagName === "SELECT" && e.key !== "Enter")) return;
			e.preventDefault();
			$(e.currentTarget).trigger("change");
			$view.find(`.fk-tu-cell[data-r=${r + (e.shiftKey && e.key === "Enter" ? -1 : move)}][data-c=${c}]`).trigger("focus").trigger("select");
		});
		$view.on("paste", ".fk-tu-cell", (e) => {
			const text = (e.originalEvent.clipboardData || window.clipboardData).getData("text");
			if (!/[\t\n]/.test(text.trim())) return;
			e.preventDefault();
			this.paste(text, Number(e.currentTarget.dataset.r), Number(e.currentTarget.dataset.c), rows, cols);
		});
		$view.find("[data-act=check-all]").on("change", (e) => {
			rows.forEach((a) => (e.currentTarget.checked ? this.selected.add(a._id) : this.selected.delete(a._id)));
			this.render_grid();
		});
		$view.on("change", "[data-row-check]", (e) => {
			const id = Number(e.currentTarget.dataset.rowCheck);
			e.currentTarget.checked ? this.selected.add(id) : this.selected.delete(id);
			$(e.currentTarget).closest("tr").toggleClass("selected", e.currentTarget.checked);
		});
		$view.find("[data-act=add-apartments]").on("click", () => this.add_apartments_dialog());
		$view.find("[data-act=add-row]").on("click", () => {
			const last = rows[rows.length - 1];
			const apt = { _id: this.next_id++, number: last ? shift_number(last.number, 1) : "", type: last?.type || "",
				floor: last?.floor || "", name: "", manifests: last ? structuredClone(last.manifests || {}) : {} };
			if (this.apts.some((a) => a.number && a.number.toUpperCase() === apt.number.toUpperCase())) apt.number = "";
			apt.name = apt.number;
			this.touch(apt);
			this.apts.push(apt);
			this.grid_order.push(apt._id);
			this.render_grid();
			this.render_counts();
			this.$body.find(`.fk-tu-cell[data-r=${rows.length}][data-c=2]`).trigger("focus").trigger("select");
		});
		$view.find("[data-act=fill-down]").on("click", () => {
			const f = this.grid_focus;
			if (!f || !rows[f.r]) return frappe.msgprint(__("Click into the cell to copy first, then tick the rows to fill."));
			const col = cols[f.c];
			if (col.key === "number") return frappe.msgprint(__("Apt No can't be filled down; each apartment needs its own."));
			const value = this.cell_value(rows[f.r], col);
			const targets = rows.slice(f.r + 1).filter((a) => this.selected.has(a._id));
			if (!targets.length) return frappe.msgprint(__("Tick the rows below to fill."));
			targets.forEach((a) => this.set_cell(a, col, value));
			this.render_grid();
			this.render_counts();
		});
		$view.find("[data-act=delete-rows]").on("click", () => {
			const ids = rows.filter((a) => this.selected.has(a._id)).map((a) => a._id);
			if (!ids.length) return frappe.msgprint(__("Tick the rows to delete."));
			frappe.confirm(__("Delete {0} apartment(s)?", [ids.length]), () => {
				this.apts = this.apts.filter((a) => !ids.includes(a._id));
				ids.forEach((id) => this.selected.delete(id));
				this.set_dirty(true);
				this.render();
			});
		});
		$view.find("[data-act=sort]").on("click", () => {
			this.grid_order = null;
			this.render_grid();
		});
	}

	add_apartments_dialog() {
		const fields = [
			{ fieldtype: "Data", fieldname: "floor", label: __("Floor"), reqd: 1, description: __("e.g. 1, 2, Ground") },
			{ fieldtype: "Data", fieldname: "numbers", label: __("Apt Nos"), reqd: 1, description: __("Ranges and lists, e.g. 101-108, 110") },
			{ fieldtype: "Data", fieldname: "type", label: __("Apt Type"), reqd: 1, description: this.types().length ? __("Existing: {0}", [this.types().join(", ")]) : "" },
			{ fieldtype: "Check", fieldname: "name_as_number", label: __("Unit Name same as Apt No"), default: 1 },
			{ fieldtype: "Section Break", label: __("Manifests") },
		];
		for (const pt of this.data.project_types) {
			const options = this.manifests_for(pt);
			fields.push(
				{ fieldtype: "Select", fieldname: `m_${scrub(pt)}`, label: pt, reqd: pt === "Kitchen" ? 1 : 0,
					options: [{ value: "", label: "" }, ...options.map((m) => ({ value: m.name, label: m.label }))],
					default: options.length === 1 && pt === "Kitchen" ? options[0].name : "" },
				{ fieldtype: "Int", fieldname: `q_${scrub(pt)}`, label: __("{0} Qty", [pt]), default: 1 },
				{ fieldtype: "Column Break" },
			);
		}
		const d = new frappe.ui.Dialog({
			title: __("Add Apartments"),
			fields,
			primary_action_label: __("Add"),
			primary_action: (v) => {
				const numbers = expand_numbers(v.numbers);
				const taken = new Set(this.apts.map((a) => (a.number || "").toUpperCase()));
				const clashes = numbers.filter((n) => taken.has(n.toUpperCase()));
				if (clashes.length) return frappe.msgprint(__("Already used: {0}", [clashes.join(", ")]));
				const manifests = {};
				for (const pt of this.data.project_types) {
					if (v[`m_${scrub(pt)}`]) manifests[pt] = { manifest: v[`m_${scrub(pt)}`], qty: Math.max(1, v[`q_${scrub(pt)}`] || 1) };
				}
				this.selected.clear();
				for (const number of numbers) {
					const apt = { _id: this.next_id++, number, type: v.type.trim(), floor: v.floor.trim(),
						name: v.name_as_number ? number : "", manifests: structuredClone(manifests) };
					this.touch(apt);
					this.apts.push(apt);
					this.selected.add(apt._id);
				}
				d.hide();
				this.render();
			},
		});
		d.show();
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
			.fk-tu-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
			.fk-tu-facts { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
			.fk-tu-counts { display: inline-flex; gap: 12px; flex-wrap: wrap; }
			.fk-tu-type i, .fk-tu-idx i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 4px; vertical-align: middle; }
			.fk-tu-messages .alert { padding: 8px 12px; margin-bottom: 8px; }
			.fk-tu-messages ul { margin: 0; padding-left: 18px; }
			.fk-tu-tools { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; margin-bottom: 10px; }
			.fk-tu-grid-wrap { overflow: auto; max-height: calc(100vh - 260px); border: 1px solid var(--border-color); border-radius: var(--border-radius-md); }
			.fk-tu-grid { border-collapse: collapse; width: 100%; font-size: var(--text-sm); }
			.fk-tu-grid th { position: sticky; top: 0; z-index: 1; background: var(--subtle-fg); padding: 6px 8px; text-align: left; white-space: nowrap;
				border-bottom: 1px solid var(--border-color); font-weight: 600; }
			.fk-tu-grid td { border-bottom: 1px solid var(--border-color); border-right: 1px solid var(--border-color); padding: 0; }
			.fk-tu-grid tr.selected td { background: var(--subtle-accent); }
			.fk-tu-grid .fk-tu-check, .fk-tu-grid .fk-tu-idx { padding: 0 6px; width: 1%; white-space: nowrap; color: var(--text-muted); }
			.fk-tu-cell { width: 100%; min-width: 80px; border: 0; background: transparent; padding: 5px 8px; outline: none; }
			select.fk-tu-cell { min-width: 180px; }
			.fk-tu-cell.fk-tu-qty { min-width: 50px; width: 60px; text-align: right; }
			.fk-tu-cell:focus { box-shadow: inset 0 0 0 2px var(--primary); background: var(--card-bg); }
			.fk-tu-status { padding: 0 6px !important; white-space: nowrap; }
			.page-container[data-page-route="tender-units"] .container { max-width: none; padding-left: 24px; padding-right: 24px; }
		</style>`).appendTo("head");
	}
}

// ------------------------------------------------------------ plain helpers

function scrub(text) {
	return (text || "").toLowerCase().replace(/[^a-z0-9]+/g, "_");
}

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

// "101-104, 110" → 101, 102, 103, 104, 110 (same as the tender form's Add Units)
function expand_numbers(text) {
	const out = [];
	for (const part of (text || "").split(",").map((p) => p.trim()).filter(Boolean)) {
		const range = part.match(/^(\D*)(\d+)\s*-\s*\1?(\d+)$/);
		if (!range) {
			out.push(part);
			continue;
		}
		const [, prefix, from, to] = range;
		for (let n = parseInt(from, 10); n <= parseInt(to, 10) && out.length < 5000; n++) {
			out.push(prefix + String(n).padStart(from.length, "0"));
		}
	}
	return [...new Set(out)];
}

// add to the trailing number of an Apt No, keeping its prefix and padding: "A-101" + 100 → "A-201"
function shift_number(number, offset) {
	const m = (number || "").match(/^(.*?)(\d+)$/);
	if (!m || !offset) return number || "";
	return m[1] + String(parseInt(m[2], 10) + offset).padStart(m[2].length, "0");
}
