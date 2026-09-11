frappe.provide("fitzgerald_kitchens.offline_route_guard");

(function () {
	// Only these Desk routes are offline-capable. Everything else needs network
	// (Task DocType, Project, Stock, reports, etc. — see OFFLINE_APPROACH.md rule 1).
	const OFFLINE_SAFE_ROUTES = ["my-tasks", "task-scan"];

	function is_offline_safe_route(route) {
		if (!route || !route.length) {
			return true;
		}
		return OFFLINE_SAFE_ROUTES.includes(route[0]);
	}

	function warn_offline_blocked() {
		frappe.show_alert({
			message: __("You're offline — only My Tasks works offline. Reconnect to open this page."),
			indicator: "orange",
		});
	}

	function get_route_from_anchor(anchor) {
		const href = anchor.getAttribute("href") || "";
		if (!href || href.startsWith("#") || href.startsWith("http")) {
			return null;
		}
		const clean = href.replace(/^\/app\//, "").replace(/^\//, "");
		if (!clean) {
			return null;
		}
		return clean.split("/");
	}

	function handle_sidebar_click(event) {
		if (navigator.onLine) {
			return;
		}
		const anchor = event.target.closest(".body-sidebar .item-anchor, .body-sidebar a[href]");
		if (!anchor) {
			return;
		}
		const route = get_route_from_anchor(anchor);
		if (is_offline_safe_route(route)) {
			return;
		}
		event.preventDefault();
		event.stopPropagation();
		event.stopImmediatePropagation();
		warn_offline_blocked();
		return false;
	}

	function bootstrap() {
		if (!window.jQuery || !window.frappe || !frappe.router) {
			setTimeout(bootstrap, 50);
			return;
		}
		if (window._fk_offline_route_guard_init) {
			return;
		}
		window._fk_offline_route_guard_init = true;

		document.addEventListener("click", handle_sidebar_click, true);

		// Safety net: if a route change slips through anyway while offline
		// (e.g. programmatic frappe.set_route), bounce back to My Tasks.
		frappe.router.on("change", function () {
			if (navigator.onLine) {
				return;
			}
			const route = frappe.get_route();
			if (is_offline_safe_route(route)) {
				return;
			}
			warn_offline_blocked();
			frappe.set_route("my-tasks");
		});
	}

	bootstrap();
})();
