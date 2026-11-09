# Theming

Floppy resolves its colour theme on the server, not in the browser. This page
records the contract, because two of its rules are easy to break by accident and
neither failure is visible in the theme the author has open.

## How a theme is selected

CineTrack is the only theme. `user.theme` still exists (it is exported and read
by clients) but has one value, `cinetrack`; migration `users.0140` moved every
account onto it. `base.html` writes the class unconditionally, for signed-in,
public and anonymous pages alike:

```html
<html class="{% block html_theme %}cinetrack{% endblock html_theme %}">
```

There is no theme picker, header light/dark toggle or custom palette. The
`custom_theme` column is kept, unused, so the upgrade deletes no saved data.

`ct_shell` in `base.html` decides only whether the v2 navigation chrome renders:
signed in and not a public view. Public and anonymous pages (public lists,
public detail links) keep their own sidebar-less layout under the same palette.

## Tokens

The tokens live in `src/static/css/areas/tokens.css`, one of the per-area files
imported by the entry `src/static/css/input.css`. They are declared in two
places only:

| Selector | Holds |
| --- | --- |
| `:root` | the dark defaults, the motion scale and the `@theme` values |
| `html.cinetrack` | the CineTrack palette, radius and motion |

There are no `html.light`, `html.dark`, preset or custom palette blocks, and no
`prefers-color-scheme` override. `base.html` always stamps `cinetrack` on
`<html>`, so a rule scoped to any other theme class can never match. Do not add
one.

`--color-accent-contrast` is the foreground for controls filled with
`--color-accent`. Define the pair together in `html.cinetrack`, because the
CineTrack accents are too bright for white text.

`html.cinetrack` owns `--theme-radius`, `--motion-duration`,
`--motion-distance` and `--motion-ease`. Components consume those tokens rather
than inventing local timings or radii.

If you add a token, add it to `:root`, and to `html.cinetrack` if CineTrack
needs a different value.

The global `prefers-reduced-motion: reduce` block is a required safety net. It
lives in `src/static/css/areas/overrides.css`. It must keep navigation and
controls usable while reducing animations and smooth scrolling to effectively
instantaneous changes.

## CineTrack

`html.cinetrack` maps the Android app's `ui/theme` values onto the same tokens
and sets Manrope, self-hosted under `static/fonts/manrope/` (SIL OFL) and
preloaded only for this theme. It also defines `--ct-*` tokens (status colours, progress track, radii) for the redesigned components. The shell sets its own `--ct-shell-pad` in `src/static/css/areas/shell.css`.

Glass follows the app's rule: `.ct-glass` (overlays such as nav and sheets) and
`.ct-glass-control` (buttons, pills) blur what is behind them, so use them only
on controls, never as a card layer or over poster art. `.ct-card` is the plain
card material and has no blur.

`static/js/posterAccent.js` sets `--poster-accent` and `--poster-accent-text`
on the nearest `[data-poster-accent-scope]` from an
`<img data-poster-accent crossorigin="anonymous">`. A poster that can't be
sampled sets nothing, so consume it as `var(--poster-accent, var(--color-accent))`.

## Never use Tailwind's `dark:` variant

`dark:` compiles to `@media (prefers-color-scheme: dark)`, which reads the
operating system and ignores `user.theme`. It agrees with the app only while a
user keeps the system default, and inverts for anyone who overrides it. Use a
token instead.

`src/app/tests/test_theme_tokens.py` fails the build on any `dark:` utility in a
template, and on the raw palette utilities that have token equivalents.

## Colour on a fixed surface

A token resolves per theme; a hardcoded colour does not. Pairing them inverts.

- A `--color-*` text token on a permanently dark surface, such as a poster
  overlay (`bg-gray-900/90`) or a toast (`bg-red-700/95`), goes dark-on-dark in
  the light theme. Pin a literal foreground there instead, usually `text-white`.
- A hardcoded light foreground on a token surface fails the other way.

Toast icons are the standard example of the first case and keep their literal
palette values on purpose.

## Two values that must stay apart

`--color-hover-dim` is painted over `--color-sidebar` by the sidebar navigation
and the header controls. If the two resolve to the same colour, those controls
lose their hover feedback. They collided at `#f1f3f5` in the light theme once
already.

## Rebuilding `main.css`

```bash
npx --offline @tailwindcss/cli@4.1.11 -i ./src/static/css/input.css -o ./src/static/css/main.css
```

`input.css` is an entry file: `@import "tailwindcss" source("../../");` first,
then one `@import` per file in `src/static/css/areas/`, in cascade order. Edit
the area file that owns a rule, not the entry. Keep the imports in their
current order, since the file order is the cascade.

The input uses `source("../../")`, so the build scans `src/`, which contains its
own committed output. One pass is not a fixpoint: a class removed from a
template can survive in the stylesheet because the previous stylesheet still
mentions it. Run the command until the output stops changing.

For the same reason, a Python or JavaScript file that contains a Tailwind class
name as a string literal will have that class compiled into the stylesheet. The
banned-utility list in `test_theme_tokens.py` assembles its names from
concatenated parts to avoid exactly that.

## Persisting preferences

The preferences view reads every field with a presence check rather than a
fallback, so a form that posts only some fields does not reset the rest.
`users.tests.views.test_theme_toggle` pins this.

Settings > Appearance owns the sidebar style and detail page composition. It
validates the complete payload before saving any part. Values passed to Django's
`json_script` must remain Python dictionaries; the filter performs the single
required serialization before Alpine parses them.

`PATCH /api/v1/user/preferences/` follows the same rule and ignores any field
the body omits. It does not accept `theme`.
