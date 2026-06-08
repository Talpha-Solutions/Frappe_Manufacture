(function () {
	const STORAGE_PROJECT = "fk_tracker_focused_project";
	const STORAGE_SEARCH = "fk_tracker_focused_search";
	const TRACKER_PATH = "/project";

	function normalizePath(pathname) {
		if (!pathname) {
			return "";
		}
		const trimmed = pathname.replace(/\/+$/, "");
		return trimmed || "/";
	}

	function isTrackerPath(pathname) {
		return normalizePath(pathname) === TRACKER_PATH;
	}

	function readStorage(key) {
		try {
			return sessionStorage.getItem(key);
		} catch (error) {
			return null;
		}
	}

	function writeStorage(key, value) {
		try {
			sessionStorage.setItem(key, value);
		} catch (error) {
			/* ignore quota / privacy mode */
		}
	}

	function removeStorage(key) {
		try {
			sessionStorage.removeItem(key);
		} catch (error) {
			/* ignore */
		}
	}

	window.fkTrackerState = {
		STORAGE_PROJECT: STORAGE_PROJECT,
		STORAGE_SEARCH: STORAGE_SEARCH,
		TRACKER_PATH: TRACKER_PATH,

		getFocusedProject() {
			return readStorage(STORAGE_PROJECT);
		},

		getFocusedSearch() {
			return readStorage(STORAGE_SEARCH) || "";
		},

		saveFocusedProject(projectId, searchText) {
			if (!projectId) {
				return;
			}
			writeStorage(STORAGE_PROJECT, projectId);
			if (searchText) {
				writeStorage(STORAGE_SEARCH, searchText);
			}
		},

		clearFocusedProject() {
			removeStorage(STORAGE_PROJECT);
			removeStorage(STORAGE_SEARCH);
		},

		buildTrackerUrl(projectId) {
			const url = new URL(TRACKER_PATH, window.location.origin);
			if (projectId) {
				url.searchParams.set("project", projectId);
			}
			return url.pathname + url.search;
		},

		forEachTrackerSidebarLink(callback) {
			document.querySelectorAll("a[href]").forEach(function (link) {
				let linkUrl;
				try {
					linkUrl = new URL(link.getAttribute("href"), window.location.origin);
				} catch (error) {
					return;
				}

				if (!isTrackerPath(linkUrl.pathname)) {
					return;
				}

				callback(link, linkUrl);
			});
		},

		syncSidebarLinks() {
			const projectId = this.getFocusedProject();
			if (!projectId) {
				return;
			}

			const trackerUrl = this.buildTrackerUrl(projectId);
			this.forEachTrackerSidebarLink(function (link, linkUrl) {
				if (!linkUrl.searchParams.get("project")) {
					link.setAttribute("href", trackerUrl);
				}
			});
		},

		resetSidebarLinks() {
			this.forEachTrackerSidebarLink(function (link, linkUrl) {
				if (linkUrl.searchParams.has("project")) {
					link.setAttribute("href", TRACKER_PATH);
				}
			});
		},

		resolveStoredSearch(projectId, cards) {
			const storedSearch = this.getFocusedSearch();
			if (storedSearch) {
				return storedSearch;
			}

			if (!cards || !cards.length) {
				return projectId || "";
			}

			for (let index = 0; index < cards.length; index += 1) {
				const card = cards[index];
				if (card.getAttribute("data-project-id") === projectId) {
					return (
						card.getAttribute("data-project-label") ||
						card.getAttribute("data-search") ||
						projectId
					);
				}
			}

			return projectId || "";
		},

		restoreTrackerPage(options) {
			const cards = options.cards || [];
			const searchInput = options.searchInput;
			const pills = options.pills || [];
			const urlParams = new URLSearchParams(window.location.search);
			const urlProject = urlParams.get("project");
			let focusedProject = options.serverFocusedProject || urlProject || null;

			if (urlProject) {
				focusedProject = urlProject;
			} else {
				const storedProject = this.getFocusedProject();
				if (storedProject) {
					focusedProject = storedProject;
				}
			}

			if (!focusedProject) {
				return {
					focusedProject: null,
					searchValue: (searchInput && searchInput.value) || "",
				};
			}

			let searchValue = (searchInput && searchInput.value) || "";
			if (!searchValue) {
				searchValue = this.resolveStoredSearch(focusedProject, cards);
			}
			if (!searchValue && options.serverInitialSearch) {
				searchValue = options.serverInitialSearch;
			}

			if (searchInput) {
				searchInput.value = searchValue;
			}

			pills.forEach(function (pill) {
				pill.classList.remove("active");
			});

			const url = new URL(window.location.href);
			if (url.searchParams.get("project") !== focusedProject) {
				url.searchParams.set("project", focusedProject);
				window.history.replaceState({}, "", url.pathname + url.search);
			}

			this.saveFocusedProject(focusedProject, searchValue);

			return {
				focusedProject: focusedProject,
				searchValue: searchValue,
			};
		},
	};

	document.addEventListener("DOMContentLoaded", function () {
		window.fkTrackerState.syncSidebarLinks();
	});
})();
