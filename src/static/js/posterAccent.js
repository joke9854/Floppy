// Poster accent, as CineTrack's rememberPosterAccent: the poster's dominant
// vivid hue becomes --poster-accent (and --poster-accent-text, lifted 32%
// towards white) on the nearest [data-poster-accent-scope], or on the image's
// parent. Mark the poster <img data-poster-accent crossorigin="anonymous">.
// Results are cached per poster URL; a poster that can't be read (no CORS,
// greyscale art) sets nothing, so CSS falls back to var(--color-accent).
if (!window.__floppyPosterAccentBound) {
  window.__floppyPosterAccentBound = true;

  const CACHE_PREFIX = "floppy:poster-accent:v1:";
  const NONE = "none";

  function readCache(src) {
    try {
      return window.localStorage.getItem(CACHE_PREFIX + src);
    } catch (error) {
      return null;
    }
  }

  function writeCache(src, value) {
    try {
      window.localStorage.setItem(CACHE_PREFIX + src, value);
    } catch (error) {
      // Private mode or full storage: the colour is just recomputed.
    }
  }

  function rgbToHsv(r, g, b) {
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const delta = max - min;
    let hue = 0;
    if (delta) {
      if (max === r) {
        hue = ((g - b) / delta) % 6;
      } else if (max === g) {
        hue = (b - r) / delta + 2;
      } else {
        hue = (r - g) / delta + 4;
      }
      hue = (hue * 60 + 360) % 360;
    }
    return [hue, max ? delta / max : 0, max / 255];
  }

  function hsvToRgb(h, s, v) {
    const c = v * s;
    const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
    const m = v - c;
    const [r, g, b] = h < 60 ? [c, x, 0]
      : h < 120 ? [x, c, 0]
        : h < 180 ? [0, c, x]
          : h < 240 ? [0, x, c]
            : h < 300 ? [x, 0, c]
              : [c, 0, x];
    return [r + m, g + m, b + m].map((value) => Math.round(value * 255));
  }

  // Twelve 30-degree hue bands weighted by saturation squared times value;
  // near-black, near-white and grey pixels are ignored; the heaviest band wins.
  function sampleAccent(img) {
    const canvas = document.createElement("canvas");
    canvas.width = 48;
    canvas.height = 72;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    context.drawImage(img, 0, 0, canvas.width, canvas.height);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    const weights = new Array(12).fill(0);
    const sums = Array.from({ length: 12 }, () => [0, 0]);
    let counted = 0;
    for (let index = 0; index < pixels.length; index += 4) {
      const [hue, saturation, value] = rgbToHsv(pixels[index], pixels[index + 1], pixels[index + 2]);
      counted += 1;
      if (saturation < 0.1 || value < 0.15 || value > 0.97) {
        continue;
      }
      const band = Math.min(11, Math.floor(hue / 30));
      const weight = saturation * saturation * value;
      weights[band] += weight;
      sums[band][0] += saturation * weight;
      sums[band][1] += hue * weight;
    }
    const best = weights.indexOf(Math.max(...weights));
    if (!counted || weights[best] / counted < 0.004) {
      return null;
    }
    const saturation = Math.min(0.75, Math.max(0.45, sums[best][0] / weights[best]));
    return hsvToRgb(sums[best][1] / weights[best], saturation, 0.82);
  }

  function apply(img, value) {
    if (!value || value === NONE) {
      return;
    }
    const scope = img.closest("[data-poster-accent-scope]") || img.parentElement;
    const rgb = value.split(",").map(Number);
    const lifted = rgb.map((channel) => Math.round(channel + (255 - channel) * 0.32));
    scope.style.setProperty("--poster-accent", `rgb(${rgb.join(" ")})`);
    scope.style.setProperty("--poster-accent-text", `rgb(${lifted.join(" ")})`);
  }

  function resolve(img) {
    const src = img.currentSrc || img.src;
    if (!src || img.dataset.posterAccentDone === src) {
      return;
    }
    const cached = readCache(src);
    if (cached) {
      img.dataset.posterAccentDone = src;
      apply(img, cached);
      return;
    }
    if (!img.complete || !img.naturalWidth) {
      img.addEventListener("load", () => resolve(img), { once: true });
      return;
    }
    img.dataset.posterAccentDone = src;
    let value;
    try {
      const rgb = sampleAccent(img);
      value = rgb ? rgb.join(",") : NONE;
    } catch (error) {
      // A tainted canvas (no CORS from the image host): keep the app accent,
      // uncached, so a CORS-enabled load of the same URL can still sample it.
      return;
    }
    writeCache(src, value);
    apply(img, value);
  }

  function resolveAll(root) {
    (root || document).querySelectorAll("img[data-poster-accent]").forEach(resolve);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => resolveAll(document));
  } else {
    resolveAll(document);
  }
  document.addEventListener("htmx:afterSwap", (event) => {
    resolveAll(event.target instanceof Element ? event.target : document);
  });
}
