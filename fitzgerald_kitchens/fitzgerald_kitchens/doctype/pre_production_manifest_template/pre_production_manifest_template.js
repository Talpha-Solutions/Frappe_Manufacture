const METHOD_BASE =
	"fitzgerald_kitchens.fitzgerald_kitchens.doctype.pre_production_manifest_template.pre_production_manifest_template";

frappe.ui.form.on("Pre Production Manifest Template", {
	setup(frm) {
		frm.set_query("party_type", () => ({ filters: { name: ["in", ["Lead", "Customer"]] } }));
	},
	async refresh(frm) {
		frm.__fk_party_type = frm.doc.party_type;
		add_party_template_button(frm);
		add_get_from_template_button(frm);
		set_rows_table_full_width(frm);
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
	const templates = await frappe.db.get_list("Pre Production Manifest Template", {
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
			const source = await frappe.db.get_doc("Pre Production Manifest Template", template);
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
		const source = await frappe.db.get_doc("Pre Production Manifest Template", template);
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
	if (frm.is_new() || !frm.doc.is_template || !frappe.model.can_create("Pre Production Manifest Template")) return;
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
					{ fieldtype: "HTML", options: `<p class="text-muted small">${__("Copies this template's rows. Edit the copy for them; this template isn't changed.")}</p>` },
				],
				primary_action_label: __("Create"),
				primary_action({ party_type, party_name, template_name }) {
					frappe
						.xcall(`${METHOD_BASE}.create_party_template`, { template: frm.doc.name, party_type, party_name, template_name })
						.then((name) => {
							dialog.hide();
							frappe.show_alert({ message: __("Created {0}", [name]), indicator: "green" });
							frappe.set_route("Form", "Pre Production Manifest Template", name);
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

function escape_html(value) {
	return frappe.utils.escape_html(value || "");
}
