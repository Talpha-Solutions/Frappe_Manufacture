// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

const MOP_METHOD = "fitzgerald_kitchens.fitzgerald_kitchens.report.material_order_plan.material_order_plan";
const MOP_STATUS_COLOURS = {
	Overdue: "red",
	"Order Now": "orange",
	"Order Soon": "yellow",
	Later: "blue",
	Covered: "green",
	"Choose Item": "purple",
	"No BOM": "gray",
	"No Date": "gray",
	"Not Stocked": "gray",
};
const MOP_STATUS_HELP = {
	Overdue: __("Should already have been ordered to arrive in time"),
	"Order Now": __("Order today to arrive in time"),
	"Order Soon": __("Order within the window"),
	Later: __("Not needed yet"),
	Covered: __("Stock, open orders and requests cover it"),
	"Choose Item": __("A placeholder: choose the real item (finish / spec) by this date so it can be ordered in time"),
	"No BOM": __("Manufactured item without an active BOM, so its materials can't be worked out"),
	"No Date": __("Some units have no delivery date: set them on the plan's Units, or use Delivery Date (if not set)"),
	"Not Stocked": __("Not a stock item"),
};

frappe.query_reports["Material Order Plan"] = {
	filters: [
		{
			fieldname: "pre_production_plan",
			label: __("Pre Production Plans"),
			fieldtype: "MultiSelectList",
			get_data: (txt) => frappe.db.get_link_options("Pre Production Plan", txt),
			description: __("Leave blank for every plan (except Lost or Cancelled)"),
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			description: __("Stock counted from this warehouse (and those under it); all of the company's if blank"),
		},
		{ fieldname: "as_on", label: __("As On"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{
			fieldname: "default_delivery_date",
			label: __("Delivery Date (if not set)"),
			fieldtype: "Date",
			description: __("For units with no delivery date, e.g. a plan with no Units table yet"),
		},
		{
			fieldname: "window_weeks",
			label: __("Order Soon Window (weeks)"),
			fieldtype: "Int",
			default: 4,
		},
		{
			fieldname: "manufacturing_days",
			label: __("Manufactured: Days Before Delivery"),
			fieldtype: "Int",
			default: 14,
			description: __("Materials for factory-made items are needed this many days before the unit's delivery"),
		},
		{
			fieldname: "bought_in_days",
			label: __("Bought-in: Days Before Delivery"),
			fieldtype: "Int",
			default: 0,
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "MultiSelectList",
			description: __("Leave blank for every status"),
			get_data: (txt) =>
				Object.keys(MOP_STATUS_COLOURS)
					.filter((s) => !txt || __(s).toLowerCase().includes(txt.toLowerCase()))
					.map((s) => ({ value: s, description: MOP_STATUS_HELP[s] })),
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data?.status) {
			const colour = MOP_STATUS_COLOURS[data.status] || "gray";
			return `<span class="indicator-pill ${colour}" title="${frappe.utils.escape_html(MOP_STATUS_HELP[data.status] || "")}">${frappe.utils.escape_html(__(data.status))}</span>`;
		}
		if (column.fieldname === "to_order" && data && flt(data.to_order) > 0) {
			return `<b>${value}</b>`;
		}
		return value;
	},

	// tick boxes, so only some rows can go on a Material Request
	get_datatable_options(options) {
		return Object.assign(options, { checkboxColumn: true });
	},

	onload(report) {
		report.page.add_inner_button(__("Create Material Request"), () => create_material_request(report));
	},
};

// a draft Purchase Material Request for the rows to order now / soon (or the ticked ones)
function create_material_request(report) {
	const data = report.data || [];
	const checked = report.datatable?.rowmanager?.getCheckedRows?.().map((i) => data[i]).filter(Boolean) || [];
	const orderable = (r) => r && flt(r.to_order) > 0 && ["Overdue", "Order Now", "Order Soon"].includes(r.status);
	const rows = (checked.length ? checked : data).filter(orderable);
	if (!rows.length) {
		frappe.msgprint(__("Nothing to order: no Overdue, Order Now or Order Soon rows with a quantity to order."));
		return;
	}
	frappe.confirm(
		__("Create a draft Purchase Material Request for {0} item(s)?", [rows.length]) +
			(checked.length ? "" : `<br><small class="text-muted">${__("Tick rows first to order only some of them.")}</small>`),
		() =>
			frappe
				.call({
					method: `${MOP_METHOD}.create_material_request`,
					args: {
						filters: report.get_filter_values(),
						items: rows.map((r) => ({ item_code: r.item_code, qty: r.to_order, schedule_date: r.first_need })),
					},
					freeze: true,
				})
				.then((r) => r.message && frappe.set_route("Form", "Material Request", r.message))
	);
}
