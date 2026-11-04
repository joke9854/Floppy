// Global keyboard shortcut for search
// Bind once: this script is re-evaluated on boosted (hx-boost) navigation.
if (!window.__floppySearchShortcutBound) {
window.__floppySearchShortcutBound = true;
document.addEventListener('keydown', (e) => {
  // Ignore if typing in an input, textarea, or contenteditable
  const activeEl = document.activeElement;
  const isTyping = activeEl.tagName === 'INPUT' ||
                   activeEl.tagName === 'TEXTAREA' ||
                   activeEl.isContentEditable;

  if (isTyping) return;

  if (e.key === '/') {
    e.preventDefault();
    const searchInput = document.getElementById('global-search');
    // The CineTrack sidebar hides the top bar from lg up; search there is the palette.
    if (searchInput && !searchInput.checkVisibility() && document.querySelector('.ct-palette')) {
      window.dispatchEvent(new CustomEvent('ct-palette-open'));
    } else if (searchInput) {
      searchInput.focus();
      searchInput.select();
    }
  }
});
}
