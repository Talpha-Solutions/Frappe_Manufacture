// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

const SITE_PROJECT_TYPE = "Site";
const KITCHEN_PROJECT_TYPE = "Kitchen";

const PROJECT_NAMING_SERIES = {
	[SITE_PROJECT_TYPE]: "PROJ-.####",
	Kitchen: "UNIT-KIT-.#####",
	Robe: "UNIT-ROB-.#####",
	Utility: "UNIT-UTL-.#####",
	"Vanity Unit": "UNIT-VAN-.#####",
	Pantry: "UNIT-PAN-.#####",
	Unit: "UNIT-UNT-.#####",
};

function force_project_overview_web_link(frm) {
	if (!frm || frm.doctype !== "Project" || frm.doc.__islocal) {
		return;
	}

	const path = "/project?project=" + encodeURIComponent(frm.doc.name);

	// ERPNext and prior refresh passes may each add a sidebar link; clear all first.
	if (frm.sidebar?.clear_user_actions) {
		frm.sidebar.clear_user_actions();
	} else if (frm.web_link) {
		frm.web_link.remove();
	}

	frm.add_web_link(path);
}

frappe.ui.form.on("Project", {
	refresh(frm) {
		// Run after ERPNext's refresh handler so only one link remains.
		frappe.after_ajax(() => force_project_overview_web_link(frm));

		toggle_unit_tab(frm);
		toggle_download_qr_tab(frm);
		toggle_parent_unit(frm);
		setup_parent_project_query(frm);
		setup_download_qr_actions(frm);
		setup_installation_manifest_actions(frm);
		setup_material_request_actions(frm);
		setup_production_plan_actions(frm);
		setup_amend_manifest_actions(frm);
		render_download_qr_html(frm);
	},
	project_type(frm) {
		toggle_unit_tab(frm);
		toggle_download_qr_tab(frm);
		toggle_parent_unit(frm);
		apply_default_naming_series(frm);
		sync_effective_manifest_from_configuration(frm);
		render_download_qr_html(frm);
	},
	fk_unit_configuration(frm) {
		sync_effective_manifest_from_configuration(frm);
	},
	fk_effective_manifest(frm) {
		render_download_qr_html(frm);
	},
});

function is_site_project(frm) {
	return frm.doc.project_type === SITE_PROJECT_TYPE;
}

function is_kitchen_project(frm) {
	return frm.doc.project_type === KITCHEN_PROJECT_TYPE;
}

function show_parent_unit(frm) {
	return !is_site_project(frm) && !is_kitchen_project(frm);
}

function toggle_unit_tab(frm) {
	frm.toggle_display("fk_unit_tab", !is_site_project(frm));
}

function toggle_download_qr_tab(frm) {
	frm.toggle_display("fk_download_qr_tab", !is_site_project(frm));
}

function toggle_parent_unit(frm) {
	const show = show_parent_unit(frm);
	frm.toggle_display("fk_parent_unit_project", show);
	if (!show && frm.doc.fk_parent_unit_project) {
		frm.set_value("fk_parent_unit_project", null);
	}
}

function setup_parent_project_query(frm) {
	frm.set_query("fk_parent_project", () => ({
		filters: { project_type: SITE_PROJECT_TYPE },
	}));

	frm.set_query("fk_parent_unit_project", () => ({
		filters: { project_type: KITCHEN_PROJECT_TYPE },
	}));
}

const KITCHEN_UTILITY_MANIFEST_TYPES = new Set([KITCHEN_PROJECT_TYPE, "Utility"]);

function sync_effective_manifest_from_configuration(frm) {
	if (is_site_project(frm) || !frm.doc.fk_unit_configuration || !frm.doc.project_type) {
		return;
	}

	frappe.db
		.get_value(
			"Project Unit Configuration",
			frm.doc.fk_unit_configuration,
			[
				"kitchen_utility_manifest",
				"wardrobe_manifest",
				"vanity_unit_manifest",
				"pantry_manifest",
			]
		)
		.then((r) => {
			const puc = r.message || {};
			let manifest = null;

			if (frm.doc.project_type === "Robe") {
				manifest = puc.wardrobe_manifest;
			} else if (frm.doc.project_type === "Vanity Unit") {
				manifest = puc.vanity_unit_manifest;
			} else if (frm.doc.project_type === "Pantry") {
				manifest = puc.pantry_manifest;
			} else if (KITCHEN_UTILITY_MANIFEST_TYPES.has(frm.doc.project_type)) {
				manifest = puc.kitchen_utility_manifest;
			}

			if (manifest && frm.doc.fk_effective_manifest !== manifest) {
				const current_manifest = frm.doc.fk_effective_manifest;
				if (!current_manifest) {
					frm.set_value("fk_effective_manifest", manifest);
					return;
				}

				frappe.db.get_value("Manifest", current_manifest, "scope").then((scope_r) => {
					if (scope_r.message?.scope === "Unit Snapshot") {
						return;
					}
					frm.set_value("fk_effective_manifest", manifest);
				});
			}
		});
}

