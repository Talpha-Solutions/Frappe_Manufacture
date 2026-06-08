const MAX_UPLOAD_COUNT = fitzgerald_kitchens.task_camera?.MAX_UPLOAD_COUNT || 25;

frappe.ui.form.on('Task', {
	refresh: function(frm) {
		setup_uploader_tab(frm);
		setup_label_scans_tab(frm);
	}
});

function setup_uploader_tab(frm) {
	if (!frm.get_field('custom_uploader_target')) return;

	let combined_html = `
		<div class="unified-stacked-container" style="display: flex; flex-direction: column; gap: 20px; margin-top: 15px;">
			<div class="camera-action-bar" style="padding: 15px 20px; border: 1px solid #e2e8f0; border-radius: 8px; background: #fff; display: flex; align-items: center; justify-content: space-between;">
				<div>
					<h5 style="font-size: 14px; font-weight: 600; color: #3c4b57; margin: 0;">
						<i class="fa fa-camera" style="margin-right: 6px; color: #1b66ec;"></i> Camera Utility
					</h5>
				</div>
				<button class="btn btn-secondary btn-sm btn-launch-camera-modal" type="button" style="padding: 6px 16px; font-weight: 500; display: flex; align-items: center; gap: 6px;">
					<i class="fa fa-video-camera"></i> Open Camera
				</button>
			</div>

			<div class="uploader-section" style="padding: 25px 20px; border: 2px dashed #b4c0cc; border-radius: 8px; background: #fdfefe; text-align: center; transition: all 0.2s ease;" onmouseover="this.style.borderColor='#1b66ec'; this.style.background='#f4f8ff';" onmouseout="this.style.borderColor='#b4c0cc'; this.style.background='#fdfefe';">
				<div class="upload-prompt-zone" style="margin-bottom: 15px;">
					<div style="font-size: 32px; color: #8a99a8; margin-bottom: 8px;"><i class="fa fa-cloud-upload"></i></div>
					<div style="font-size: 14px; font-weight: 500; color: #3c4b57; margin-bottom: 4px;">Drag & drop your files here</div>
					<div style="font-size: 12px; color: #8a99a8; margin-bottom: 15px;">or click the button below to browse local storage</div>
				</div>
				
				<button class="btn btn-primary btn-sm btn-upload-multi" type="button" style="padding: 6px 16px; font-weight: 500; box-shadow: 0 2px 4px rgba(27,102,236,0.15);">
					<i class="fa fa-plus" style="margin-right: 5px;"></i> Choose Files
				</button>
				<button class="btn btn-danger btn-sm btn-reset-uploads ml-2" type="button" style="display:none; padding: 6px 14px;">
					<i class="fa fa-trash-o"></i> Clear Gallery
				</button>
				
				<div class="thumbnail-gallery-wrapper d-flex flex-wrap justify-content-center" style="gap: 15px; margin-top: 20px; border-top: 1px solid #f0f4f7; padding-top: 20px; display: none !important;"></div>
			</div>
		</div>
	`;

	let wrapper = frm.get_field('custom_uploader_target').$wrapper;
	wrapper.html(combined_html);
	render_current_thumbnails(frm);

	wrapper.find('.btn-upload-multi').on('click', () => {
		if (frm.doc.__islocal) {
			frappe.msgprint(__('Please save the Task before uploading files.'));
			return;
		}

		frappe.call({
			method: 'fitzgerald_kitchens.fitzgerald_kitchens.custom.task.get_attached_files',
			args: { doctype: frm.doc.doctype, name: frm.doc.name },
			callback: (r) => {
				const existingCount = r.message ? r.message.length : 0;
				if (existingCount >= MAX_UPLOAD_COUNT) {
					frappe.msgprint(__('Maximum of {0} files already uploaded.', [MAX_UPLOAD_COUNT]));
					return;
				}

				new frappe.ui.FileUploader({
					doctype: frm.doc.doctype,
					docname: frm.doc.name,
					folder: 'Home/Attachments',
					allow_multiple: true,
					on_success: () => {
						render_current_thumbnails(frm);
					}
				});
			}
		});
	});

	wrapper.find('.btn-reset-uploads').on('click', () => {
		frappe.confirm(__('Are you sure you want to permanently delete all files in this gallery?'), () => {
			frappe.call({
				method: 'fitzgerald_kitchens.fitzgerald_kitchens.custom.task.delete_all_files',
				args: { doctype: frm.doc.doctype, name: frm.doc.name },
				callback: () => {
					render_current_thumbnails(frm);
					frappe.show_alert({ message: __('Gallery Reset Successfully'), indicator: 'green' });
				}
			});
		});
	});

	wrapper.find('.btn-launch-camera-modal').on('click', () => {
		if (frm.doc.__islocal) {
			frappe.msgprint(__('Please save the Task before launching camera assets.'));
			return;
		}
		fitzgerald_kitchens.task_camera.launch({
			doctype: frm.doc.doctype,
			docname: frm.doc.name,
			on_success: () => render_current_thumbnails(frm),
		});
	});
}

