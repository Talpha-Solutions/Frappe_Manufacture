// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

// The Cabinet Vision Browser: /app/cabinet-vision-job/view/tree
// Job → Room → Base / Wall / Tall … → Cabinet → Parts by material / Doors / Drawers / Accessories,
// with the clicked node's details on the right.

const CV_BROWSER = "fitzgerald_kitchens.fitzgerald_kitchens.doctype.cabinet_vision_job.cabinet_vision_browser";
const cv_esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
const cv_num = (v, dp = 0) => (v == null || v === "" ? "" : format_number(v, null, dp));

frappe.treeview_settings["Cabinet Vision Job"] = {
	get_tree_nodes: `${CV_BROWSER}.get_children`,
	filters: [
		{
			fieldname: "job",
			fieldtype: "Link",
			options: "Cabinet Vision Job",
			label: __("Job"),
			// the tree rebuilds itself on change; refresh the panel once it has the new job
			onchange: () =>
				setTimeout(() => {
					const view = frappe.views.trees["Cabinet Vision Job"];
					if (!view) return;
					if (view.args.job) cv_show_detail(view, view.args.job);
					else cv_panel_message(view, __("Pick a job to browse."));
				}, 0),
		},
	],
	title: __("Cabinet Vision Browser"),
	root_label: "Cabinet Vision Job",
	get_tree_root: false,
	show_expand_all: false,
	disable_add_node: true,
	do_not_setup_menu: true,

	get_label(node) {
		if (node.is_root) return `<b>${cv_esc(node.data.job_name || node.label)}</b>`;
		const d = node.data;
		let label = cv_esc(d.title || node.label);
		if (d.by_others) label = `<span class="text-muted">${label}</span>`;
		if (d.badge !== undefined && d.badge !== "") {
			label += ` <span class="cv-badge">${cv_esc(d.badge)}</span>`;
		}
		return label;
	},

	onrender(node) {
		if (!node.is_root || !node.data.value || node.data.value === "Cabinet Vision Job") return;
		frappe.db.get_value("Cabinet Vision Job", node.data.value, "job_name").then((r) => {
			const name = r.message && r.message.job_name;
			if (name) node.$tree_link.find(".tree-label").html(` <b>${cv_esc(name)}</b>`);
		});
	},

	toolbar: [
		{
			label: __("Open Cabinet"),
			condition: (node) => !!node.data.cabinet,
			click: (node) => frappe.set_route("Form", "Cabinet Vision Cabinet", node.data.cabinet),
		},
		{
			label: __("Open Job"),
			condition: (node) => node.is_root && node.data.value !== "Cabinet Vision Job",
			click: (node) => frappe.set_route("Form", "Cabinet Vision Job", node.data.value),
		},
	],

	onload(view) {
		cv_add_styles();
		// the tree view's card is capped at 900px and clips overflow; the tree and panel need the room,
		// and the panel stays in view while the tree scrolls
		view.page.main.addClass("cv-browser-main");
		const $row = $('<div class="row cv-browser"></div>').appendTo(view.page.main);
		view.body = $('<div class="col-lg-5 col-md-6 col-12 cv-browser-tree"></div>').appendTo($row);
		view.$panel = $('<div class="col-lg-7 col-md-6 col-12 cv-browser-panel"></div>').appendTo($row);
		cv_panel_message(view, __("Pick a job to browse."));

		view.page.add_inner_button(__("Open Job"), () => {
			if (view.args.job) frappe.set_route("Form", "Cabinet Vision Job", view.args.job);
		});

		// the job to open: from the route (View in Browser on a job), else the latest imported one
		const from_route = frappe.route_options && frappe.route_options.job;
		if (from_route) delete frappe.route_options.job;
		const pick = from_route
			? Promise.resolve(from_route)
			: frappe.db
					.get_list("Cabinet Vision Job", {
						fields: ["name"],
						filters: { import_status: "Imported" },
						order_by: "imported_on desc",
						limit: 1,
					})
					.then((r) => r[0] && r[0].name);
		pick.then((job) => {
			if (!job) {
				cv_panel_message(view, __("No imported Cabinet Vision jobs yet."));
				view.make_tree();
				return;
			}
			view.page.fields_dict.job.set_input(job);
			view.args.job = job;
			view.root_label = job;
			view.make_tree();
			cv_show_detail(view, job);
		});
	},

	click(node) {
		const view = frappe.views.trees["Cabinet Vision Job"];
		if (!view || !view.args.job) {
			cv_panel_message(view, __("Pick a job to browse."));
			return;
		}
		cv_show_detail(view, node.is_root ? view.args.job : node.data.value);
	},
};

// ------------------------------------------------------------------------------------- panel

function cv_panel_message(view, message) {
	if (view && view.$panel) view.$panel.html(`<div class="cv-empty text-muted">${cv_esc(message)}</div>`);
}

