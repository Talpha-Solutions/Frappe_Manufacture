const MAX_UPLOAD_COUNT = 25;

frappe.ui.form.on('Task', {
	refresh: function(frm) {
		setup_uploader_tab(frm);
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
		launch_camera_popup(frm);
	});
}

function launch_camera_popup(frm) {
	let localStream = null;

	let d = new frappe.ui.Dialog({
		title: __('Live Camera Capture'),
		fields: [{ fieldtype: 'HTML', fieldname: 'webcam_frame' }],
		primary_action_label: __('Close Camera'),
		primary_action() { d.hide(); }
	});

	function stop_camera() {
		if (localStream) {
			localStream.getTracks().forEach(track => track.stop());
			localStream = null;
		}
		let video = d.get_field('webcam_frame').$wrapper.find('#native-webcam-feed')[0];
		if (video) {
			video.srcObject = null;
		}
	}

	d.get_field('webcam_frame').$wrapper.html(`
		<div style="text-align: center; padding: 10px 0;">
			<div style="max-width: 100%; width: 420px; margin: 0 auto; border: 3px solid #1e293b; border-radius: 8px; background: #000; overflow: hidden; position: relative; box-shadow: 0 4px 12px rgba(0,0,0,0.2);">
				<video id="native-webcam-feed" autoplay playsinline muted style="width: 100%; height: auto; display: block;"></video>
			</div>
			<div style="margin-top: 15px;">
				<button class="btn btn-success btn-md btn-execute-photo-snap" type="button" style="padding: 8px 24px; font-weight: 600; font-size: 13px; box-shadow: 0 2px 6px rgba(40,167,69,0.3);">
					<i class="fa fa-circle" style="margin-right: 6px; color: #fff;"></i> Click to Snap Photo
				</button>
			</div>
			<canvas id="photo-capture-canvas" style="display: none;"></canvas>
		</div>
	`);

	d.on_page_show = function() {
		let video = d.get_field('webcam_frame').$wrapper.find('#native-webcam-feed')[0];
		
		navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false })
			.then(function(stream) {
				if (!d.display) {
					stream.getTracks().forEach(track => track.stop());
					return;
				}
				localStream = stream;
				if (video) {
					video.srcObject = stream;
					video.play().catch(function(err) {
						console.error("Webcam play failed: ", err);
					});
				}
			})
			.catch(function(err) {
				frappe.msgprint(__('Hardware access denied. Please check your system/browser app camera permissions.'));
				d.hide();
			});

		d.$wrapper.find('.btn-execute-photo-snap').on('click', function() {
			if (!localStream || !video) return;
			
			let canvas = d.get_field('webcam_frame').$wrapper.find('#photo-capture-canvas')[0];
			if (!canvas) return;

			canvas.width = video.videoWidth;
			canvas.height = video.videoHeight;
			
			let context = canvas.getContext('2d');
			context.drawImage(video, 0, 0, canvas.width, canvas.height);
			
			let dataUrl = canvas.toDataURL('image/png');
			
			stop_camera();
			d.hide();
			save_camera_snapshot_to_gallery(frm, dataUrl);
		});
	};

	d.on_hide = function() {
		stop_camera();
	};

	d.show();
}

function save_camera_snapshot_to_gallery(frm, base64Data) {
	let filename = "Snapshot_" + frappe.datetime.now_datetime().replace(/[: -]/g, "_") + ".png";
	frappe.show_alert({ message: __('Uploading captured image...'), indicator: 'blue' });

	frappe.call({
		method: 'fitzgerald_kitchens.fitzgerald_kitchens.custom.task.upload_camera_snapshot',
		args: {
			doctype: frm.doc.doctype,
			name: frm.doc.name,
			filename: filename,
			base64_data: base64Data
		},
		callback: function() {
			render_current_thumbnails(frm);
			frappe.show_alert({ message: __('Photo captured and saved to Gallery!'), indicator: 'green' });
		}
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
