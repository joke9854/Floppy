import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

# Alpine only hides an `x-show` element once it has booted. A modal backdrop is
# a full-screen `fixed inset-0 bg-black/50` div, so until then it renders over
# the whole page. `x-cloak` plus the global `[x-cloak] { display: none
# !important }` rule in input.css is what suppresses that flash, and it has to
# be on the same element as the `x-show`.
#
# Rendering every page that carries one of these is far more scaffolding than a
# single attribute warrants, and misses any template no test happens to render
# (media_card_list.html, episode_row.html and detail_action_buttons.html all
# went without it). Scanning the templates covers them all, including ones
# added later.
MODAL_OPEN_STATES = ("trackOpen", "listsOpen", "tagsOpen", "editTrackOpen")

# The backdrop is the element that covers the page. A nested `x-show` on inner
# content is hidden along with its parent, so only these need cloaking.
BACKDROP = re.compile(r"fixed\s+inset-0[^\"]*bg-black/")

OPEN_TAG = re.compile(r"<(?:div|template)\b[^>]*>", re.DOTALL)


def _template_files():
    return sorted(Path(settings.BASE_DIR).joinpath("templates").rglob("*.html"))


class ModalCloakContractTests(SimpleTestCase):
    """Every modal backdrop must be cloaked until Alpine hides it."""

    def test_modal_backdrops_carry_x_cloak(self):
        offenders = []
        for path in _template_files():
            text = path.read_text(encoding="utf-8")
            for match in OPEN_TAG.finditer(text):
                tag = match.group(0)
                if not BACKDROP.search(tag):
                    continue
                shows = re.search(r'x-show="([^"]+)"', tag)
                if not shows or shows.group(1).strip() not in MODAL_OPEN_STATES:
                    continue
                if "x-cloak" in tag:
                    continue
                line = text.count("\n", 0, match.start()) + 1
                offenders.append(f'{path.name}:{line} (x-show="{shows.group(1)}")')

        self.assertEqual(
            offenders,
            [],
            "Modal backdrops missing x-cloak, so they flash over the page "
            f"before Alpine boots: {offenders}",
        )

    def test_the_scan_actually_finds_the_backdrops_it_guards(self):
        """Guard the guard: a regex that matches nothing would pass vacuously."""
        found = 0
        for path in _template_files():
            text = path.read_text(encoding="utf-8")
            for match in OPEN_TAG.finditer(text):
                tag = match.group(0)
                shows = re.search(r'x-show="([^"]+)"', tag)
                if BACKDROP.search(tag) and shows:
                    found += 1
        self.assertGreater(found, 10, "modal backdrop scan matched almost nothing")
