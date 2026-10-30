// CineTrack shell: rail and bottom-nav menus, and the Ctrl/Cmd+K command palette.
// Loaded for every theme (it is small) so a boosted switch to the CineTrack
// theme, which keeps the old <head>, still finds the component.
document.addEventListener("alpine:init", () => {
  // A1: command palette. Arrow keys move the highlighted option, Enter
  // follows it; with nothing highlighted Enter runs the online search.
  Alpine.data("ctPalette", () => ({
    open: false,
    active: -1,
    activeId: null,
    returnFocus: null,
    options() {
      return Array.from(this.$root.querySelectorAll("[role=option]"));
    },
    show() {
      this.returnFocus = document.activeElement;
      this.open = true;
      this.$refs.input.value = "";
      this.$nextTick(() => {
        this.$refs.input.focus();
        htmx.trigger(this.$refs.input, "ct-palette-refresh");
      });
    },
    close() {
      this.open = false;
      if (this.returnFocus && this.returnFocus.focus) this.returnFocus.focus();
    },
    reset() {
      this.select(this.$refs.input.value.trim() && this.options().length ? 0 : -1);
    },
    select(index) {
      const options = this.options();
      options.forEach((option, i) => option.setAttribute("aria-selected", i === index ? "true" : "false"));
      this.active = index;
      this.activeId = index >= 0 && options[index] ? options[index].id : null;
      if (this.activeId) options[index].scrollIntoView({ block: "nearest" });
    },
    move(step) {
      const count = this.options().length;
      if (!count) return;
      this.select((this.active + step + count) % count);
    },
    hover(event) {
      const option = event.target instanceof Element ? event.target.closest("[role=option]") : null;
      const index = option ? this.options().indexOf(option) : -1;
      if (index >= 0 && index !== this.active) this.select(index);
    },
    go() {
      const options = this.options();
      const target = options[this.active] || options.find((option) => option.classList.contains("ct-palette-online"));
      if (target) target.click();
    },
  }));

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

  // Discover hero (W4): scroll-snap slides with dots and arrows. Autoplay
  // advances every 7 s while the tab is visible and the hero has neither the
  // pointer nor focus; never under reduced motion.
  Alpine.data("ctHero", (count) => ({
    index: 0,
    paused: false,
    timer: null,
    init() {
      this.$root.addEventListener("pointerenter", () => { this.paused = true; });
      this.$root.addEventListener("pointerleave", () => { this.paused = false; });
      this.$root.addEventListener("focusin", () => { this.paused = true; });
      this.$root.addEventListener("focusout", () => { this.paused = false; });
      if (count > 1 && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        this.timer = setInterval(() => {
          if (!this.paused && document.visibilityState === "visible") this.go(this.index + 1);
        }, 7000);
      }
    },
    destroy() {
      clearInterval(this.timer);
    },
    slides() {
      return Array.from(this.$refs.track.children);
    },
    go(next) {
      const slides = this.slides();
      if (!slides.length) return;
      this.index = (next + slides.length) % slides.length;
      this.$refs.track.scrollTo({ left: slides[this.index].offsetLeft - slides[0].offsetLeft, behavior: "smooth" });
    },
    sync() {
      const slides = this.slides();
      const left = this.$refs.track.scrollLeft;
      let nearest = 0;
      slides.forEach((slide, i) => {
        const offset = slide.offsetLeft - slides[0].offsetLeft;
        if (Math.abs(offset - left) < Math.abs(slides[nearest].offsetLeft - slides[0].offsetLeft - left)) nearest = i;
      });
      this.index = nearest;
    },
  }));
});