function render_current_thumbnails(frm) {
	if (frm.doc.__islocal) return;

	frappe.call({
		method: 'fitzgerald_kitchens.fitzgerald_kitchens.custom.task.get_attached_files',
		args: { doctype: frm.doc.doctype, name: frm.doc.name },
		callback: function(r) {
			let wrapper = frm.get_field('custom_uploader_target').$wrapper;
			let gallery = wrapper.find('.thumbnail-gallery-wrapper');
			let reset_btn = wrapper.find('.btn-reset-uploads');
			gallery.empty();

			const count = r.message ? r.message.length : 0;

			if (count < MAX_UPLOAD_COUNT) {
				wrapper.find('.btn-upload-multi').show();
			} else {
				wrapper.find('.btn-upload-multi').hide();
			}

			if (count > 0) {
				reset_btn.show();
				gallery.attr('style', 'gap: 15px; margin-top: 20px; border-top: 1px solid #eef2f5; padding-top: 20px; display: flex !important;');
				
				r.message.forEach(file => {
					let is_img = /\.(jpg|jpeg|png|gif|webp)$/i.test(file.file_url);
					let src = is_img ? file.file_url : '/assets/frappe/images/fallback_logo.svg';
					
					let thumb = $(
						'<div class="card thumbnail-card" data-file-id="' + file.name + '" style="width: 120px; border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden; background: #fff; box-shadow: 0 2px 4px rgba(0,0,0,0.05); cursor: pointer; transition: all 0.2s;">' +
							'<div style="height: 90px; background: #f8fafc; display: flex; align-items: center; justify-content: center; position: relative;">' +
								'<img src="' + src + '" style="max-width: 100%; max-height: 100%; object-fit: cover;">' +
								'<button class="btn btn-danger btn-xs btn-delete-file" type="button" style="position: absolute; top: 4px; right: 4px; padding: 2px 5px; font-size: 10px;"><i class="fa fa-trash"></i></button>' +
							'</div>' +
							'<div style="padding: 6px; font-size: 11px; font-weight: 500; color: #475569; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center; border-top: 1px solid #f1f5f9;" title="' + file.file_name + '">' + file.file_name + '</div>' +
						'</div>'
					);
					
					thumb.find('.btn-delete-file').on('click', (e) => {
						e.stopPropagation();
						frappe.confirm(__('Delete this file attachment?'), () => {
							frappe.call({
								method: 'frappe.client.delete',
								args: { doctype: 'File', name: file.name },
								callback: () => {
									thumb.remove();
									render_current_thumbnails(frm);
								}
							});
						});
					});
					
					thumb.on('click', () => window.open(file.file_url, '_blank'));
					gallery.append(thumb);
				});
			} else {
				reset_btn.hide();
				gallery.hide();
			}
		}
	});
}

