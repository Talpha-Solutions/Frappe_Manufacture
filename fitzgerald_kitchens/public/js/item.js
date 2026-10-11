// Item Specs table on the Item form's Pricing tab (mirrors ERPNext's Item Prices table).

const ITEM_SPEC_METHOD =
	"fitzgerald_kitchens.fitzgerald_kitchens.doctype.item_spec.item_spec.get_item_specs";

frappe.ui.form.on("Item", {
	refresh(frm) {
		render_item_specs(frm);
	},
});

function render_item_specs(frm) {
	const field = frm.fields_dict.custom_item_specs_html;
	if (!field || frm.doc.__islocal) return;

	if (!frappe.model.can_read("Item Spec")) {
		frm.toggle_display(["custom_item_specs_section", "custom_item_specs_html"], false);
		return;
	}

	const requested_item = frm.doc.name;
	const container = field.$wrapper;
	container.html(
		`<div class="text-muted text-center" style="padding: 20px;">${__("Loading...")}</div>`
	);

	frappe.call({
		method: ITEM_SPEC_METHOD,
		args: { item_code: requested_item },
		callback(r) {
			if (requested_item !== frm.doc.name || !r.message) return;

			const { specs, has_more } = r.message;
			container.html(item_specs_html(specs, has_more, requested_item));

			container.find(".add-spec-btn").on("click", () => add_item_spec(frm));
			container.find(".spec-row").on("click", function (e) {
				if ($(e.target).is("a")) return;
				frappe.set_route("Form", "Item Spec", $(this).data("name"));
			});
		},
	});
}

function item_specs_html(specs, has_more, item_code) {
	const esc = frappe.utils.escape_html;
	const add_btn_class = specs.length ? "btn-xs" : "btn-sm";
	const add_btn = frappe.model.can_create("Item Spec")
		? `<button class="btn ${add_btn_class} btn-default add-spec-btn">${__("+ Add Spec")}</button>`
		: "";

	const style = `
		<style>
			.item-spec-table { width: 100%; border-collapse: collapse; font-size: var(--text-md); color: var(--text-color); }
			.item-spec-table thead tr { background: var(--subtle-fg); }
			.item-spec-table th { padding: 8px 10px; font-weight: 400; color: var(--text-muted); border-bottom: 1px solid var(--border-color); white-space: nowrap; }
			.item-spec-table td { padding: 9px 10px; border-bottom: 1px solid var(--border-color); vertical-align: top; }
			.item-spec-table tbody tr:last-child td { border-bottom: none; }
			.item-spec-table tbody tr.spec-row { cursor: pointer; }
			.item-spec-table tbody tr.spec-row:hover { background: var(--fg-hover-color); }
			.item-spec-table .col-no { width: 42px; text-align: center; color: var(--text-muted); font-size: var(--text-sm); }
			.item-spec-table .col-list { width: 22%; }
			.item-spec-table .col-ref { width: 16%; color: var(--text-muted); }
			.item-spec-table .spec-text { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; white-space: pre-line; }
			.item-specs-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 10px; margin-bottom: 16px; }
		</style>
	`;
	const intro = `
		<div style="margin-bottom: 12px;">
			<div class="text-extra-muted" style="font-size: var(--text-sm);">${__(
				"Specifications recorded for this item across spec lists."
			)}</div>
		</div>
	`;

	if (!specs.length) {
		return `${style}${intro}
			<div style="text-align: center; padding: 40px 20px; color: var(--text-muted); border: 1px dashed var(--border-color); border-radius: var(--border-radius-md); margin-bottom: 14px;">
				<p style="margin-bottom: 12px;">${__("No item specs found.")}</p>
				${add_btn}
			</div>`;
	}

	const rows = specs
		.map(
			(s, i) => `
			<tr class="spec-row" data-name="${esc(s.name)}" title="${esc(s.specification || "")}">
				<td class="col-no">${i + 1}</td>
				<td class="col-list">
					${esc(s.spec_list)}
					${s.enabled ? "" : `<span class="indicator-pill gray" style="margin-left: 6px;">${__("Disabled")}</span>`}
				</td>
				<td class="col-ref">${esc(s.spec_reference || "")}</td>
				<td><div class="spec-text">${esc(s.specification || "")}</div></td>
			</tr>`
		)
		.join("");

	const view_all = has_more
		? `<a href="/app/item-spec?item_code=${encodeURIComponent(item_code)}" class="btn btn-xs btn-default">${__(
				"View All Specs"
		  )}</a>`
		: "";

	return `${style}${intro}
		<div style="border: 1px solid var(--border-color); border-radius: var(--border-radius-md); overflow: hidden; margin-bottom: 16px;">
			<table class="item-spec-table">
				<thead>
					<tr>
						<th class="col-no">${__("No.")}</th>
						<th class="col-list">${__("Spec List")}</th>
						<th class="col-ref">${__("Reference")}</th>
						<th>${__("Specification")}</th>
					</tr>
				</thead>
				<tbody>${rows}</tbody>
			</table>
		</div>
		<div class="item-specs-footer">
			<div>${view_all}</div>
			${add_btn}
		</div>`;
}

function add_item_spec(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Spec for {0}", [frm.doc.item_name || frm.doc.name]),
		size: "large",
		fields: [
			{
				fieldname: "spec_list",
				fieldtype: "Link",
				label: __("Spec List"),
				options: "Spec List",
				reqd: 1,
				get_query: () => ({ filters: { enabled: 1 } }),
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "spec_reference",
				fieldtype: "Data",
				label: __("Spec Reference"),
				description: __("Clause in the source specification, e.g. N17 410"),
			},
			{ fieldtype: "Section Break" },
			{ fieldname: "specification", fieldtype: "Text", label: __("Specification"), reqd: 1 },
			{ fieldname: "note", fieldtype: "Small Text", label: __("Note") },
		],
		primary_action_label: __("Save"),
		primary_action(values) {
			dialog.disable_primary_action();
			frappe.db
				.insert({ doctype: "Item Spec", item_code: frm.doc.name, ...values })
				.then(() => {
					dialog.hide();
					frappe.show_alert({ message: __("Spec added"), indicator: "green" });
					render_item_specs(frm);
				})
				.catch(() => dialog.enable_primary_action());
		},
	});
	dialog.show();
}
