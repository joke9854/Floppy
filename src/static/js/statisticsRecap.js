// A7: draw the monthly recap card on a canvas and save it as a PNG.
// Text only: TMDB posters are not drawn because that would need CORS
// (crossorigin) on images we keep plain. Loaded again on boosted swaps,
// so the listener is bound once.
(function () {
  if (window.floppyRecapBound) return;
  window.floppyRecapBound = true;

  const WIDTH = 1080;
  const HEIGHT = 1350;
  const PAD = 88;

  function fit(ctx, text, maxWidth) {
    if (ctx.measureText(text).width <= maxWidth) return text;
    let end = text.length;
    while (end > 0 && ctx.measureText(text.slice(0, end) + "…").width > maxWidth) end--;
    return text.slice(0, end) + "…";
  }

  function draw(recap, card) {
    // Read resolved colours from the rendered card, so every theme matches.
    const style = getComputedStyle(card);
    const color = (selector) => getComputedStyle(card.querySelector(selector)).color;
    const text = color(".ct-recap-total");
    const muted = color(".ct-recap-caption");
    const accent = color(".ct-recap-eyebrow");
    const font = getComputedStyle(document.body).fontFamily;

    const canvas = document.createElement("canvas");
    canvas.width = WIDTH;
    canvas.height = HEIGHT;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = style.backgroundColor || "#1e1f26";
    ctx.fillRect(0, 0, WIDTH, HEIGHT);
    ctx.textBaseline = "alphabetic";

    let y = PAD + 30;
    ctx.fillStyle = accent;
    ctx.font = `600 34px ${font}`;
    ctx.fillText(`${gettext("Monthly recap")} · ${recap.month_label}`.toUpperCase(), PAD, y);

    y += 150;
    ctx.fillStyle = text;
    ctx.font = `700 128px ${font}`;
    ctx.fillText(fit(ctx, recap.total_time, WIDTH - PAD * 2), PAD, y);
    y += 60;
    ctx.fillStyle = muted;
    ctx.font = `400 38px ${font}`;
    ctx.fillText(gettext("watched and played"), PAD, y);

    if (recap.plays.length) {
      y += 110;
      let x = PAD;
      recap.plays.forEach((play) => {
        ctx.fillStyle = text;
        ctx.font = `600 64px ${font}`;
        ctx.fillText(String(play.count), x, y);
        const width = Math.max(ctx.measureText(String(play.count)).width, 160);
        ctx.fillStyle = muted;
        ctx.font = `400 32px ${font}`;
        ctx.fillText(play.label, x, y + 44);
        x += width + 110;
      });
      y += 44;
    }

    recap.top.forEach((section) => {
      if (y > HEIGHT - 260) return;
      y += 100;
      ctx.fillStyle = text;
      ctx.font = `600 40px ${font}`;
      ctx.fillText(interpolate(gettext("Top %s"), [section.label]), PAD, y);
      section.entries.slice(0, 3).forEach((entry, index) => {
        if (y > HEIGHT - 200) return;
        y += 62;
        const meta = entry.episodes
          ? interpolate(ngettext("%s ep", "%s eps", entry.episodes), [entry.episodes])
          : entry.duration;
        ctx.font = `400 36px ${font}`;
        const metaWidth = ctx.measureText(meta).width;
        ctx.fillStyle = muted;
        ctx.fillText(String(index + 1), PAD, y);
        ctx.fillText(meta, WIDTH - PAD - metaWidth, y);
        ctx.fillStyle = text;
        ctx.fillText(fit(ctx, entry.title, WIDTH - PAD * 2 - 60 - metaWidth - 32), PAD + 60, y);
      });
    });

    ctx.fillStyle = muted;
    ctx.font = `600 32px ${font}`;
    ctx.fillText("Floppy", PAD, HEIGHT - PAD + 10);
    return canvas;
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-recap-save]");
    const data = document.getElementById("ct-recap-data");
    const card = document.querySelector("[data-recap-card]");
    if (!button || !data || !card) return;
    const recap = JSON.parse(data.textContent);
    draw(recap, card).toBlob((blob) => {
      if (!blob) return;
      const file = new File([blob], button.dataset.filename, { type: "image/png" });
      // Phones get the share sheet (save to photos); desktops download.
      const touch = matchMedia("(pointer: coarse)").matches;
      if (touch && navigator.canShare && navigator.canShare({ files: [file] })) {
        navigator.share({ files: [file], title: recap.month_label }).catch(() => {});
        return;
      }
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = button.dataset.filename;
      link.click();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    }, "image/png");
  });
})();