function is_label_scan_task_type(task_type) {
	if (!task_type) {
		return false;
	}
	const normalized = String(task_type).trim().toLowerCase();
	if (normalized === "dispatch") {
		return true;
	}
	return ["Assembly", "Despatch", "Dispatch", "Delivery"].includes(task_type);
}

function setup_label_scans_tab(frm) {
	if (!frm.get_field('custom_label_scans_target')) {
		return;
	}

	const wrapper = frm.get_field('custom_label_scans_target').$wrapper;
	if (frm.doc.__islocal) {
		wrapper.html(
			`<div class="text-muted small">${__('Save the Task to view scanned QR labels.')}</div>`
		);
		return;
	}

	if (frm.doc.type && !is_label_scan_task_type(frm.doc.type)) {
		wrapper.html(
			`<div class="text-muted small">${__(
				'Label scans are tracked for Assembly, Despatch, and Delivery tasks only.'
			)}</div>`
		);
		return;
	}

	wrapper.html(`<div class="text-muted small">${__('Loading scanned labels...')}</div>`);

	frappe.call({
		method: 'fitzgerald_kitchens.fitzgerald_kitchens.page.task_scan.label_scan.get_task_label_scan_logs',
		args: { task: frm.doc.name },
		callback: (r) => {
			const data = r.message || {};
			const total = flt(data.total_labels) || 0;
			const scanned = flt(data.scanned) || 0;
			const progress = total ? Math.round((scanned / total) * 100) : 0;
			const logs = data.logs || [];

			let summary = `<div class="task-label-scan-summary" style="margin-bottom: 16px;">
				<div style="font-size: 13px; color: #475569; margin-bottom: 8px;">
					${total
						? __('{0} of {1} labels scanned ({2}%)', [scanned, total, progress])
						: __('No QR labels configured for this project yet.')}
				</div>`;

			if (total) {
				summary += `<div style="height: 8px; background: #e2e8f0; border-radius: 999px; overflow: hidden;">
					<div style="height: 100%; width: ${progress}%; background: #1b66ec;"></div>
				</div>`;
			}
			summary += `</div>`;

			if (!logs.length) {
				wrapper.html(
					summary +
						`<div class="text-muted small">${__('No QR labels scanned on this task yet.')}</div>`
				);
				return;
			}

			const rows = logs
				.map((log) => {
					const status_class = log.status === 'Scanned' ? 'text-success' : 'text-danger';
					const when = log.scan_datetime
						? frappe.datetime.str_to_user(log.scan_datetime)
						: '';
					const label = log.item_instance_code || log.qr_text || '';
					const qr_cell = log.qr_base64
						? `<img src="data:image/png;base64,${log.qr_base64}" alt="${frappe.utils.escape_html(label)}" style="width: 52px; height: 52px; object-fit: contain; border: 1px solid #e2e8f0; border-radius: 4px; background: #fff;">`
						: `<span class="text-muted">—</span>`;
					return `<tr>
						<td class="text-center">${qr_cell}</td>
						<td>${frappe.utils.escape_html(label)}</td>
						<td>${frappe.utils.escape_html(log.item_name || log.item_code || '')}</td>
						<td class="${status_class}">${frappe.utils.escape_html(log.status || '')}</td>
						<td>${frappe.utils.escape_html(log.scanned_by || '')}</td>
						<td>${frappe.utils.escape_html(when)}</td>
					</tr>`;
				})
				.join('');

			wrapper.html(
				summary +
					`<div class="table-responsive">
						<table class="table table-bordered table-condensed">
							<thead>
								<tr>
									<th>${__('QR Code')}</th>
									<th>${__('Label')}</th>
									<th>${__('Item')}</th>
									<th>${__('Status')}</th>
									<th>${__('Scanned By')}</th>
									<th>${__('When')}</th>
								</tr>
							</thead>
							<tbody>${rows}</tbody>
						</table>
					</div>`
			);
		},
	});
}
