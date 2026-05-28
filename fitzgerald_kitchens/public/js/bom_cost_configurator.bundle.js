frappe.provide("frappe.ui");

(() => {
const BCC_API =
	"fitzgerald_kitchens.fitzgerald_kitchens.doctype.bom_cost_calculator.bom_cost_calculator";

function bcc_is_virtual_tree_node(node) {
	const data = node?.data || {};
	const value = String(data.value || "");
	return (
		data.is_routing_node ||
		data.is_raw_materials_node ||
		data.is_operation_node ||
		value.startsWith("__routing__:") ||
		value.startsWith("__raw_materials__:") ||
		value.includes("__op__")
	);
}

function bcc_is_removable_raw_material(node) {
	if (!node || node.is_root || bcc_is_virtual_tree_node(node)) {
		return false;
	}

	if (node.parent_node?.data?.is_raw_materials_node) {
		return true;
	}

	return !cint(node.expandable);
}

function bcc_is_deletable_assembly(node) {
	if (!node || node.is_root || bcc_is_virtual_tree_node(node)) {
		return false;
	}

	return cint(node.expandable);
}

class BOMCostConfigurator {
	constructor({ wrapper, page, frm, bom_configurator }) {
		this.$wrapper = $(wrapper);
		this.$wrapper.addClass("bcc-cost-tree-tab");
		this.$tree_container = $('<div class="bcc-tree-container"></div>').appendTo(this.$wrapper);
		this.page = this.$tree_container;
		this.bom_configurator = bom_configurator;
		this.frm = frm;
		this.ROUTING_PREFIX = "__routing__:";
		this.RAW_MATERIALS_PREFIX = "__raw_materials__:";
		this.OP_SUFFIX = "__op__";
		this.CC_API = BCC_API;

		this.make();
		this.prepare_layout();
		this.bind_events();
	}

	add_boms() {
		this.frm.call({
			method: "add_boms",
			freeze: true,
			doc: this.frm.doc,
		});
	}

	make() {
		let options = {
			...this.tree_options(),
			...this.tree_methods(),
		};

		this.tree_view = new frappe.views.TreeView(options);
		frappe.views.trees["BOM Cost Configurator"] = this.tree_view;

		const node = this.tree_view.tree?.root_node;
		if (!node) {
			return;
		}

		this._patch_tree_assembly_context();
		this.tree_view.tree.show_toolbar(node);
		this.tree_view.tree.load_children(node, true);
	}

	_patch_tree_assembly_context() {
		const tree = this.tree_view?.tree;
		if (!tree || tree._bcc_assembly_context_patched) {
			return;
		}

		tree._bcc_assembly_context_patched = true;
		const original_load_children = tree.load_children.bind(tree);

		const with_assembly_context = function (args, node) {
			if (
				node?.data?.expandable &&
				!node.is_root &&
				!node.data?.is_routing_node &&
				!node.data?.is_raw_materials_node &&
				!node.data?.is_operation_node
			) {
				args.assembly_row_name = node.data.name;
			}
		};

		tree.get_nodes = function (value, is_root) {
			const args = Object.assign({}, this.args);
			args.parent = value;
			args.is_root = is_root;
			with_assembly_context(args, this._bcc_expand_node);

			return new Promise((resolve) => {
				frappe.call({
					method: this.method,
					args,
					callback: (r) => {
						this.on_get_node && this.on_get_node(r.message);
						resolve(r.message);
					},
				});
			});
		};

		tree.get_all_nodes = function (value, is_root, label) {
			const args = Object.assign({}, this.args);
			args.label = label || value;
			args.parent = value;
			args.is_root = is_root;
			args.tree_method = this.method;
			delete args.assembly_row_name;

			return new Promise((resolve) => {
				frappe.call({
					method: "frappe.desk.treeview.get_all_nodes",
					args,
					callback: (r) => {
						this.on_get_node && this.on_get_node(r.message, true);
						resolve(r.message);
					},
				});
			});
		};

		tree.load_children = function (node, deep) {
			this._bcc_expand_node = node;
			return original_load_children(node, deep);
		};

		const original_show_toolbar = tree.show_toolbar.bind(tree);
		tree.show_toolbar = function (node) {
			if (node?.$tree_link && this.toolbar) {
				node.$toolbar?.remove();
				node.$toolbar = this.get_toolbar(node).insertAfter(node.$tree_link);
			}
			original_show_toolbar(node);
		};
	}

	bind_events() {
		frappe.views.trees["BOM Cost Configurator"].events = {
			frm: this.frm,
			add_item: this.add_item.bind(this),
			add_sub_assembly: this.add_sub_assembly.bind(this),
			set_query_for_workstation: this.set_query_for_workstation.bind(this),
			get_sub_assembly_modal_fields: this.get_sub_assembly_modal_fields.bind(this),
			convert_to_sub_assembly: this.convert_to_sub_assembly.bind(this),
			delete_node: this.delete_node.bind(this),
			remove_routing: this.remove_routing.bind(this),
			edit_bom: this.edit_bom.bind(this),
			load_tree: this.load_tree.bind(this),
			set_default_qty: this.set_default_qty.bind(this),
		};
	}

	tree_options() {
		return {
			parent: this.$tree_container.get(0),
			body: this.$tree_container.get(0),
			doctype: "BOM Cost Configurator",
			page: this.page,
			expandable: true,
			title: __("BOM Cost Calculator"),
			breadcrumb: "Manufacturing",
			get_tree_nodes: "fitzgerald_kitchens.fitzgerald_kitchens.doctype.bom_cost_calculator.bom_cost_calculator.get_children",
			root_label: this.frm.doc.item_code,
			disable_add_node: true,
			get_tree_root: false,
			show_expand_all: false,
			extend_toolbar: false,
			do_not_make_page: true,
			do_not_setup_menu: true,
		};
	}

	tree_methods() {
		let frm_obj = this;
		let view = frappe.views.trees["BOM Cost Configurator"];

		return {
			onload: function (me) {
				me.args["parent_id"] = frm_obj.frm.doc.name;
				me.args["parent"] = frm_obj.frm.doc.item_code;
				me.parent = frm_obj.$tree_container.get(0);
				me.body = frm_obj.$tree_container.get(0);
				me.make_tree();
			},
			onrender(node) {
				const data = node.data || {};

				if (data.is_routing_node) {
					frm_obj._render_routing_node(node);
					return;
				}

				if (data.is_raw_materials_node) {
					frm_obj._render_raw_materials_node(node);
					return;
				}

				if (data.is_operation_node) {
					frm_obj._render_operation_node(node);
					return;
				}

				const qty = data.qty || frm_obj.frm.doc.qty;
				const uom = data.uom || frm_obj.frm.doc.uom;
				const docname = data.name || frm_obj.frm.doc.name;
				let amount = flt(data.amount);

				if (node.is_root || data.value === frm_obj.frm.doc.item_code) {
					amount = flt(frm_obj.frm.doc.total_cost || frm_obj.frm.doc.raw_material_cost) || amount;
				} else if (data.expandable || data.routing) {
					amount = flt(data.amount) || amount;
				}

				amount = frappe.format(amount, {
					fieldtype: "Currency",
					currency: frm_obj.frm.doc.currency,
				});

				$(`
					<div class="pill small pull-right bom-qty-pill"
						style="background-color: var(--bg-white);
							color: var(--text-on-gray);
							font-weight:450;
							margin-right: 40px;
							display: inline-flex;
							min-width: 128px;
							border: 1px solid var(--bg-gray);
						">
							<div style="padding-right:5px" data-bom-qty-docname="${docname}">${qty} ${uom}</div>
							<div class="fg-item-amt" style="padding-left:12px; border-left:1px solid var(--bg-gray)">
								${amount}
							</div>
					</div>
				`).insertBefore(node.$ul);
			},
			toolbar:
				(this.frm?.doc.docstatus || 0) === 0
					? [
							{
								label: __(frappe.utils.icon("edit", "sm") + " BOM"),
								click: function (node) {
									let view = frappe.views.trees["BOM Cost Configurator"];
									view.events.edit_bom(node, view);
								},
								condition: function (node) {
									return (
										!node.data?.is_routing_node &&
										!node.data?.is_raw_materials_node &&
										!node.data?.is_operation_node
									);
								},
								btnClass: "hidden-xs",
							},
							{
								label: __(frappe.utils.icon("add", "sm") + " Raw Material"),
								click: function (node) {
									let view = frappe.views.trees["BOM Cost Configurator"];
									view.events.add_item(node, view);
								},
								condition: function (node) {
									if (node.data?.is_operation_node) {
										return false;
									}
									if (node.data?.is_raw_materials_node) {
										return true;
									}
									if (node.data?.is_routing_node) {
										return false;
									}
									return node.expandable && !node.data?.routing;
								},
								btnClass: "hidden-xs",
							},
							{
								label: __(frappe.utils.icon("add", "sm") + " Sub Assembly"),
								click: function (node) {
									let view = frappe.views.trees["BOM Cost Configurator"];
									view.events.add_sub_assembly(node, view);
								},
								condition: function (node) {
									return (
										node.expandable &&
										!node.data?.is_routing_node &&
										!node.data?.is_raw_materials_node &&
										!node.data?.is_operation_node
									);
								},
								btnClass: "hidden-xs",
							},
							{
								label: __(frappe.utils.icon("add", "sm") + " Phantom Item"),
								click: function (node) {
									let view = frappe.views.trees["BOM Cost Configurator"];
									view.events.add_sub_assembly(node, view, true);
								},
								condition: function (node) {
									return (
										node.expandable &&
										!node.data?.is_routing_node &&
										!node.data?.is_raw_materials_node &&
										!node.data?.is_operation_node
									);
								},
								btnClass: "hidden-xs",
							},
							{
								label: __("Collapse All"),
								click: function (node) {
									let view = frappe.views.trees["BOM Cost Configurator"];

									if (!node.expanded) {
										view.tree.load_children(node, true);
										$(node.parent[0]).find(".tree-children").show();
										node.$toolbar.find(".expand-all-btn").html(__("Collapse All"));
									} else {
										node.$tree_link.trigger("click");
										node.$toolbar.find(".expand-all-btn").html(__("Expand All"));
									}
								},
								condition: function (node) {
									return node.expandable && node.is_root;
								},
								btnClass: "hidden-xs expand-all-btn",
							},
							{
								label: __(frappe.utils.icon("move", "sm") + " Sub Assembly"),
								click: function (node) {
									let view = frappe.views.trees["BOM Cost Configurator"];
									view.events.convert_to_sub_assembly(node, view);
								},
								condition: function (node) {
									return (
										!node.expandable &&
										!node.data?.is_routing_node &&
										!node.data?.is_raw_materials_node &&
										!node.data?.is_operation_node
									);
								},
								btnClass: "hidden-xs",
							},
							{
								label: __(frappe.utils.icon("move", "sm") + " Phantom Item"),
								click: function (node) {
									let view = frappe.views.trees["BOM Cost Configurator"];
									view.events.convert_to_sub_assembly(node, view, true);
								},
								condition: function (node) {
									return (
										!node.expandable &&
										!node.data?.is_routing_node &&
										!node.data?.is_raw_materials_node &&
										!node.data?.is_operation_node
									);
								},
								btnClass: "hidden-xs",
							},
							{
								label: __(frappe.utils.icon("delete", "sm") + " Remove Route"),
								click: function (node) {
									let view = frappe.views.trees["BOM Cost Configurator"];
									view.events.remove_routing(node, view);
								},
								condition: function (node) {
									return node.data?.is_routing_node;
								},
								btnClass: "hidden-xs",
							},
							{
								label: __(frappe.utils.icon("delete", "sm") + " Remove Raw Material"),
								click: function (node) {
									let view = frappe.views.trees["BOM Cost Configurator"];
									view.events.delete_node(node, view);
								},
								condition: bcc_is_removable_raw_material,
							},
							{
								label: __(frappe.utils.icon("delete", "sm") + " Item"),
								click: function (node) {
									let view = frappe.views.trees["BOM Cost Configurator"];
									view.events.delete_node(node, view);
								},
								condition: bcc_is_deletable_assembly,
								btnClass: "hidden-xs",
							},
					  ]
					: [
							{
								label: __("Expand All"),
								click: function (node) {
									let view = frappe.views.trees["BOM Cost Configurator"];

									if (!node.expanded) {
										view.tree.load_children(node, true);
										$(node.parent[0]).find(".tree-children").show();
										node.$toolbar.find(".expand-all-btn").html(__("Collapse All"));
									} else {
										node.$tree_link.trigger("click");
										node.$toolbar.find(".expand-all-btn").html(__("Expand All"));
									}
								},
								condition: function (node) {
									return node.expandable && node.is_root;
								},
								btnClass: "hidden-xs expand-all-btn",
							},
					  ],
		};
	}

	add_item(node, view) {
		frappe.prompt(
			[
				{ label: __("Item"), fieldname: "item_code", fieldtype: "Link", options: "Item", reqd: 1 },
				{ label: __("Qty"), fieldname: "qty", default: 1.0, fieldtype: "Float", reqd: 1 },
			],
			(data) => {
				if (!node.data.parent_id) {
					node.data.parent_id = this.frm.doc.name;
				}

				let fg_item = node.data.value;
				let fg_reference_id = fitzgerald_kitchens.bom.resolve_fg_reference_id(node, this.frm);

				if (node.data.is_raw_materials_node) {
					fg_item = node.data.value;
				} else if (node.data.is_routing_node) {
					fg_item = node.data.value;
					fg_reference_id = node.data.assembly_row_name || fg_reference_id;
				}

				frappe.call({
					method: `${BCC_API}.add_item`,
					args: {
						parent: node.data.parent_id,
						fg_item: fg_item,
						item_code: data.item_code,
						fg_reference_id: fg_reference_id,
						qty: data.qty,
					},
					callback: (r) => {
						view.events.load_tree(r, node);
					},
				});
			},
			__("Add Item"),
			__("Add")
		);
	}

	set_query_for_workstation(dialog) {
		let workstation = dialog.fields.filter((field) => field.fieldname === "workstation");
		if (workstation.length) {
			workstation[0].get_query = function () {
				let workstation_type = dialog.get_value("workstation_type");

				if (workstation_type) {
					return {
						filters: {
							workstation_type: dialog.get_value("workstation_type"),
						},
					};
				}
			};
		}
	}

	add_sub_assembly(node, view, phantom = false) {
		let me = this;
		let dialog = new frappe.ui.Dialog({
			fields: view.events.get_sub_assembly_modal_fields(view, node.is_root, false, phantom),
			title: phantom ? __("Add Phantom Item") : __("Add Sub Assembly"),
		});

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
						if (fitzgerald_kitchens.bom?.populate_dialog_items) {
							fitzgerald_kitchens.bom.populate_dialog_items(dialog, r.message.items);
						}
					}
				},
			});
		};

		dialog.show();
		dialog.set_primary_action(__("Add"), () => {
			let bom_item = dialog.get_values();

			if (!node.data?.parent_id) {
				node.data.parent_id = this.frm.doc.name;
			}

			frappe.call({
				method: `${BCC_API}.add_sub_assembly`,
				args: {
					parent: node.data.parent_id,
					fg_item: node.data.value,
					fg_reference_id: fitzgerald_kitchens.bom.resolve_fg_reference_id(node, this.frm),
					bom_item: bom_item,
					routing: bom_item.routing || "",
					phantom: phantom,
				},
				callback: (r) => {
					view.events.load_tree(r, node);
				},
			});

			dialog.hide();
		});
	}

	get_sub_assembly_modal_fields(view, is_root = false, read_only = false, phantom = false) {
		let fields = [
			{
				label: phantom ? __("Phantom Item") : __("Sub Assembly Item"),
				fieldname: "item_code",
				fieldtype: "Link",
				options: "Item",
				reqd: 1,
				read_only: read_only,
				filters: {
					is_stock_item: !phantom,
				},
			},
			{ fieldtype: "Column Break" },
			{
				label: __("Qty"),
				fieldname: "qty",
				default: 1.0,
				fieldtype: "Float",
				reqd: 1,
				read_only: read_only,
				change() {
					this.layout.fields_dict.items.grid.data.forEach((row) => {
						row.qty = flt(this.value);
					});

					this.layout.fields_dict.items.grid.refresh();
				},
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
					description: __("Select routing for operation costs. Default BOM routing loads automatically."),
				}
			);
		}

		fields.push(
			...[
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
								let doc = this.doc;
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
				},
			]
		);

		return fields;
	}

	convert_to_sub_assembly(node, view, phantom = false) {
		let me = this;
		let dialog = new frappe.ui.Dialog({
			fields: view.events.get_sub_assembly_modal_fields(view, node.is_root, true, phantom),
			title: phantom ? __("Add Phantom Item") : __("Add Sub Assembly"),
		});

		dialog.set_values({
			item_code: node.data.value,
			qty: node.data.qty,
		});

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
						if (fitzgerald_kitchens.bom?.populate_dialog_items) {
							fitzgerald_kitchens.bom.populate_dialog_items(dialog, r.message.items);
						}
					}
				},
			});
		};

		dialog.show();
		dialog.set_primary_action(__("Add"), () => {
			let bom_item = dialog.get_values();

			if (!bom_item.item_code) {
				frappe.throw(
					phantom ? __("Phantom Item is mandatory") : __("Sub Assembly Item is mandatory")
				);
			}

			(bom_item.items || []).forEach((d) => {
				if (!d.item_code) {
					frappe.throw(__("Item is mandatory in Raw Materials table."));
				}
			});

			frappe.call({
				method: `${BCC_API}.add_sub_assembly`,
				args: {
					parent: node.data.parent_id,
					fg_item: node.data.value,
					bom_item: bom_item,
					fg_reference_id: fitzgerald_kitchens.bom.resolve_fg_reference_id(node, this.frm),
					convert_to_sub_assembly: true,
					routing: bom_item.routing || "",
					phantom: phantom,
				},
				callback: (r) => {
					node.expandable = true;
					view.events.load_tree(r, node.parent_node);
				},
			});

			dialog.hide();
		});
	}

	set_default_qty(dialog) {
		dialog.fields_dict.items.grid.fields_map.item_code.onchange = function (event) {
			if (event) {
				let name = $(event.currentTarget).closest(".grid-row").attr("data-name");
				let item_row = dialog.fields_dict.items.grid.grid_rows_by_docname[name].doc;
				item_row.qty = 1;
				dialog.fields_dict.items.grid.refresh();
			}
		};
	}

	delete_node(node, view) {
		if (bcc_is_virtual_tree_node(node)) {
			return;
		}

		if (!bcc_is_removable_raw_material(node) && !bcc_is_deletable_assembly(node)) {
			return;
		}

		const is_raw_material = bcc_is_removable_raw_material(node);

		const message = is_raw_material
			? __("Are you sure you want to remove this raw material?")
			: __("Are you sure you want to delete this Item?");

		let fg_item = node.data.fg_item || node.data.value;
		if (node.parent_node?.data?.is_raw_materials_node && node.parent_node.data.assembly_row_name) {
			const assembly_row = this.frm.doc.items?.find(
				(row) => row.name === node.parent_node.data.assembly_row_name
			);
			if (assembly_row?.item_code) {
				fg_item = assembly_row.item_code;
			}
		}

		frappe.confirm(message, () => {
			frappe.call({
				method: `${BCC_API}.delete_node`,
				args: {
					parent: node.data.parent_id,
					fg_item,
					doctype: node.data.doctype,
					docname: node.data.name,
				},
				callback: (r) => {
					let reload_node = node.parent_node;
					if (reload_node?.data?.is_raw_materials_node) {
						reload_node.loaded = false;
					} else if (reload_node?.data?.expandable) {
						reload_node.loaded = false;
					}
					view.events.load_tree(r, reload_node || node.parent_node);
				},
			});
		});
	}

	remove_routing(node, view) {
		if (!node.data?.is_routing_node) {
			return;
		}

		frappe.confirm(__("Remove routing from this sub assembly?"), () => {
			frappe.call({
				method: `${BCC_API}.remove_routing`,
				args: {
					parent: node.data.parent_id,
					assembly_row_name: node.data.assembly_row_name,
				},
				callback: (r) => {
					const assembly_node = node.parent_node;
					if (assembly_node) {
						assembly_node.loaded = false;
						view.events.load_tree(r, assembly_node);
					} else {
						view.events.load_tree(r, node);
					}
				},
			});
		});
	}

	edit_bom(node, view) {
		let me = this;
		let qty = node.data.qty || this.frm.doc.qty;
		let fields = [{ label: __("Qty"), fieldname: "qty", default: qty, fieldtype: "Float", reqd: 1 }];

		this.frm.edit_bom_dialog = frappe.prompt(
			fields,
			(data) => {
				let doctype = node.data.doctype || this.frm.doc.doctype;
				let docname = node.data.name || this.frm.doc.name;

				frappe.call({
					method: `${BCC_API}.edit_bom_cost_calculator`,
					args: {
						doctype: doctype,
						docname: docname,
						data: data,
						parent: node.data.parent_id || this.frm.doc.name,
					},
					callback: (r) => {
						for (let key in data) {
							node.data[key] = data[key];
						}

						let uom = node.data.uom || this.frm.doc.uom;
						$(node.parent.get(0))
							.find(`[data-bom-qty-docname='${docname}']`)
							.html(data.qty + " " + uom);
						view.events.load_tree(r, node);
					},
				});
			},
			__("Edit BOM"),
			__("Update")
		);
	}

	prepare_layout() {
		let main_div = this.$tree_container[0];
		let tree_children = $(main_div).find(".tree-children")[0];

		if (main_div) {
			main_div.style.marginBottom = "0";
		}

		if (tree_children) {
			tree_children.style.minHeight = "320px";
			tree_children.style.maxHeight = "320px";
			tree_children.style.overflowY = "auto";
		}

		this.setup_bottom_panel();
	}

	setup_bottom_panel() {
		this.$wrapper.find(".bcc-bottom-panel").remove();

		this.$bottom_panel = $(`
			<div class="bcc-bottom-panel border-top pt-3 mt-3">
				<div class="row align-items-stretch">
					<div class="col-md-7 col-sm-12">
						<div class="d-flex justify-content-between align-items-center mb-2">
							<h6 class="mb-0 text-muted">${__("Other Charges")}</h6>
							<button type="button" class="btn btn-sm btn-primary bcc-add-other-charge">
								${__("Add Other Charge")}
							</button>
						</div>
						<div class="bcc-other-charges-table-wrapper">
							<table class="table table-sm table-bordered bcc-other-charges-table mb-0">
								<thead>
									<tr>
										<th>${__("Charge Type")}</th>
										<th>${__("Description")}</th>
										<th class="text-right">${__("Amount")}</th>
										<th style="width:40px;"></th>
									</tr>
								</thead>
								<tbody></tbody>
							</table>
							<div class="bcc-other-charges-empty text-muted small py-3 text-center">
								${__("No other charges added yet.")}
							</div>
						</div>
					</div>
					<div class="col-md-5 col-sm-12 mt-3 mt-md-0">
						<div class="bcc-cost-summary-card">
							<div class="bcc-summary-header">
								<span class="bcc-summary-title">${__("Cost Summary")}</span>
								<span class="bcc-summary-subtitle">${__("Live breakdown of estimated BOM cost")}</span>
							</div>
							<div class="bcc-summary-body">
								<div class="bcc-summary-row">
									<span class="bcc-summary-row-label">${__("Raw Materials")}</span>
									<span class="bcc-summary-value bcc-rm-total">0</span>
								</div>
								<div class="bcc-summary-row">
									<span class="bcc-summary-row-label">${__("Route")}</span>
									<span class="bcc-summary-value bcc-route-total">0</span>
								</div>
								<div class="bcc-summary-row">
									<span class="bcc-summary-row-label">${__("Other Charges")}</span>
									<span class="bcc-summary-value bcc-other-total">0</span>
								</div>
							</div>
							<div class="bcc-summary-total">
								<span class="bcc-summary-total-label">${__("Total Cost")}</span>
								<span class="bcc-summary-total-value bcc-grand-total">0</span>
							</div>
						</div>
					</div>
				</div>
			</div>
		`).appendTo(this.$wrapper);

		this.$bottom_panel.find(".bcc-add-other-charge").on("click", () => this.show_add_other_charge_dialog());
		this.refresh_other_charges_table();
		this.refresh_cost_summary();
	}

	show_add_other_charge_dialog() {
		const dialog = new frappe.ui.Dialog({
			title: __("Add Other Charge"),
			fields: [
				{
					label: __("Charge Type"),
					fieldname: "charge_type",
					fieldtype: "Select",
					options: [
						"Freight",
						"Installation",
						"Design",
						"Labour",
						"Transport",
						"Packaging",
						"Miscellaneous",
					].join("\n"),
					reqd: 1,
				},
				{
					label: __("Description"),
					fieldname: "description",
					fieldtype: "Data",
				},
				{
					label: __("Amount"),
					fieldname: "amount",
					fieldtype: "Currency",
					options: "currency",
					reqd: 1,
				},
			],
			primary_action_label: __("Add"),
			primary_action: (values) => {
				frappe.call({
					method: `${BCC_API}.add_other_charge`,
					args: {
						parent: this.frm.doc.name,
						charge_type: values.charge_type,
						description: values.description,
						amount: values.amount,
					},
					callback: (r) => {
						this.sync_doc_from_response(r.message);
						this.refresh_other_charges_table();
						this.refresh_cost_summary();
						this.refresh_root_tree_cost();
						dialog.hide();
					},
				});
			},
		});

		dialog.show();
	}

	remove_other_charge(row_name) {
		frappe.confirm(__("Remove this other charge?"), () => {
			frappe.call({
				method: `${BCC_API}.remove_other_charge`,
				args: {
					parent: this.frm.doc.name,
					row_name: row_name,
				},
				callback: (r) => {
					this.sync_doc_from_response(r.message);
					this.refresh_other_charges_table();
					this.refresh_cost_summary();
					this.refresh_root_tree_cost();
				},
			});
		});
	}

	sync_doc_from_response(doc) {
		if (!doc) {
			return;
		}

		this.frm.doc.other_charges = doc.other_charges || this.frm.doc.other_charges || [];
		this.frm.doc.raw_materials_total = doc.raw_materials_total;
		this.frm.doc.routing_cost_total = doc.routing_cost_total;
		this.frm.doc.other_charges_total = doc.other_charges_total;
		this.frm.doc.raw_material_cost = doc.raw_material_cost ?? doc.bom_cost;
		this.frm.doc.total_cost = doc.total_cost;
	}

	render_cost_summary(summary) {
		if (!summary || !this.$bottom_panel?.length) {
			return;
		}

		this.sync_doc_from_response({ ...this.frm.doc, ...summary });
		this.$bottom_panel.find(".bcc-rm-total").html(this.format_currency(summary.raw_materials_total));
		this.$bottom_panel.find(".bcc-route-total").html(this.format_currency(summary.routing_cost_total));
		this.$bottom_panel.find(".bcc-other-total").html(this.format_currency(summary.other_charges_total));
		this.$bottom_panel
			.find(".bcc-grand-total")
			.html(this.format_currency(summary.total_cost ?? summary.bom_cost));
		this.refresh_root_tree_cost();
	}

	format_currency(value) {
		return frappe.format(flt(value), {
			fieldtype: "Currency",
			currency: this.frm.doc.currency,
		});
	}

	refresh_other_charges_table() {
		if (!this.$bottom_panel?.length) {
			return;
		}

		const charges = this.frm.doc.other_charges || [];
		const $tbody = this.$bottom_panel.find(".bcc-other-charges-table tbody");
		$tbody.empty();

		if (!charges.length) {
			this.$bottom_panel.find(".bcc-other-charges-table").hide();
			this.$bottom_panel.find(".bcc-other-charges-empty").show();
			return;
		}

		this.$bottom_panel.find(".bcc-other-charges-table").show();
		this.$bottom_panel.find(".bcc-other-charges-empty").hide();

		charges.forEach((row) => {
			const $tr = $(`
				<tr data-name="${row.name}">
					<td>${frappe.utils.escape_html(row.charge_type || "")}</td>
					<td>${frappe.utils.escape_html(row.description || "")}</td>
					<td class="text-right">${this.format_currency(row.amount)}</td>
					<td class="text-center">
						<button type="button" class="btn btn-xs btn-link text-danger bcc-remove-other-charge" title="${__("Remove")}">
							${frappe.utils.icon("delete", "sm")}
						</button>
					</td>
				</tr>
			`);
			$tr.find(".bcc-remove-other-charge").on("click", () => this.remove_other_charge(row.name));
			$tbody.append($tr);
		});
	}

	refresh_cost_summary() {
		if (!this.$bottom_panel?.length || !this.frm.doc.name) {
			return;
		}

		frappe.call({
			method: `${BCC_API}.get_cost_summary`,
			args: { parent: this.frm.doc.name },
			callback: (r) => this.render_cost_summary(r.message),
		});
	}

	refresh_root_tree_cost() {
		const tree = frappe.views.trees?.["BOM Cost Configurator"]?.tree;
		const root = tree?.root_node;
		if (!root) {
			return;
		}

		const total = this.frm.doc.total_cost || this.frm.doc.raw_material_cost;
		const formatted = this.format_currency(total);
		$(root.parent?.get(0)).find(".fg-item-amt").first().html(formatted);
	}

	load_tree(response, node) {
		const doc = response.message;
		if (doc) {
			this.sync_doc_from_response(doc);
		}

		frappe.views.trees["BOM Cost Configurator"].tree.load_children(node);

		let current = node;
		while (current) {
			let total_amount;
			const item_row = doc?.items?.find((item) => item.name === current.data?.name);

			if (current.is_root || current.data?.value === this.frm.doc.item_code) {
				total_amount = doc?.total_cost || doc?.raw_material_cost;
			} else if (item_row) {
				total_amount = item_row.amount;
				current.data.amount = item_row.amount;
			} else if (current.data?.amount !== undefined) {
				total_amount = current.data.amount;
			}

			if (total_amount !== undefined) {
				const formatted = this.format_currency(total_amount);
				$(current.parent.get(0)).find(".fg-item-amt").first().html(formatted);
			}

			current = current.parent_node;
		}

		this.refresh_other_charges_table();
		this.refresh_cost_summary();
	}

	_render_routing_node(node) {
		const data = node.data || {};
		const totalCost = frappe.format(data.amount || 0, {
			fieldtype: "Currency",
			currency: this.frm.doc.currency,
		});

		node.$tree_link
			.find(".tree-label")
			.html(__(data.routing_name || data.title || "Route"))
			.css("color", "var(--blue-500)");

		$(`
			<div class="pull-right bom-routing-pill"
				style="display:inline-flex; align-items:center; gap:6px; margin-right:40px;">
				<span class="badge badge-info"
					style="background:var(--blue-100);color:var(--blue-700);
						font-size:11px; padding:2px 7px; border-radius:10px;">
					${__("Route")}
				</span>
				<span class="fg-item-amt"
					style="background-color:var(--bg-white);
						border:1px solid var(--blue-200);
						color:var(--blue-700);
						font-weight:500;
						border-radius:4px;
						padding:2px 10px;
						min-width:100px;
						text-align:right;">
					${totalCost}
				</span>
			</div>
		`).insertBefore(node.$ul);
	}

	_render_raw_materials_node(node) {
		const data = node.data || {};
		const totalCost = frappe.format(data.amount || 0, {
			fieldtype: "Currency",
			currency: this.frm.doc.currency,
		});

		node.$tree_link.find(".tree-label").html(__("Raw Materials")).css("color", "var(--green-600)");

		$(`
			<div class="pull-right bom-raw-materials-pill"
				style="display:inline-flex; align-items:center; gap:6px; margin-right:40px;">
				<span class="badge badge-success"
					style="background:var(--green-100);color:var(--green-700);
						font-size:11px; padding:2px 7px; border-radius:10px;">
					${__("Raw Materials")}
				</span>
				<span class="fg-item-amt"
					style="background-color:var(--bg-white);
						border:1px solid var(--green-200);
						color:var(--green-700);
						font-weight:500;
						border-radius:4px;
						padding:2px 10px;
						min-width:100px;
						text-align:right;">
					${totalCost}
				</span>
			</div>
		`).insertBefore(node.$ul);
	}

	_render_operation_node(node) {
		const data = node.data || {};
		const timeInMins = flt(data.qty);
		const cost = frappe.format(data.amount || 0, {
			fieldtype: "Currency",
			currency: this.frm.doc.currency,
		});

		node.$tree_link.find(".tree-label").css("color", "var(--gray-700)");

		$(`
			<div class="pull-right bom-operation-pill"
				style="display:inline-flex; align-items:center; gap:6px; margin-right:40px;">
				<span style="color:var(--gray-600); font-size:12px;">
					${timeInMins} ${__("mins")}
				</span>
				<span class="fg-item-amt"
					style="background-color:var(--bg-white);
						border:1px solid var(--bg-gray);
						color:var(--text-on-gray);
						font-weight:450;
						border-radius:4px;
						padding:2px 10px;
						min-width:100px;
						text-align:right;">
					${cost}
				</span>
			</div>
		`).insertBefore(node.$ul);
	}
}

frappe.ui.BOMCostConfigurator = BOMCostConfigurator;
})();
