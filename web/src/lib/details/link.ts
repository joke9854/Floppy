import { detailHref, libraryHref, reloadFor } from '#lib/shell/nav.ts';

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

/**
 * A genre chip's attributes (P4-L1): Django's `/medialist/<type>?genre=...`
 * opens the web Library for the types that have one (its `genre` filter),
 * else the Django list.
 */
export function genreLink(url: string): Record<string, string> {
	const match = /^\/medialist\/([^/?#]+)\/?(\?.*)?$/.exec(url);
	if (!match) return detailLink(url);
	return detailLink(`${libraryHref(decodeURIComponent(match[1]))}${match[2] ?? ''}`);
}
