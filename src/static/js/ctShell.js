// CineTrack shell: rail and bottom-nav menus, and Ctrl/Cmd+K to search.
// Loaded for every theme (it is small) so a boosted switch to the CineTrack
// theme, which keeps the old <head>, still finds the component.
document.addEventListener("alpine:init", () => {
  // Disclosure menu: a button plus a panel of links. Opening moves focus to
  // the first item; Escape closes and returns focus; tabbing out closes.
  Alpine.data("ctMenu", () => ({
    open: false,
    toggle() {
      if (this.open) {
        this.close();
        return;
      }
      this.open = true;
      this.$nextTick(() => {
        const first = this.$refs.panel.querySelector("a, button");
        if (first) first.focus();
      });
    },
    close(returnFocus = true) {
      if (!this.open) return;
      this.open = false;
      if (returnFocus) this.$refs.toggle.focus();
    },
    onFocusOut(event) {
      if (!this.$root.contains(event.relatedTarget)) this.open = false;
    },
  }));
});

// Bind once: kept in <head>, which boosted navigation leaves in place.
if (!window.__floppyCtShellBound) {
  window.__floppyCtShellBound = true;
  document.addEventListener("keydown", (event) => {
    if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "k") return;
    if (!document.querySelector("[data-ct-shell]")) return;
    const searchInput = document.getElementById("global-search");
    if (!searchInput) return;
    event.preventDefault();
    searchInput.focus();
    searchInput.select();
  });
}
