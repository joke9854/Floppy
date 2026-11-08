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
  // The sidebar's search hint names the platform's palette shortcut.
  const labelShortcut = () => {
    if (!/Mac|iPhone|iPad/.test(navigator.platform)) return;
    document.querySelectorAll("[data-ct-shortcut-label]").forEach((el) => {
      el.textContent = "⌘K";
    });
  };
  document.addEventListener("DOMContentLoaded", labelShortcut);
  document.addEventListener("htmx:afterSettle", labelShortcut);
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

  // A5: detail-page shortcuts. W marks the first unwatched episode on the
  // page (as the Home check does), S opens tracking, R the rating, and ?
  // lists them. Ignored while typing, with modifiers, or with a dialog open.
  const isTyping = (el) => el instanceof Element
    && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));
  const dialogOpen = () => [...document.querySelectorAll(".fixed.inset-0, .ct-palette")]
    .some((el) => el.checkVisibility());
  // The episode W and the hero button mark: the show's next episode when the
  // server named one on the button, else the first unwatched one listed.
  const episodeCheck = (season, episode) => document.querySelector(
    `[data-ct-episode-check][data-season-number="${season}"][data-episode-number="${episode}"]`,
  );
  const nextEpisode = () => {
    const pinned = document.querySelector("[data-ct-mark-next][data-episode-number]");
    if (pinned) {
      // Marked and waiting for the page to name the next one (refreshLiveParts).
      const row = episodeCheck(pinned.dataset.seasonNumber, pinned.dataset.episodeNumber);
      if (pinned.dataset.pending || (row && row.dataset.watched !== "0")) return null;
      return { data: pinned.dataset, row };
    }
    const row = document.querySelector("[data-ct-episode-check][data-watched='0']");
    return row ? { data: row.dataset, row } : null;
  };
  const markNextEpisode = (help) => {
    const next = nextEpisode();
    if (!next) {
      document.dispatchEvent(new CustomEvent("showToast", {
        detail: { message: help.dataset.noneLeft, type: "info" },
      }));
      return false;
    }
    const { data, row } = next;
    const values = {
      media_id: data.mediaId,
      season_number: data.seasonNumber,
      episode_number: data.episodeNumber,
      source: data.source,
      end_date: window.ctWatchNow(help.dataset.trackTime === "true"),
    };
    if (data.libraryMediaType) values.library_media_type = data.libraryMediaType;
    if (window.crypto && crypto.randomUUID) values.watch_operation_id = crypto.randomUUID();
    const pinned = document.querySelector("[data-ct-mark-next][data-episode-number]");
    if (row) row.dataset.watched = "pending";
    if (pinned) pinned.dataset.pending = "1";
    const url = `${help.dataset.episodeSaveUrl}?next=${encodeURIComponent(location.pathname)}`;
    // The body as source, so the button's own hx-vals (instance_id) are not sent.
    htmx.ajax("POST", url, { values, swap: "none", source: document.body }).catch(() => {
      if (row) row.dataset.watched = "0";
      if (pinned) delete pinned.dataset.pending;
      const button = document.querySelector("[data-ct-mark-next]");
      if (button) {
        delete button.dataset.watchedAt;
        button.classList.remove("is-watched");
      }
      syncMarkNext();
    });
    return true;
  };
  // v2 detail: the primary button marks the same episode W would and names
  // it, and that episode's row reads "Up next". Just marked, it reads a green
  // "Watched" until the live refresh names the next one; a completed show with
  // none left keeps it green. Hidden otherwise.
  const syncMarkNext = () => {
    const button = document.querySelector("[data-ct-mark-next]");
    if (!button) return;
    const label = button.querySelector("[data-ct-mark-next-label]");
    if (button.dataset.watchedAt) {
      button.hidden = false;
      label.textContent = button.dataset.watchedLabel;
      return;
    }
    const next = nextEpisode();
    const done = !next && "ctCompleted" in button.dataset;
    button.hidden = !next && !done;
    button.classList.toggle("is-watched", done);
    button.closest(".ct-detail-actions")?.classList.toggle("has-primary", Boolean(next) || done);
    document.querySelectorAll(".ct-episode-list .ct-ep-row").forEach((row) => {
      row.classList.toggle("is-next", Boolean(next?.row) && row.contains(next.row));
    });
    if (done) label.textContent = button.dataset.watchedLabel;
    if (!next) return;
    label.textContent = button.dataset.label
      .replace("%(season)s", next.data.seasonNumber)
      .replace("%(episode)s", next.data.episodeNumber);
  };
  // W and the hero button: mark, and show the button's green "Watched".
  const markFromHero = (help) => {
    const button = document.querySelector("[data-ct-mark-next]");
    if (!markNextEpisode(help) || !button) return;
    button.dataset.watchedAt = String(Date.now());
    button.classList.add("is-watched");
    syncMarkNext();
  };
  const openTrack = () => document.querySelector('.ct-detail-hero [data-ct-shortcut="track"]')?.click();
  document.addEventListener("DOMContentLoaded", syncMarkNext);
  document.addEventListener("htmx:afterSettle", syncMarkNext);
  // After a watch is saved, edited or undone, re-fetch this page and swap in
  // its [data-ct-live] parts (the hero button, progress card and counts), so
  // they read the server's numbers rather than the ones on first paint.
  let refreshTimer;
  const refreshLiveParts = () => {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(async () => {
      // A part loaded from another URL (a season's fragment on a show page)
      // names it in data-ct-live-src; the rest come from this page.
      const sources = new Map();
      document.querySelectorAll("[data-ct-live][id]").forEach((el) => {
        const src = el.dataset.ctLiveSrc || location.href;
        if (!sources.has(src)) sources.set(src, []);
        sources.get(src).push(el);
      });
      await Promise.all([...sources].map(async ([src, parts]) => {
        const response = await fetch(src, { credentials: "same-origin" }).catch(() => null);
        if (!response?.ok) return;
        const fresh = new DOMParser().parseFromString(await response.text(), "text/html");
        parts.forEach((el) => {
          const replacement = fresh.getElementById(el.id);
          if (!replacement) return;
          const swap = () => {
            if (!el.isConnected) return;
            const node = document.importNode(replacement, true);
            el.replaceWith(node);
            htmx.process(node);
            syncMarkNext();
          };
          // A just-marked hero button holds its green "Watched" for a beat.
          const wait = el.dataset.watchedAt ? 1200 - (Date.now() - Number(el.dataset.watchedAt)) : 0;
          if (wait > 0) setTimeout(swap, wait);
          else swap();
        });
      }));
      syncMarkNext();
    }, 150);
  };
  document.addEventListener("htmx:afterRequest", (event) => {
    const config = event.detail.requestConfig;
    if (!event.detail.successful || config?.verb !== "post") return;
    if (document.querySelector("[data-ct-live]")) refreshLiveParts();
  });
  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) return;
    if (event.target.closest("[data-ct-open-track]")) {
      openTrack();
      return;
    }
    const button = event.target.closest("[data-ct-mark-next]");
    const help = document.querySelector("[data-ct-shortcuts]");
    if (!button || !help) return;
    if (button.classList.contains("is-watched")) {
      if (!button.dataset.watchedAt) openTrack();
      return;
    }
    markFromHero(help);
  });
  document.addEventListener("keydown", (event) => {
    if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return;
    if (isTyping(event.target) || !document.querySelector("[data-ct-shell] .ct-detail-hero")) return;
    const help = document.querySelector("[data-ct-shortcuts]");
    if (!help || dialogOpen()) return;
    const key = event.key.toLowerCase();
    if (key === "?") {
      event.preventDefault();
      window.dispatchEvent(new CustomEvent("ct-shortcuts-open"));
    } else if (key === "w") {
      event.preventDefault();
      markFromHero(help);
    } else if (key === "s" || key === "r") {
      const target = document.querySelector(
        `.ct-detail-hero [data-ct-shortcut="${key === "s" ? "track" : "rate"}"]`,
      );
      if (!target) return;
      event.preventDefault();
      target.click();
    }
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

  // Re-render one Home card from its row's own load_row fragment, so it names
  // the next episode, its count and a live check. The undo stays attached.
  const refreshHomeCard = async (form) => {
    const slot = form.closest("[data-ct-card-key]");
    const rowUrl = slot?.closest("[data-row-id][hx-get]")?.getAttribute("hx-get");
    if (!rowUrl) return;
    const response = await fetch(`${rowUrl}&offset=0`, {
      credentials: "same-origin",
      headers: { "HX-Request": "true" },
    }).catch(() => null);
    if (!response?.ok || !slot.isConnected) return;
    const fresh = new DOMParser().parseFromString(await response.text(), "text/html")
      .querySelector(`[data-ct-card-key="${slot.dataset.ctCardKey}"]`);
    if (!fresh) return;
    const node = document.importNode(fresh, true);
    const instanceId = form.dataset.ctWatchedInstance;
    const freshForm = node.querySelector("form[data-ct-check]");
    if (instanceId && freshForm) freshForm.dataset.ctWatchedInstance = instanceId;
    slot.replaceWith(node);
    htmx.process(node);
    revealComplete(node);
  };

  // M5: the check fills green and the progress line grows by one episode,
  // then the card re-renders with the next one. The button stays done until
  // then, so a second tap can't log the episode twice.
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
    // Remember the play and the card's state so the toast's Undo can reset it.
    try {
      const trigger = JSON.parse(event.detail.xhr.getResponseHeader("HX-Trigger") || "{}");
      const instanceId = trigger.showToast?.undo?.instanceId;
      if (instanceId) form.dataset.ctWatchedInstance = String(instanceId);
    } catch {
      // No undo for this check.
    }
    button.dataset.ctLabel = button.getAttribute("aria-label") || "";
    button.classList.add("is-done");
    button.disabled = true;
    button.setAttribute("aria-label", window.gettext ? gettext("Watched") : "Watched");
    if (card) {
      const style = getComputedStyle(card);
      const progress = Number.parseFloat(style.getPropertyValue("--ct-progress")) || 0;
      const step = Number.parseFloat(style.getPropertyValue("--ct-progress-step")) || 0;
      card.dataset.ctProgressBefore = card.style.getPropertyValue("--ct-progress");
      card.style.setProperty("--ct-progress", `${Math.min(100, progress + step)}%`);
      card.classList.add("is-watched");
    }
    setTimeout(() => refreshHomeCard(form), 900);
  });

  document.addEventListener("ctWatchUndone", (event) => {
    const form = document.querySelector(
      `form[data-ct-check][data-ct-watched-instance="${event.detail.instanceId}"]`,
    );
    if (!form) return;
    delete form.dataset.ctWatchedInstance;
    const button = form.querySelector("button");
    button.classList.remove("is-done");
    button.disabled = false;
    button.setAttribute("aria-label", button.dataset.ctLabel || "");
    const card = form.closest(".ct-progress-card");
    if (card) {
      card.style.setProperty("--ct-progress", card.dataset.ctProgressBefore || "");
      card.classList.remove("is-watched");
    }
    // A new check is a new play, not a resend of the undone one.
    const operation = form.querySelector('[name="watch_operation_id"]');
    if (operation && window.crypto?.randomUUID) operation.value = crypto.randomUUID();
    refreshHomeCard(form);
  });
}
