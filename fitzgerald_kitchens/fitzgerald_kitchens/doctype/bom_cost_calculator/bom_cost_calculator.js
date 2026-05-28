// Copyright (c) 2024, Talpha Solutions
frappe.provide("fitzgerald_kitchens.bom");

fitzgerald_kitchens.bom.populate_dialog_items = function (dialog, items) {
	const grid = dialog.fields_dict.items?.grid;
	if (!grid || !items?.length) {
		return;
	}

	grid.remove_all();
	grid.df.data = items.map((item, index) => ({
		idx: index + 1,
		__islocal: true,
		item_code: item.item_code,
		item_name: item.item_name || "",
		qty: flt(item.qty) || 1,
	}));

	items.forEach((item) => {
		if (item.item_code) {
			frappe.utils.add_link_title("Item", item.item_code, item.item_name || item.item_code);
		}
	});

	grid.refresh();
};

fitzgerald_kitchens.bom.resolve_fg_reference_id = function (node, frm) {
	if (node.is_root || node.data?.value === frm.doc.item_code) {
		return frm.doc.name;
	}

	const name = node.data?.assembly_row_name || node.data?.name;
	if (name && !String(name).startsWith("__routing__:") && !String(name).includes("__op__")) {
		return name;
	}

	const item_code = node.data?.value;
	if (item_code && frm.doc.items?.length) {
		const matches = frm.doc.items.filter(
			(row) => row.item_code === item_code && cint(row.is_expandable)
		);
		if (matches.length === 1) {
			return matches[0].name;
		}
	}

	return frm.doc.name;
};