function cv_show_detail(view, value) {
	view.$panel.html(`<div class="cv-empty text-muted">${__("Loading...")}</div>`);
	frappe
		.call({ method: `${CV_BROWSER}.get_node_detail`, args: { job: view.args.job, value } })
		.then((r) => {
			const d = r.message || {};
			const render = {
				job: cv_render_job,
				room: cv_render_room,
				group: cv_render_group,
				cabinet: cv_render_cabinet,
				part_material: cv_render_part_material,
			}[d.kind] || cv_render_row;
			view.$panel.html(`<div class="cv-panel">${render(d)}</div>`);
		});
}

function cv_header(d, links = "") {
	return `
		<div class="cv-head">
			<div>
				<div class="cv-title">${cv_esc(d.title)}${d.by_others ? ` <span class="indicator-pill gray">${__("By Others")}</span>` : ""}</div>
				${d.subtitle ? `<div class="text-muted small">${cv_esc(d.subtitle)}</div>` : ""}
			</div>
			<div>${links}</div>
		</div>`;
}

function cv_cards(cards) {
	if (!cards || !cards.length) return "";
	return `<div class="cv-cards">${cards
		.map((c) => `<div class="cv-card"><div class="cv-card-value">${cv_esc(c.value)}</div><div class="cv-card-label">${cv_esc(c.label)}</div></div>`)
		.join("")}</div>`;
}

function cv_specs(specs) {
	const rows = (specs || []).filter((s) => s.value !== null && s.value !== undefined && s.value !== "");
	if (!rows.length) return "";
	return `<table class="table table-sm cv-specs"><tbody>${rows
		.map((s) => `<tr><td class="text-muted">${cv_esc(s.label)}</td><td>${cv_esc(s.value)}</td></tr>`)
		.join("")}</tbody></table>`;
}

function cv_section(title, body) {
	return body ? `<div class="cv-section-title">${cv_esc(title)}</div>${body}` : "";
}

function cv_link(doctype, name, label) {
	return `<a href="/app/${frappe.router.slug(doctype)}/${encodeURIComponent(name)}">${cv_esc(label || name)}</a>`;
}

function cv_open_button(doctype, name, label) {
	return `<a class="btn btn-default btn-xs" href="/app/${frappe.router.slug(doctype)}/${encodeURIComponent(name)}">${cv_esc(label)}</a>`;
}

function cv_quantity(r) {
	const out = [];
	if (flt(r.area_m2)) out.push(`${cv_num(r.area_m2, 3)} m²`);
	if (flt(r.length_m)) out.push(`${cv_num(r.length_m, 2)} m`);
	if (flt(r.qty)) out.push(`${cv_num(r.qty)} ${__("pcs")}`);
	return out.join(" · ");
}

function cv_takeoff(rows) {
	if (!rows || !rows.length) return "";
	return `<table class="table table-sm cv-table">
		<thead><tr><th>${__("Material")}</th><th>${__("Type")}</th><th class="text-right">${__("Parts")}</th><th class="text-right">${__("Quantity")}</th></tr></thead>
		<tbody>${rows
			.map(
				(r) => `<tr>
					<td>${r.material ? cv_link("Cabinet Vision Material", r.material, r.material_name) : cv_esc(r.material_name)}</td>
					<td class="text-muted">${cv_esc(r.material_type)}</td>
					<td class="text-right">${cv_esc(r.part_count)}</td>
					<td class="text-right">${cv_quantity(r)}</td>
				</tr>`
			)
			.join("")}</tbody></table>`;
}

function cv_cabinet_table(cabinets) {
	if (!cabinets || !cabinets.length) return "";
	return `<table class="table table-sm cv-table">
		<thead><tr><th>${__("Cabinet")}</th><th>${__("W × H × D (mm)")}</th><th class="text-right">${__("Parts")}</th></tr></thead>
		<tbody>${cabinets
			.map(
				(c) => `<tr class="${c.by_others ? "text-muted" : ""}">
					<td>${cv_link("Cabinet Vision Cabinet", c.name, c.cabinet_name)}${c.by_others ? ` <small>(${__("by others")})</small>` : ""}</td>
					<td>${cv_esc(c.size)}</td>
					<td class="text-right">${cv_esc(c.part_count)}</td>
				</tr>`
			)
			.join("")}</tbody></table>`;
}

function cv_render_job(d) {
	const moldings = (d.moldings || []).length
		? `<table class="table table-sm cv-table"><thead><tr><th>${__("Molding")}</th><th class="text-right">${__("Length (m)")}</th><th class="text-right">${__("Miters")}</th></tr></thead><tbody>${d.moldings
				.map((m) => `<tr><td>${cv_esc(m.style)}</td><td class="text-right">${cv_num(m.length_m, 3)}</td><td class="text-right">${cv_esc(m.miters)}</td></tr>`)
				.join("")}</tbody></table>`
		: "";
	return (
		cv_header(d, cv_open_button("Cabinet Vision Job", d.name, __("Open Job"))) +
		cv_cards(d.cards) +
		cv_section(__("Cabinets"), cv_cards(d.groups)) +
		cv_section(__("Material take-off"), cv_takeoff(d.takeoff)) +
		cv_section(__("Moldings"), moldings)
	);
}

function cv_render_room(d) {
	return cv_header(d) + cv_section(__("Room specification"), cv_specs(d.specs)) + cv_section(__("Cabinets"), cv_cabinet_table(d.cabinets));
}