// Bind once: kept in <head>, which boosted navigation leaves in place.
if (!window.__floppyCtShellBound) {
  window.__floppyCtShellBound = true;
  document.addEventListener("keydown", (event) => {
    if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "k") return;
    if (!document.querySelector("[data-ct-shell]")) return;
    if (document.querySelector(".ct-palette")) {
      event.preventDefault();
      window.dispatchEvent(new CustomEvent("ct-palette-open"));
      return;
    }
    const searchInput = document.getElementById("global-search");
    if (!searchInput) return;
    event.preventDefault();
    searchInput.focus();
    searchInput.select();
  });

  // M3: the poster a detail link was clicked from morphs into the detail
  // page's poster in the cross-document view transition (CineTrack's
  // sharedPoster). A name must be unique on the page, so the previous one
  // is cleared first, and a detail page (whose own poster holds the name)
  // names nothing.
  document.addEventListener("click", (event) => {
    if (!document.querySelector("[data-ct-shell]") || document.querySelector(".ct-detail-hero")) return;
    const link = event.target instanceof Element ? event.target.closest("a[href*='/details/']") : null;
    const card = link?.closest(".media-card, .ct-poster-card, .ct-progress-card, .ct-discover-hero__slide");
    if (!card) return;
    const img = card.querySelector(".ct-progress-poster img, .ct-discover-hero__poster")
      || card.querySelector("img:not(.ct-accent-probe)");
    if (!img) return;
    document.querySelectorAll("[data-ct-shared-poster]").forEach((named) => {
      named.style.viewTransitionName = "";
      named.removeAttribute("data-ct-shared-poster");
    });
    img.style.viewTransitionName = "ct-poster";
    img.setAttribute("data-ct-shared-poster", "");
  }, true);
}

// Home cards (W2). The check's end date is the browser's local time at the
// click, formatted as the date picker's "now" (date only without TRACK_TIME),
// so the watch keeps the exact time as "Add watch" would.
window.ctWatchNow = function ctWatchNow(trackTime) {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  if (!trackTime) return date;
  return `${date}T${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
};

if (!window.__floppyCtCardsBound) {
  window.__floppyCtCardsBound = true;

  // M7: posters fade in once decoded. Images that finished before this ran
  // are shown at once; load and error both reveal (error shows the alt).
  const reveal = (img) => img.classList.add("is-loaded");
  const revealComplete = (root) => {
    root.querySelectorAll(".ct-fade-img:not(.is-loaded)").forEach((img) => {
      if (img.complete) reveal(img);
    });
  };
  const onImageSettled = (event) => {
    if (event.target instanceof HTMLImageElement && event.target.classList.contains("ct-fade-img")) {
      reveal(event.target);
    }
  };
  document.addEventListener("load", onImageSettled, true);
  document.addEventListener("error", onImageSettled, true);
  revealComplete(document);
  document.addEventListener("htmx:afterSwap", (event) => {
    revealComplete(event.target instanceof Element ? event.target : document);
  });

  // M5: the check fills green and the progress line grows by one episode.
  // The button stays done, so a second tap can't log the episode twice; the
  // card shows the next episode on the next Home load.
  document.addEventListener("htmx:afterRequest", (event) => {
    const form = event.detail.elt;
    if (!(form instanceof HTMLFormElement) || !form.hasAttribute("data-ct-check")) return;
    const button = form.querySelector("button");
    if (!event.detail.successful) {
      window.showTrackToast?.({
        message: window.gettext ? gettext("Couldn't mark it watched.") : "Couldn't mark it watched.",
        type: "error",
      });
      return;
    }
    const card = form.closest(".ct-progress-card");
    button.classList.add("is-done");
    button.disabled = true;
    button.setAttribute("aria-label", window.gettext ? gettext("Watched") : "Watched");
    if (card) {
      const style = getComputedStyle(card);
      const progress = Number.parseFloat(style.getPropertyValue("--ct-progress")) || 0;
      const step = Number.parseFloat(style.getPropertyValue("--ct-progress-step")) || 0;
      card.style.setProperty("--ct-progress", `${Math.min(100, progress + step)}%`);
      card.classList.add("is-watched");
    }
  });
}
