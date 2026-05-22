// Copyright (c) 2026, talpha solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Development Unit QR Scan", {
	onload(frm) {
		if (frm.is_new()) {
			frm.set_value("scanned_by", frappe.session.user);
			frm.set_value("scan_datetime", frappe.datetime.now_datetime());
		}
	},
	refresh(frm) {
		render_qr_scan_area(frm);

		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Scan QR Code"), () => open_qr_scanner(frm), __("Actions"));
			frm.add_custom_button(__("Load Stages"), () => load_scan_lines(frm), __("Actions"));
		}
	},
	development_unit(frm) {
		if (frm.doc.development_unit && frm.doc.docstatus === 0) {
			load_scan_lines(frm);
		}
	},
	process_tracked(frm) {
		if (!frm.doc.process_tracked || !frm.doc.scan_lines?.length) {
			return;
		}
		frm.doc.scan_lines.forEach((row) => {
			frappe.model.set_value(row.doctype, row.name, "process_tracked", 1);
		});
	},
});

function render_qr_scan_area(frm) {
	const field = frm.get_field("qr_scan_area");
	if (!field) {
		return;
	}

	if (frm.doc.docstatus !== 0) {
		field.$wrapper.html(
			`<p class="text-muted small">${__("Submitted scan — stage updates were applied to the Development Unit.")}</p>`
		);
		return;
	}

	field.$wrapper.html(`
		<div style="padding: 4px 0 8px;">
			<p class="text-muted small" style="margin-bottom: 8px;">
				${__(
					"Scan the Development Unit QR code or select a unit, then set Updated Status for stages to complete."
				)}
			</p>
			<button type="button" class="btn btn-primary btn-sm btn-scan-qr">
				${__("Open Camera Scanner")}
			</button>
		</div>
	`);

	field.$wrapper.find(".btn-scan-qr").on("click", () => open_qr_scanner(frm));
}

function open_qr_scanner(frm) {
	const scanner = new frappe.ui.Scanner({
		dialog: true,
		multiple: false,
		on_scan(result) {
			const qr_text = result?.decodedText || result;
			resolve_and_set_unit(frm, qr_text);
		},
	});
	scanner.scan();
}

function resolve_and_set_unit(frm, qr_text) {
	frappe.call({
		method:
			"fitzgerald_kitchens.fitzgerald_kitchens.doctype.development_unit_qr_scan.development_unit_qr_scan.resolve_qr_code",
		args: { qr_text },
		freeze: true,
		freeze_message: __("Resolving QR code..."),
		callback(r) {
			if (!r.message?.development_unit) {
				return;
			}

			frm.set_value("development_unit", r.message.development_unit);
			frappe.show_alert({
				message: __("Development Unit {0} loaded", [r.message.development_unit]),
				indicator: "green",
			});
		},
	});
}

function load_scan_lines(frm) {
	if (!frm.doc.development_unit) {
		frappe.msgprint(__("Select or scan a Development Unit first."));
		return;
	}

	frappe.call({
		method:
			"fitzgerald_kitchens.fitzgerald_kitchens.doctype.development_unit_qr_scan.development_unit_qr_scan.get_stages_for_qr_scan",
		args: { development_unit: frm.doc.development_unit },
		freeze: true,
		freeze_message: __("Loading stages..."),
		callback(r) {
			const stages = r.message || [];
			frm.clear_table("scan_lines");

			stages.forEach((row) => {
				const child = frm.add_child("scan_lines");
				child.stage_row_name = row.name;
				child.stage = row.stage;
				child.sequence = row.sequence;
				child.status = row.status;
				child.process_tracked = row.process_tracked || 0;
			});

			frm.refresh_field("scan_lines");

			if (!stages.length) {
				frappe.msgprint(__("No stages found on this Development Unit."));
			}
		},
	});
}
