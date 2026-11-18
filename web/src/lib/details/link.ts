import { detailHref, reloadFor } from '#lib/shell/nav.ts';

/**
 * A title link's attributes (P4-C1): movie and show pages open the web
 * detail page in place, everything else loads its Django page. The detail
 * load reads the provider, so it preloads on tap, never on hover.
 */
export function detailLink(url: string): Record<string, string> {
	const href = detailHref(url);
	const reload = reloadFor(href);
	return reload === 'off'
		? { href, 'data-sveltekit-reload': 'off', 'data-sveltekit-preload-data': 'tap' }
		: { href, 'data-sveltekit-reload': '' };
}
