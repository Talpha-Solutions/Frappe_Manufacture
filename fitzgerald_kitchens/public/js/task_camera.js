frappe.provide("fitzgerald_kitchens.task_camera");

const TASK_CAMERA_API = "fitzgerald_kitchens.fitzgerald_kitchens.custom.task";

fitzgerald_kitchens.task_camera = {
	MAX_UPLOAD_COUNT: 25,

	launch({ doctype, docname, on_success }) {
		if (!docname) {
			frappe.msgprint(__("Please save the Task before launching camera."));
			return;
		}

		// The attached-file count is just a soft admin cap, not something the
		// capture flow can function without — skip the round-trip when
		// offline (it would otherwise never call back and the camera would
		// silently fail to open), and fail open rather than closed if the
		// check itself errors out (e.g. a flaky connection).
		if (!navigator.onLine) {
			this._open_dialog({ doctype, docname, on_success });
			return;
		}

		frappe.call({
			method: `${TASK_CAMERA_API}.get_attached_files`,
			args: { doctype, name: docname },
			callback: (r) => {
				const existingCount = r.message ? r.message.length : 0;
				if (existingCount >= this.MAX_UPLOAD_COUNT) {
					frappe.msgprint(
						__("Maximum of {0} files already uploaded.", [this.MAX_UPLOAD_COUNT])
					);
					return;
				}
				this._open_dialog({ doctype, docname, on_success });
			},
			error: () => {
				this._open_dialog({ doctype, docname, on_success });
			},
		});
	},

	save_snapshot({ doctype, docname, blob, on_success }) {
		const filename = "Snapshot_" + frappe.datetime.now_datetime().replace(/[: -]/g, "_") + ".jpg";

		// Offline-capable path: only available where the shared outbox layer is
		// loaded (the My Tasks desk page — see hooks.py `page_js`). The blob is
		// queued in IndexedDB immediately and uploaded/linked once online,
		// reusing the same evidence-photo pipeline as Development Units.
		if (doctype === "Task" && window.fkDeskMyTasksOffline) {
			const wasOffline = !navigator.onLine;
			frappe.show_alert({
				message: wasOffline
					? __("Photo saved — will upload when back online")
					: __("Uploading captured image..."),
				indicator: "blue",
			});
			fitzgerald_kitchens.task_camera
				._queue_offline(docname, blob, filename)
				.then(function () {
					frappe.show_alert({
						message: wasOffline
							? __("Photo queued for upload")
							: __("Photo captured and saved to Gallery!"),
						indicator: "green",
					});
					if (on_success) {
						on_success();
					}
				})
				.catch(function (err) {
					frappe.msgprint({
						title: __("Photo capture failed"),
						message: String(err && err.message ? err.message : err),
						indicator: "red",
					});
				});
			return;
		}

		// Fallback (e.g. plain Task form, where the offline layer isn't
		// loaded): upload straight away via the original base64 JSON path.
		// Only works while online.
		frappe.show_alert({ message: __("Uploading captured image..."), indicator: "blue" });
		const reader = new FileReader();
		reader.onload = function () {
			frappe.call({
				method: `${TASK_CAMERA_API}.upload_camera_snapshot`,
				args: {
					doctype,
					name: docname,
					filename,
					base64_data: reader.result,
				},
				callback() {
					frappe.show_alert({
						message: __("Photo captured and saved to Gallery!"),
						indicator: "green",
					});
					if (on_success) {
						on_success();
					}
				},
			});
		};
		reader.readAsDataURL(blob);
	},

	_queue_offline(docname, blob, filename) {
		return fkDeskMyTasksOffline.queueTaskPhoto(docname, blob, filename);
	},

	_open_dialog({ doctype, docname, on_success }) {
		const me = this;
		let localStream = null;

		const d = new frappe.ui.Dialog({
			title: __("Live Camera Capture"),
			fields: [{ fieldtype: "HTML", fieldname: "webcam_frame" }],
			primary_action_label: __("Close Camera"),
			primary_action() {
				d.hide();
			},
		});

		function stop_camera() {
			if (localStream) {
				localStream.getTracks().forEach((track) => track.stop());
				localStream = null;
			}
			const video = d.get_field("webcam_frame").$wrapper.find("#native-webcam-feed")[0];
			if (video) {
				video.srcObject = null;
			}
		}

		d.get_field("webcam_frame").$wrapper.html(`
			<div style="text-align: center; padding: 10px 0;">
				<div style="max-width: 100%; width: 420px; margin: 0 auto; border: 3px solid #1e293b; border-radius: 8px; background: #000; overflow: hidden; position: relative; box-shadow: 0 4px 12px rgba(0,0,0,0.2);">
					<video id="native-webcam-feed" autoplay playsinline muted style="width: 100%; height: auto; display: block;"></video>
				</div>
				<div style="margin-top: 15px;">
					<button class="btn btn-success btn-md btn-execute-photo-snap" type="button" style="padding: 8px 24px; font-weight: 600; font-size: 13px; box-shadow: 0 2px 6px rgba(40,167,69,0.3);">
						<i class="fa fa-circle" style="margin-right: 6px; color: #fff;"></i> ${__("Click to Snap Photo")}
					</button>
				</div>
				<canvas id="photo-capture-canvas" style="display: none;"></canvas>
			</div>
		`);

		d.on_page_show = function () {
			const video = d.get_field("webcam_frame").$wrapper.find("#native-webcam-feed")[0];

			navigator.mediaDevices
				.getUserMedia({ video: { facingMode: "environment" }, audio: false })
				.then(function (stream) {
					if (!d.display) {
						stream.getTracks().forEach((track) => track.stop());
						return;
					}
					localStream = stream;
					if (video) {
						video.srcObject = stream;
						video.play().catch(function (err) {
							console.error("Webcam play failed: ", err);
						});
					}
				})
				.catch(function () {
					frappe.msgprint(
						__(
							"Hardware access denied. Please check your system/browser app camera permissions."
						)
					);
					d.hide();
				});

			d.$wrapper.find(".btn-execute-photo-snap").on("click", function () {
				if (!localStream || !video) {
					return;
				}

				const canvas = d.get_field("webcam_frame").$wrapper.find("#photo-capture-canvas")[0];
				if (!canvas) {
					return;
				}

				canvas.width = video.videoWidth;
				canvas.height = video.videoHeight;

				const context = canvas.getContext("2d");
				context.drawImage(video, 0, 0, canvas.width, canvas.height);

				canvas.toBlob(
					function (blob) {
						if (!blob) {
							return;
						}
						stop_camera();
						d.hide();
						me.save_snapshot({ doctype, docname, blob, on_success });
					},
					"image/jpeg",
					0.85
				);
			});
		};

		d.on_hide = function () {
			stop_camera();
		};

		d.show();
	},
};