function apply_default_naming_series(frm) {
	if (!frm.is_new() || !frm.doc.project_type) {
		return;
	}
	const series = PROJECT_NAMING_SERIES[frm.doc.project_type] || "UNIT-UNT-.#####";
	if (frm.doc.naming_series !== series) {
		frm.set_value("naming_series", series);
	}
}

function setup_download_qr_actions(frm) {
	if (frm.is_new() || is_site_project(frm) || !frm.fields_dict.fk_download_qr_html) {
		return;
	}

	frm.add_custom_button(__("Download QR"), () => download_project_qr_zip(frm), __("Actions"));
}

function setup_installation_manifest_actions(frm) {
	if (frm.is_new() || is_site_project(frm) || !frm.doc.fk_effective_manifest) {
		return;
	}

	frm.add_custom_button(
		__("Download Manifest"),
		() => download_installation_manifest(frm),
		__("Actions")
	);
}

function setup_material_request_actions(frm) {
	if (frm.is_new() || is_site_project(frm) || !frm.doc.fk_effective_manifest) {
		return;
	}
	if (!frappe.model.can_create("Material Request")) {
		return;
	}

	frm.add_custom_button(__("Material Request"), () => create_material_request_from_project(frm), __("Actions"));
}

function setup_production_plan_actions(frm) {
	if (frm.is_new() || is_site_project(frm) || !frm.doc.fk_effective_manifest) {
		return;
	}
	if (!frappe.model.can_create("Production Plan")) {
		return;
	}

	frm.add_custom_button(
		__("Create Production Plan"),
		() => create_production_plan_from_project(frm),
		__("Actions")
	);
}

function create_production_plan_from_project(frm) {
	if (!frm.doc.fk_effective_manifest) {
		frappe.msgprint(__("Set Effective Manifest on the Unit tab first."));
		return;
	}

	frappe.call({
		method: "fitzgerald_kitchens.setup.project_production_plan.make_production_plan_from_project",
		args: { project: frm.doc.name },
		freeze: true,
		freeze_message: __("Creating Production Plan..."),
		callback(r) {
			if (!r.message) {
				return;
			}
			frappe.model.sync(r.message);
			frappe.set_route("Form", "Production Plan", r.message.name);
		},
	});
}

function setup_amend_manifest_actions(frm) {
	if (frm.is_new() || is_site_project(frm) || !frm.doc.fk_effective_manifest) {
		return;
	}
	if (!frappe.model.can_create("Manifest")) {
		return;
	}

	frm.add_custom_button(
		__("Amend Effective Manifest"),
		() => amend_effective_manifest(frm),
		__("Actions")
	);
}

function amend_effective_manifest(frm) {
	if (!frm.doc.fk_effective_manifest) {
		frappe.msgprint(__("Set Effective Manifest on the Unit tab first."));
		return;
	}

	frappe.confirm(
		__(
			"Create an editable unit copy of the effective manifest? The project template manifest will not be changed."
		),
		() => {
			frappe.call({
				method: "fitzgerald_kitchens.setup.project_manifest_amend.amend_effective_manifest",
				args: { project: frm.doc.name },
				freeze: true,
				freeze_message: __("Creating unit manifest..."),
				callback(r) {
					if (!r.message) {
						return;
					}
					frm.set_value("fk_effective_manifest", r.message);
					frappe.show_alert({
						message: __("Unit manifest created. Template unchanged."),
						indicator: "green",
					});
					frappe.set_route("Form", "Manifest", r.message);
				},
			});
		}
	);
}