function cv_render_group(d) {
	return cv_header(d) + cv_cabinet_table(d.cabinets);
}

function cv_render_cabinet(d) {
	const drawers = (d.drawers || []).length
		? `<table class="table table-sm cv-table"><tbody>${d.drawers
				.map((r) => `<tr><td>${cv_esc(__(r.kind))}</td><td>${cv_esc(r.name)}</td><td class="text-right">${cv_esc(r.size)} mm</td></tr>`)
				.join("")}</tbody></table>`
		: "";
	const accessories = (d.accessories || []).length
		? `<table class="table table-sm cv-table"><tbody>${d.accessories
				.map((a) => `<tr><td>${cv_esc(a.name)}</td><td class="text-right">× ${cv_num(a.qty)}</td></tr>`)
				.join("")}</tbody></table>`
		: "";
	return (
		cv_header(d, cv_open_button("Cabinet Vision Cabinet", d.name, __("Open Cabinet"))) +
		cv_cards(d.cards) +
		cv_specs(d.specs) +
		cv_section(__("Material take-off"), cv_takeoff(d.takeoff)) +
		cv_section(__("Drawers & roll-outs"), drawers) +
		cv_section(__("Accessories"), accessories)
	);
}

function cv_render_part_material(d) {
	const parts = `<table class="table table-sm cv-table">
		<thead><tr><th>${__("Part")}</th><th class="text-right">${__("W × L (mm)")}</th><th class="text-right">${__("Area (m²)")}</th><th>${__("Edge Band")}</th></tr></thead>
		<tbody>${(d.parts || [])
			.map(
				(p) => `<tr>
					<td>${cv_esc(p.description)}</td>
					<td class="text-right">${p.is_hardware ? `<span class="text-muted">${__("hardware")}</span>` : `${cv_num(p.w, 1)} × ${cv_num(p.l, 1)}`}</td>
					<td class="text-right">${p.is_hardware ? "" : cv_num(p.area_m2, 4)}</td>
					<td>${cv_esc(p.edge_band)}</td>
				</tr>`
			)
			.join("")}</tbody></table>`;
	const links = d.material ? cv_open_button("Cabinet Vision Material", d.material, __("Open Material")) : "";
	const item = d.material
		? `<div class="small text-muted cv-item">${__("ERPNext Item")}: ${d.item ? cv_link("Item", d.item) : __("not mapped yet")}</div>`
		: "";
	return cv_header(d, links) + item + cv_takeoff(d.takeoff) + parts;
}

function cv_render_row(d) {
	const links = d.cabinet ? cv_open_button("Cabinet Vision Cabinet", d.cabinet, __("Open Cabinet")) : "";
	return cv_header(d, links) + cv_specs(d.specs);
}

// ------------------------------------------------------------------------------------- styles

function cv_add_styles() {
	if (document.getElementById("cv-browser-styles")) return;
	$(`<style id="cv-browser-styles">
		.layout-main-section.cv-browser-main { max-width: none !important; overflow: visible !important; }
		.cv-browser { margin: 0; align-items: flex-start; }
		.cv-browser-tree { border-right: 1px solid var(--border-color); padding: var(--padding-md); min-height: 60vh; overflow-x: auto; }
		.cv-browser-tree .tree-label { white-space: nowrap; }
		.cv-browser-panel { padding: var(--padding-md) var(--padding-lg); position: sticky; top: var(--navbar-height, 60px);
			max-height: calc(100vh - var(--navbar-height, 60px) - 16px); overflow-y: auto; }
		.cv-table td.text-right, .cv-table th.text-right { white-space: nowrap; }
		.cv-badge { font-size: var(--text-xs); color: var(--text-muted); background: var(--subtle-fg); border-radius: 8px; padding: 1px 6px; margin-left: 4px; }
		.cv-empty { padding: var(--padding-xl) 0; text-align: center; }
		.cv-head { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--padding-md); margin-bottom: var(--padding-md); }
		.cv-title { font-size: var(--text-xl); font-weight: 600; color: var(--heading-color); }
		.cv-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: var(--padding-sm); margin-bottom: var(--padding-md); }
		.cv-card { border: 1px solid var(--border-color); border-radius: var(--border-radius-md); padding: var(--padding-sm) var(--padding-md); }
		.cv-card-value { font-size: var(--text-lg); font-weight: 600; color: var(--heading-color); }
		.cv-card-label { font-size: var(--text-xs); color: var(--text-muted); }
		.cv-section-title { font-weight: 600; color: var(--heading-color); margin: var(--padding-md) 0 var(--padding-xs); }
		.cv-table td, .cv-table th, .cv-specs td { font-size: var(--text-sm); }
		.cv-specs td:first-child { width: 40%; }
		.cv-item { margin-bottom: var(--padding-sm); }
		@media (max-width: 767px) {
			.cv-browser-tree { border-right: 0; border-bottom: 1px solid var(--border-color); min-height: 0; }
			.cv-browser-panel { position: static; max-height: none; }
		}
	</style>`).appendTo("head");
}
