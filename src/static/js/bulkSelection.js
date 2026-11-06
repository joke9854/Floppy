// Bind once: this script is re-evaluated on boosted (hx:boost) navigation.
if (!window.__floppyBulkSelectionBound) {
  window.__floppyBulkSelectionBound = true;
  document.addEventListener("alpine:init", () => {
    // Media card state. Shared here rather than inlined on each card: the
    // inline copy was ~1 KB of every Library card (32 per page).
    Alpine.data("mediaCard", (bulkSelect = false) => ({
      trackOpen: false,
      listsOpen: false,
      revealed: false,
      tapToReveal(e) {
        if (this.revealed) {
          if (e.target.closest("button, a, input, select, textarea")) return;
          const link =
            this.$root.querySelector(".media-card-overlay a[href]") ||
            this.$root.querySelector("a.media-card-title[href]");
          if (link) {
            e.preventDefault();
            e.stopPropagation();
            link.click();
          }
          return;
        }
        if (
          !window.matchMedia("(pointer: coarse)").matches ||
          this.$root.classList.contains("media-card-hide-overlay") ||
          !this.$root.querySelector(".media-card-overlay") ||
          (bulkSelect && this.selectMode)
        ) {
          return;
        }
        e.preventDefault();
        e.stopPropagation();
        this.revealed = true;
        window.dispatchEvent(new CustomEvent("media-card-revealed", { detail: this.$root }));
      },
    }));

    Alpine.data("bulkSelection", (configId, refreshId) => ({
      selectMode: false,
      selectedItemIds: [],
      bulkLoading: false,
      bulkStatuses: [],
      bulkTags: [],
      bulkLists: [],
      config: {},

      init() {
        const configElement = document.getElementById(configId);
        if (configElement) {
          try {
            this.config = JSON.parse(configElement.textContent || "{}");
          } catch (error) {
            console.error("Failed to load bulk-action configuration", error);
          }
        }
        this.bulkStatuses = this.config.statuses || [];
        this.bulkTags = this.config.tags || [];
        this.bulkLists = this.config.lists || [];
      },

      toggleSelectMode() {
        this.selectMode = !this.selectMode;
        if (!this.selectMode) {
          this.selectedItemIds = [];
        }
      },

      isItemSelected(id) {
        return this.selectedItemIds.includes(String(id));
      },

      toggleItemSelected(id) {
        const key = String(id);
        if (this.selectedItemIds.includes(key)) {
          this.selectedItemIds = this.selectedItemIds.filter((item) => item !== key);
        } else {
          this.selectedItemIds = [...this.selectedItemIds, key];
        }
      },

      clearSelection() {
        this.selectedItemIds = [];
      },

      notify(message, type = "success") {
        if (message && typeof window.showTrackToast === "function") {
          window.showTrackToast({ message, type });
        }
      },

      refresh() {
        const refreshButton = document.getElementById(refreshId);
        if (refreshButton && window.htmx) {
          htmx.trigger(refreshButton, "click");
        }
      },

      async submitBulkAction(url, fields) {
        if (!this.selectedItemIds.length || this.bulkLoading || !url) {
          return;
        }

        this.bulkLoading = true;
        const body = new URLSearchParams();
        this.selectedItemIds.forEach((id) => body.append("item_ids", id));
        Object.entries(fields || {}).forEach(([key, value]) => body.append(key, value));

        try {
          const response = await fetch(url, {
            method: "POST",
            headers: { "X-CSRFToken": this.config.csrfToken },
            body,
          });
          let data = {};
          try {
            data = await response.json();
          } catch (error) {
            // The status code below still determines whether the request failed.
          }
          if (!response.ok || data.success === false) {
            throw new Error(data.error || gettext("The bulk action failed."));
          }
          this.notify(data.message || gettext("Bulk action completed."));
          this.toggleSelectMode();
          this.refresh();
        } catch (error) {
          this.notify(error.message || gettext("The bulk action failed."), "error");
        } finally {
          this.bulkLoading = false;
        }
      },

      bulkTagAction(tagName, action) {
        return this.submitBulkAction(this.config.tagUrl, {
          tag_name: tagName,
          action,
        });
      },

      bulkStatusAction(status) {
        return this.submitBulkAction(this.config.statusUrl, { status });
      },

      bulkListAction(customListId) {
        return this.submitBulkAction(this.config.listUrl, {
          custom_list_id: customListId,
        });
      },

      bulkCollectionAction() {
        return this.submitBulkAction(this.config.collectionUrl, {});
      },
    }));
  });
}