function create_material_request_from_project(frm) {
	if (!frm.doc.fk_effective_manifest) {
		frappe.msgprint(__("Set Effective Manifest on the Unit tab first."));
		return;
	}

	frappe.call({
		method: "fitzgerald_kitchens.setup.project_material_request.make_material_request_from_project",
		args: { project: frm.doc.name },
		freeze: true,
		freeze_message: __("Creating Material Request..."),
		callback(r) {
			if (!r.message) {
				return;
			}
			frappe.model.sync(r.message);
			frappe.set_route("Form", "Material Request", r.message.name);
		},
	});
}

function download_installation_manifest(frm) {
	if (!frm.doc.name || !frm.doc.fk_effective_manifest) {
		frappe.msgprint(__("Set Effective Manifest on the Unit tab first."));
		return;
	}

	const format = encodeURIComponent("Installation Manifest");
	const url = frappe.urllib.get_full_url(
		`/api/method/frappe.utils.print_format.download_pdf?doctype=Project&name=${encodeURIComponent(
			frm.doc.name
		)}&format=${format}&no_letterhead=1`
	);
	window.open(url);
}

function bind_download_qr_panel_events(frm, field) {
	field.$wrapper
		.off("click.fkQrDownload")
		.on("click.fkQrDownload", ".fk-qr-download-btn", function () {
			const idx = parseInt($(this).attr("data-row-idx"), 10);
			const row = (frm._fk_qr_label_rows || [])[idx];
			if (!row?.qr_base64) {
				frappe.msgprint(__("QR image is not available for this label."));
				return;
			}
			download_single_qr_png(row.item_instance_code, row.qr_base64);
		})
		.off("click.fkQrDownloadAll")
		.on("click.fkQrDownloadAll", ".fk-qr-download-all-btn", () => download_project_qr_zip(frm));
}

