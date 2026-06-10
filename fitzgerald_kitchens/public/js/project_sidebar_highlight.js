frappe.provide("fitzgerald_kitchens.project_sidebar");

(function () {
	// Desk does not define frappe.ready (website only). Polyfill for stale cached scripts.
	if (window.frappe && typeof frappe.ready !== "function") {
		frappe.ready = function (callback) {
			if (frappe.app?.sidebar) {
				callback();
				return;
			}
			const run = () => {
				if (frappe.app?.sidebar) {
					callback();
				}
			};
			if (window.jQuery) {
				jQuery(document).one("app_ready", run);
			}
			setTimeout(run, 500);
			setTimeout(run, 1500);
		};
	}

	const SITE_PROJECT_TYPE = "Site";
	const SITE_SIDEBAR_LABEL = "Project";
	const UNIT_SIDEBAR_LABEL = "Unit";
	const SIDEBAR_LABELS = [SITE_SIDEBAR_LABEL, UNIT_SIDEBAR_LABEL];

	let pending_sidebar_label = null;

	function parse_project_type_filter(raw) {
		if (raw === null || raw === undefined || raw === "") {
			return null;
		}

		if (Array.isArray(raw)) {
			if (raw[0] === "!=") {
				return { operator: "!=", value: raw[1] };
			}
			return { operator: "=", value: raw[1] ?? raw[0] };
		}

		try {
			const parsed = JSON.parse(raw);
			if (Array.isArray(parsed)) {
				if (parsed[0] === "!=") {
					return { operator: "!=", value: parsed[1] };
				}
				return { operator: "=", value: parsed[1] ?? parsed[0] };
			}
			return { operator: "=", value: parsed };
		} catch {
			return { operator: "=", value: raw };
		}
	}

	function get_project_type_filter_from_listview() {
		if (!window.cur_list || cur_list.doctype !== "Project") {
			return null;
		}

		for (const filter of cur_list.get_filters_for_args?.() || []) {
			if (filter[1] === "project_type") {
				return { operator: filter[2], value: filter[3] };
			}
		}

		return null;
	}

	function get_project_type_filter() {
		const from_list = get_project_type_filter_from_listview();
		if (from_list) {
			return from_list;
		}

		if (frappe.route_options?.project_type !== undefined) {
			const from_route = parse_project_type_filter(frappe.route_options.project_type);
			if (from_route) {
				return from_route;
			}
		}

		const fromUrl = new URLSearchParams(window.location.search).get("project_type");
		if (fromUrl) {
			return parse_project_type_filter(fromUrl);
		}

		return null;
	}

	function is_project_list_route() {
		const route = frappe.get_route();
		return (
			route[0] === "List" &&
			route[1] === "Project" &&
			window.location.pathname.endsWith("/project/view/list")
		);
	}

	function get_active_sidebar_label(filter) {
		if (pending_sidebar_label && SIDEBAR_LABELS.includes(pending_sidebar_label)) {
			return pending_sidebar_label;
		}

		if (!filter) {
			return null;
		}
		if (filter.operator === "=" && filter.value === SITE_PROJECT_TYPE) {
			return SITE_SIDEBAR_LABEL;
		}
		if (filter.operator === "!=" && filter.value === SITE_PROJECT_TYPE) {
			return UNIT_SIDEBAR_LABEL;
		}
		return null;
	}

	function apply_project_sidebar_highlight(sidebar) {
		if (!is_project_list_route()) {
			pending_sidebar_label = null;
			return false;
		}

		const activeLabel = get_active_sidebar_label(get_project_type_filter());
		if (!activeLabel) {
			return false;
		}

		const sidebarRoot = sidebar?.wrapper || $(".body-sidebar");
		$(".body-sidebar .standard-sidebar-item.active-sidebar").removeClass("active-sidebar");

		SIDEBAR_LABELS.forEach((label) => {
			sidebarRoot
				.find(`.sidebar-item-container[data-id="${label}"] .standard-sidebar-item`)
				.removeClass("active-sidebar");
		});

		const $activeItem = sidebarRoot
			.find(`.sidebar-item-container[data-id="${activeLabel}"] .standard-sidebar-item`)
			.first();
		if (!$activeItem.length) {
			return false;
		}

		$activeItem.addClass("active-sidebar");
		if (sidebar) {
			sidebar.active_item = $activeItem;
		}

		if (!pending_sidebar_label || pending_sidebar_label === activeLabel) {
			pending_sidebar_label = null;
		}

		return true;
	}

	fitzgerald_kitchens.project_sidebar.apply = function () {
		return apply_project_sidebar_highlight(frappe.app?.sidebar);
	};

	function navigate_project_list(label) {
		pending_sidebar_label = label;
		apply_project_sidebar_highlight(frappe.app?.sidebar);

		const route_options =
			label === UNIT_SIDEBAR_LABEL
				? { project_type: ["!=", SITE_PROJECT_TYPE] }
				: { project_type: SITE_PROJECT_TYPE };

		frappe.route_options = route_options;

		const navigate = () => {
			if (window.cur_list?.doctype === "Project" && cur_list.filter_area) {
				const list_filters = [
					[
						"Project",
						"project_type",
						label === UNIT_SIDEBAR_LABEL ? "!=" : "=",
						SITE_PROJECT_TYPE,
					],
				];
				return cur_list.filter_area
					.clear(false)
					.then(() => cur_list.filter_area.set(list_filters))
					.then(() => cur_list.refresh())
					.then(() => schedule_highlight());
			}

			return frappe.set_route("List", "Project").then(() => schedule_highlight());
		};

		navigate();
	}

	function handle_project_sidebar_click(event) {
		const anchor = event.target.closest(
			`.body-sidebar .sidebar-item-container[data-id="${SITE_SIDEBAR_LABEL}"] .item-anchor, .body-sidebar .sidebar-item-container[data-id="${UNIT_SIDEBAR_LABEL}"] .item-anchor`
		);
		if (!anchor || event.ctrlKey || event.metaKey || event.shiftKey || event.button !== 0) {
			return;
		}

		const label = anchor.closest(".sidebar-item-container")?.dataset?.id;
		if (!SIDEBAR_LABELS.includes(label)) {
			return;
		}

		event.preventDefault();
		event.stopPropagation();
		event.stopImmediatePropagation();

		navigate_project_list(label);
		return false;
	}

	function patch_sidebar_prototype() {
		if (!frappe.ui?.Sidebar?.prototype || frappe.ui.Sidebar.prototype._fk_route_patch) {
			return !!frappe.ui?.Sidebar?.prototype;
		}

		const proto = frappe.ui.Sidebar.prototype;
		const original_is_route = proto.is_route_in_sidebar;

		proto.is_route_in_sidebar = function () {
			if (!is_project_list_route()) {
				return original_is_route.call(this);
			}

			const activeLabel = get_active_sidebar_label(get_project_type_filter());
			if (!activeLabel) {
				return original_is_route.call(this);
			}

			const $item = (this.wrapper || $(".body-sidebar"))
				.find(`.sidebar-item-container[data-id="${activeLabel}"] .standard-sidebar-item`)
				.first();

			if (!$item.length) {
				return original_is_route.call(this);
			}

			if (this.active_item) {
				this.active_item.removeClass("active-sidebar");
			}
			this.active_item = $item;
			return true;
		};

		const original_set_active = proto.set_active_workspace_item;
		proto.set_active_workspace_item = function () {
			if (is_project_list_route()) {
				const activeLabel = get_active_sidebar_label(get_project_type_filter());
				if (activeLabel) {
					const $item = (this.wrapper || $(".body-sidebar"))
						.find(
							`.sidebar-item-container[data-id="${activeLabel}"] .standard-sidebar-item`
						)
						.first();
					if ($item.length) {
						if (this.active_item) {
							this.active_item.removeClass("active-sidebar");
						}
						this.active_item = $item;
						this.active_item.addClass("active-sidebar");
						this.expand_parent_section?.();
						return;
					}
				}
			}

			original_set_active.call(this);
			apply_project_sidebar_highlight(this);
		};

		proto._fk_route_patch = true;
		return true;
	}

	function schedule_highlight() {
		fitzgerald_kitchens.project_sidebar.apply();
		[0, 50, 150, 350, 600].forEach((delay) => {
			setTimeout(() => fitzgerald_kitchens.project_sidebar.apply(), delay);
		});
	}

	function init_events() {
		if (window._fk_project_sidebar_init) {
			schedule_highlight();
			return;
		}
		window._fk_project_sidebar_init = true;

		schedule_highlight();
		frappe.router.on("change", schedule_highlight);
		$(document).on("sidebar_setup", schedule_highlight);
		$(document).on("page-change", schedule_highlight);

		frappe.listview_settings["Project"] = frappe.listview_settings["Project"] || {};
		const project_list_onload = frappe.listview_settings["Project"].onload;
		frappe.listview_settings["Project"].onload = function (listview) {
			project_list_onload?.call(this, listview);
			schedule_highlight();
		};

		const project_list_onload_after = frappe.listview_settings["Project"].onload_after;
		frappe.listview_settings["Project"].onload_after = function () {
			project_list_onload_after?.call(this);
			schedule_highlight();
		};

		const project_list_refresh = frappe.listview_settings["Project"].refresh;
		frappe.listview_settings["Project"].refresh = function (listview) {
			const result = project_list_refresh?.call(this, listview);
			schedule_highlight();
			return result;
		};
	}

	function when_desk_ready(callback) {
		if (frappe.app?.sidebar) {
			callback();
			return;
		}

		let done = false;
		const run = () => {
			if (done || !frappe.app?.sidebar) {
				return;
			}
			done = true;
			callback();
		};

		$(document).one("app_ready", run);
		setTimeout(run, 500);
		setTimeout(run, 1500);
	}

	function bootstrap() {
		if (!window.jQuery || !window.frappe) {
			setTimeout(bootstrap, 10);
			return;
		}

		if (!window._fk_project_sidebar_click) {
			document.addEventListener("click", handle_project_sidebar_click, true);
			window._fk_project_sidebar_click = true;
		}

		if (!patch_sidebar_prototype()) {
			setTimeout(bootstrap, 10);
			return;
		}

		when_desk_ready(init_events);
	}

	bootstrap();
})();