(function () {
	const BCC_API =
		"fitzgerald_kitchens.fitzgerald_kitchens.doctype.bom_cost_calculator.bom_cost_calculator";

	function get_tree_wrapper(frm) {
		return frm.fields_dict.bom_cost_calculator && frm.fields_dict.bom_cost_calculator.wrapper;
	}

	function bcc_get_sub_assembly_modal_fields(view, is_root, read_only, phantom) {
		let fields = [
			{
				label: phantom ? __("Phantom Item") : __("Sub Assembly Item"),
				fieldname: "item_code",
				fieldtype: "Link",
				options: "Item",
				reqd: 1,
				read_only: read_only,
				filters: { is_stock_item: !phantom },
			},
			{ fieldtype: "Column Break" },
			{
				label: __("Qty"),
				fieldname: "qty",
				default: 1.0,
				fieldtype: "Float",
				reqd: 1,
				read_only: read_only,
			},
		];

		if (!phantom) {
			fields.push(
				{ fieldtype: "Section Break" },
				{
					label: __("Routing"),
					fieldname: "routing",
					fieldtype: "Link",
					options: "Routing",
					description: __(
						"Select routing for operation costs. Default BOM routing loads automatically."
					),
				}
			);
		}

		fields.push(
			{ fieldtype: "Section Break" },
			{
				label: __("Raw Materials"),
				fieldname: "items",
				fieldtype: "Table",
				fields: [
					{
						label: __("Item"),
						fieldname: "item_code",
						fieldtype: "Link",
						options: "Item",
						reqd: 1,
						in_list_view: 1,
						change() {
							const doc = this.doc;
							doc.qty = flt(doc.qty) || 1.0;
							this.grid.set_value("qty", doc.qty, doc);
							if (doc.item_code) {
								frappe.db.get_value("Item", doc.item_code, "item_name", (r) => {
									doc.item_name = r?.item_name || "";
									this.grid.refresh();
								});
							}
						},
					},
					{
						label: __("Item Name"),
						fieldname: "item_name",
						fieldtype: "Data",
						in_list_view: 1,
						read_only: 1,
					},
					{
						label: __("Qty"),
						fieldname: "qty",
						default: 1.0,
						fieldtype: "Float",
						reqd: 1,
						in_list_view: 1,
					},
				],
			}
		);

		return fields;
	}

	function bcc_setup_default_bom_autoload(dialog, phantom) {
		if (!dialog.fields_dict.item_code) {
			return;
		}

		dialog.fields_dict.item_code.df.change = function () {
			const item_code = dialog.get_value("item_code");
			if (!item_code || phantom) {
				return;
			}

			frappe.call({
				method: `${BCC_API}.get_default_bom_details`,
				args: { item_code },
				callback(r) {
					if (!r.message) {
						return;
					}
					if (r.message.routing) {
						dialog.set_value("routing", r.message.routing);
					}
					if (r.message.items?.length) {
						fitzgerald_kitchens.bom.populate_dialog_items(dialog, r.message.items);
					}
				},
			});
		};
	}

	function bcc_patch_configurator() {
		if (frappe.ui.BOMCostConfigurator?.prototype) {
			frappe.ui.BOMCostConfigurator.prototype.get_sub_assembly_modal_fields =
				bcc_get_sub_assembly_modal_fields;
		}

		const view = frappe.views.trees?.["BOM Cost Configurator"];
		if (view?.events) {
			view.events.get_sub_assembly_modal_fields = bcc_get_sub_assembly_modal_fields;
		}
	}

	function bcc_patch_add_sub_assembly(frm) {
		const view = frappe.views.trees?.["BOM Cost Configurator"];
		if (!view?.events) {
			return;
		}

		view.events.add_sub_assembly = function (node, view_ref, phantom) {
			let dialog = new frappe.ui.Dialog({
				fields: bcc_get_sub_assembly_modal_fields(view_ref, node.is_root, false, phantom),
				title: phantom ? __("Add Phantom Item") : __("Add Sub Assembly"),
			});

			bcc_setup_default_bom_autoload(dialog, phantom);
			dialog.show();
			dialog.set_primary_action(__("Add"), () => {
				let bom_item = dialog.get_values();
				if (!node.data?.parent_id) {
					node.data.parent_id = frm.doc.name;
				}

				frappe.call({
					method: `${BCC_API}.add_sub_assembly`,
					args: {
						parent: node.data.parent_id,
						fg_item: node.data.value,
						fg_reference_id: fitzgerald_kitchens.bom.resolve_fg_reference_id(node, frm),
						bom_item: bom_item,
						routing: bom_item.routing || "",
						phantom: phantom,
					},
					callback: (r) => view_ref.events.load_tree(r, node),
				});
				dialog.hide();
			});
		};

		view.events.convert_to_sub_assembly = function (node, view_ref, phantom) {
			let dialog = new frappe.ui.Dialog({
				fields: bcc_get_sub_assembly_modal_fields(view_ref, node.is_root, true, phantom),
				title: phantom ? __("Add Phantom Item") : __("Add Sub Assembly"),
			});

			dialog.set_values({ item_code: node.data.value, qty: node.data.qty });
			bcc_setup_default_bom_autoload(dialog, phantom);
			dialog.show();
			dialog.set_primary_action(__("Add"), () => {
				let bom_item = dialog.get_values();
				if (!bom_item.item_code) {
					frappe.throw(
						phantom ? __("Phantom Item is mandatory") : __("Sub Assembly Item is mandatory")
					);
				}

				frappe.call({
					method: `${BCC_API}.add_sub_assembly`,
					args: {
						parent: node.data.parent_id,
						fg_item: node.data.value,
						bom_item: bom_item,
						fg_reference_id: fitzgerald_kitchens.bom.resolve_fg_reference_id(node, frm),
						convert_to_sub_assembly: true,
						routing: bom_item.routing || "",
						phantom: phantom,
					},
					callback: (r) => {
						node.expandable = true;
						view_ref.events.load_tree(r, node.parent_node);
					},
				});
				dialog.hide();
			});
		};
	}

	function bcc_patch_tree_actions(frm) {
		const view = frappe.views.trees?.["BOM Cost Configurator"];
		if (!view?.events) {
			return;
		}

		view.events.delete_node = function (node, view_ref) {
			if (
				node.data?.is_routing_node ||
				node.data?.is_operation_node ||
				String(node.data?.value || "").startsWith("__routing__:")
			) {
				return;
			}

			frappe.confirm(__("Are you sure you want to delete this Item?"), () => {
				frappe.call({
					method: `${BCC_API}.delete_node`,
					args: {
						parent: node.data.parent_id || frm.doc.name,
						fg_item: node.data.value,
						doctype: node.data.doctype,
						docname: node.data.name,
					},
					callback: (r) => view_ref.events.load_tree(r, node.parent_node),
				});
			});
		};

		view.events.remove_routing = function (node, view_ref) {
			if (!node.data?.is_routing_node) {
				return;
			}

			frappe.confirm(__("Remove routing from this sub assembly?"), () => {
				frappe.call({
					method: `${BCC_API}.remove_routing`,
					args: {
						parent: node.data.parent_id || frm.doc.name,
						assembly_row_name: node.data.assembly_row_name,
					},
					callback: (r) => {
						const assembly_node = node.parent_node;
						if (assembly_node) {
							assembly_node.loaded = false;
							view_ref.events.load_tree(r, assembly_node);
						} else {
							view_ref.events.load_tree(r, node);
						}
					},
				});
			});
		};

		view.events.add_item = function (node, view_ref) {
			frappe.prompt(
				[
					{
						label: __("Item"),
						fieldname: "item_code",
						fieldtype: "Link",
						options: "Item",
						reqd: 1,
					},
					{ label: __("Qty"), fieldname: "qty", default: 1.0, fieldtype: "Float", reqd: 1 },
				],
				(data) => {
					if (!node.data.parent_id) {
						node.data.parent_id = frm.doc.name;
					}

					let fg_item = node.data.value;
					let fg_reference_id = fitzgerald_kitchens.bom.resolve_fg_reference_id(node, frm);

					if (node.data.is_routing_node) {
						fg_item = node.data.value;
						fg_reference_id = node.data.assembly_row_name || fg_reference_id;
					}

					frappe.call({
						method: `${BCC_API}.add_item`,
						args: {
							parent: node.data.parent_id || frm.doc.name,
							fg_item: fg_item,
							item_code: data.item_code,
							fg_reference_id: fg_reference_id,
							qty: data.qty,
						},
						callback: (r) => view_ref.events.load_tree(r, node),
					});
				},
				__("Add Item"),
				__("Add")
			);
		};

		view.events.edit_bom = function (node, view_ref) {
			const qty = node.data.qty || frm.doc.qty;
			frappe.prompt(
				[{ label: __("Qty"), fieldname: "qty", default: qty, fieldtype: "Float", reqd: 1 }],
				(data) => {
					frappe.call({
						method: `${BCC_API}.edit_bom_cost_calculator`,
						args: {
							doctype: node.data.doctype || frm.doc.doctype,
							docname: node.data.name || frm.doc.name,
							data: data,
							parent: node.data.parent_id || frm.doc.name,
						},
						callback: (r) => view_ref.events.load_tree(r, node),
					});
				},
				__("Edit BOM"),
				__("Update")
			);
		};

		view.events.load_tree = function (response, node) {
			const doc = response.message;
			if (doc?.raw_material_cost !== undefined) {
				frm.doc.raw_material_cost = doc.raw_material_cost;
			}

			frappe.views.trees["BOM Cost Configurator"].tree.load_children(node);

			let current = node;
			while (current) {
				let total_amount;
				const item_row = doc.items?.find((item) => item.name === current.data?.name);

				if (current.is_root || current.data?.value === frm.doc.item_code) {
					total_amount = doc.raw_material_cost;
				} else if (item_row) {
					total_amount = item_row.amount;
					current.data.amount = item_row.amount;
				} else if (current.data?.amount !== undefined) {
					total_amount = current.data.amount;
				}

				if (total_amount !== undefined) {
					const formatted = frappe.format(total_amount, {
						fieldtype: "Currency",
						currency: frm.doc.currency,
					});
					$(current.parent.get(0)).find(".fg-item-amt").first().html(formatted);
				}

				current = current.parent_node;
			}
		};
	}

	frappe.ui.form.on("BOM Cost Calculator", {
		setup(frm) {
			frm.trigger("set_queries");
		},

		onload(frm) {
			if (frm.is_new() && !frm.doc.items?.length) {
				frm._bcc_show_new_dialog = true;
			}
		},

		setup_bom_cost_calculator(frm) {
			frm.dashboard.clear_comment();

			if (!get_tree_wrapper(frm)) {
				return;
			}

			if (!frm.is_new()) {
				if (
					!frappe.bom_cost_configurator ||
					frappe.bom_cost_configurator.bom_configurator !== frm.doc.name
				) {
					frm.trigger("build_tree");
				}
			} else if (!frm.doc.items?.length && frm._bcc_show_new_dialog) {
				frm._bcc_show_new_dialog = false;
				$(get_tree_wrapper(frm)).empty();
				frm.trigger("make_new_entry");
			}
		},

		build_tree(frm) {
			const wrapper = get_tree_wrapper(frm);
			if (!wrapper) {
				return;
			}

			if (frm._bcc_build_in_progress) {
				return;
			}
			frm._bcc_build_in_progress = true;

			const $parent = $(wrapper);
			$parent.empty();
			$parent.closest(".section-body").css("max-width", "1100px");
			frm.toggle_enable("item_code", false);

			try {
				if (!frappe.ui.BOMCostConfigurator) {
					frappe.msgprint(__("Could not load BOM Cost Configurator."));
					return;
				}

				frappe.bom_cost_configurator = new frappe.ui.BOMCostConfigurator({
					wrapper: $parent,
					page: $parent,
					frm: frm,
					bom_configurator: frm.doc.name,
				});

				bcc_patch_configurator();
				bcc_patch_add_sub_assembly(frm);
				bcc_patch_tree_actions(frm);
			} catch (error) {
				console.error("BOM Cost Configurator init failed:", error);
				frappe.msgprint(
					__("Failed to initialize BOM Cost Configurator: {0}", [error.message || error])
				);
			} finally {
				frm._bcc_build_in_progress = false;
			}
		},

		make_new_entry(frm) {
			let dialog = new frappe.ui.Dialog({
				title: __("BOM Cost Calculator"),
				fields: [
					{ label: __("Name"), fieldtype: "Data", fieldname: "name", reqd: 1 },
					{ fieldtype: "Column Break" },
					{
						label: __("Company"),
						fieldtype: "Link",
						fieldname: "company",
						options: "Company",
						reqd: 1,
						default: frappe.defaults.get_user_default("Company"),
					},
					{ fieldtype: "Section Break" },
					{
						label: __("Item Code (Final Product)"),
						fieldtype: "Link",
						fieldname: "item_code",
						options: "Item",
						reqd: 1,
					},
					{ fieldtype: "Column Break" },
					{ label: __("Quantity"), fieldtype: "Float", fieldname: "qty", reqd: 1, default: 1.0 },
					{ fieldtype: "Section Break" },
					{
						label: __("Currency"),
						fieldtype: "Link",
						fieldname: "currency",
						options: "Currency",
						reqd: 1,
						default: frappe.defaults.get_global_default("currency"),
					},
					{ fieldtype: "Column Break" },
					{
						label: __("Conversion Rate"),
						fieldtype: "Float",
						fieldname: "conversion_rate",
						reqd: 1,
						default: 1.0,
					},
					{ fieldtype: "Section Break" },
					{
						label: __("Routing"),
						fieldtype: "Link",
						fieldname: "routing",
						options: "Routing",
					},
				],
				primary_action_label: __("Create"),
				primary_action: (values) => {
					values.doctype = frm.doc.doctype;
					frappe.db.insert(values).then((doc) => {
						frappe.set_route("Form", doc.doctype, doc.name);
					});
				},
			});

			dialog.fields_dict.item_code.get_query = "erpnext.controllers.queries.item_query";
			dialog.show();
		},

		set_queries(frm) {
			frm.set_query("item_code", "items", () => ({
				query: "erpnext.controllers.queries.item_query",
			}));
			frm.set_query("fg_item", "items", () => ({
				query: "erpnext.controllers.queries.item_query",
			}));
		},

		refresh(frm) {
			frappe.after_ajax(() => {
				frm.trigger("setup_bom_cost_calculator");
			});
			frm.trigger("set_root_item");
			frm.trigger("add_custom_buttons");
		},

		tab_2_tab(frm) {
			if (!frm.is_new()) {
				frappe.after_ajax(() => frm.trigger("build_tree"));
			}
		},

		set_root_item(frm) {
			if (frm.is_new() && frm.doc.items?.length) {
				frappe.model.set_value(
					frm.doc.items[0].doctype,
					frm.doc.items[0].name,
					"is_root",
					1
				);
			}
		},

		add_custom_buttons(frm) {
			if (!frm.is_new()) {
				frm.add_custom_button(__("Rebuild Tree"), () => frm.trigger("build_tree"));
			}
		},
	});

	frappe.ui.form.on("BOM Cost Calculator Item", {
		item_code(frm, cdt, cdn) {
			let item = frappe.get_doc(cdt, cdn);
			if (item.item_code && item.is_root) {
				frappe.model.set_value(cdt, cdn, "fg_item", item.item_code);
			}
		},
	});
})();