function render_download_qr_html(frm) {
	const field = frm.get_field("fk_download_qr_html");
	if (!field) {
		return;
	}

	if (frm.is_new() || is_site_project(frm)) {
		field.$wrapper.html("");
		return;
	}

	if (!frm.doc.fk_effective_manifest) {
		field.$wrapper.html(
			`<p class="text-muted">${__(
				"Set Effective Manifest on the Unit tab to generate QR labels."
			)}</p>`
		);
		return;
	}

	field.$wrapper.html(`<p class="text-muted">${__("Loading QR labels...")}</p>`);

	frappe.call({
		method: "fitzgerald_kitchens.setup.project_qr_labels.get_project_qr_label_data",
		args: { project: frm.doc.name },
		freeze_message: __("Loading QR labels..."),
		callback(r) {
			const data = r.message || {};
			const rows = data.rows || [];
			frm._fk_qr_label_rows = rows;

			if (!rows.length) {
				field.$wrapper.html(
					`<p class="text-muted">${__(
						"No QR labels found. Check manifest items and Include in QR Labels."
					)}</p>`
				);
				return;
			}

			const table_rows = rows
				.map((row, index) => {
					const item_label = row.item_name || row.item_code || "";
					const qr_cell = row.qr_base64
						? `<button type="button" class="fk-qr-download-btn" data-row-idx="${index}" title="${__(
								"Click to download QR"
						  )}">
								<img src="data:image/png;base64,${row.qr_base64}" alt="${frappe.utils.escape_html(
									row.item_instance_code
								)}">
								<span class="fk-qr-download-icon">${frappe.utils.icon("download", "sm")}</span>
							</button>`
						: `<span class="text-muted">—</span>`;

					return `<tr>
						<td class="fk-qr-col-no text-muted">${index + 1}</td>
						<td class="fk-qr-col-code"><code>${frappe.utils.escape_html(
							row.item_instance_code
						)}</code></td>
						<td class="fk-qr-col-item">${frappe.utils.escape_html(item_label)}</td>
						<td class="fk-qr-col-qr text-center">${qr_cell}</td>
					</tr>`;
				})
				.join("");

			field.$wrapper.html(`
				<style>
					.fk-download-qr-panel {
						border: 1px solid var(--border-color, #d1d8dd);
						border-radius: 8px;
						background: var(--card-bg, #fff);
						overflow: hidden;
					}
					.fk-download-qr-header {
						display: flex;
						align-items: center;
						justify-content: space-between;
						gap: 12px;
						padding: 12px 16px;
						border-bottom: 1px solid var(--border-color, #d1d8dd);
						background: var(--fg-hover-color, #f7f7f7);
					}
					.fk-download-qr-meta {
						font-size: 12px;
						color: var(--text-muted, #6c757d);
						line-height: 1.5;
					}
					.fk-download-qr-meta strong {
						color: var(--text-color, #36414c);
					}
					.fk-download-qr-table {
						margin-bottom: 0;
					}
					.fk-download-qr-table thead th {
						position: sticky;
						top: 0;
						z-index: 1;
						background: var(--fg-hover-color, #f7f7f7);
						white-space: nowrap;
					}
					.fk-qr-col-no {
						width: 48px;
						text-align: center;
					}
					.fk-qr-col-code code {
						font-size: 11px;
						word-break: break-all;
					}
					.fk-qr-col-qr {
						width: 96px;
					}
					.fk-qr-download-btn {
						position: relative;
						display: inline-flex;
						align-items: center;
						justify-content: center;
						padding: 4px;
						border: 1px solid var(--border-color, #d1d8dd);
						border-radius: 6px;
						background: #fff;
						cursor: pointer;
						transition: border-color 0.15s, box-shadow 0.15s;
					}
					.fk-qr-download-btn:hover {
						border-color: var(--primary, #2490ef);
						box-shadow: 0 0 0 1px var(--primary, #2490ef);
					}
					.fk-qr-download-btn img {
						width: 64px;
						height: 64px;
						display: block;
					}
					.fk-qr-download-icon {
						position: absolute;
						right: 4px;
						bottom: 4px;
						display: flex;
						align-items: center;
						justify-content: center;
						width: 22px;
						height: 22px;
						border-radius: 50%;
						background: rgba(36, 144, 239, 0.92);
						color: #fff;
						opacity: 0;
						transition: opacity 0.15s;
					}
					.fk-qr-download-btn:hover .fk-qr-download-icon {
						opacity: 1;
					}
				</style>
				<div class="fk-download-qr-panel">
					<div class="fk-download-qr-header">
						<div class="fk-download-qr-meta">
							<div>${__("Manifest")}: <strong>${frappe.utils.escape_html(
								data.manifest || ""
							)}</strong></div>
							<div>${__("{0} label(s)", [data.count || rows.length])} · ${__(
								"Click a QR to download that label"
							)}</div>
						</div>
						<button type="button" class="btn btn-primary btn-sm fk-qr-download-all-btn">
							${frappe.utils.icon("download", "xs")}
							${__("Download All")}
						</button>
					</div>
					<div class="table-responsive">
						<table class="table table-bordered table-sm table-striped table-hover fk-download-qr-table">
							<thead>
								<tr>
									<th class="fk-qr-col-no text-center">${__("No")}</th>
									<th>${__("Item Code")}</th>
									<th>${__("Item")}</th>
									<th class="text-center">${__("QR")}</th>
								</tr>
							</thead>
							<tbody>${table_rows}</tbody>
						</table>
					</div>
				</div>
			`);

			bind_download_qr_panel_events(frm, field);
		},
	});
}

function download_single_qr_png(item_instance_code, qr_base64) {
	const link = document.createElement("a");
	link.href = `data:image/png;base64,${qr_base64}`;
	link.download = `${item_instance_code}.png`;
	document.body.appendChild(link);
	link.click();
	link.remove();
}

function download_project_qr_zip(frm) {
	if (!frm.doc.name || !frm.doc.fk_effective_manifest) {
		frappe.msgprint(__("Set Effective Manifest on the Unit tab first."));
		return;
	}

	const url = frappe.urllib.get_full_url(
		"/api/method/fitzgerald_kitchens.setup.project_qr_labels.download_project_qr_zip?" +
			"project=" +
			encodeURIComponent(frm.doc.name)
	);

	frappe.run_serially([
		() => frappe.dom.freeze(__("Preparing QR download...")),
		() =>
			fetch(url, { credentials: "include" }).then((response) => {
				if (!response.ok) {
					throw new Error(__("Could not download QR labels"));
				}
				return response.blob();
			}),
		(blob) => {
			const object_url = window.URL.createObjectURL(blob);
			const link = document.createElement("a");
			link.href = object_url;
			link.download = `${frm.doc.name}-qr-labels.zip`;
			document.body.appendChild(link);
			link.click();
			link.remove();
			window.URL.revokeObjectURL(object_url);
		},
	]).catch(() => {
		frappe.msgprint(__("Could not download QR labels"));
	}).finally(() => {
		frappe.dom.unfreeze();
	});
}
