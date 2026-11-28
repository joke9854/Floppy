import type { Component } from 'svelte';
import Box from '@lucide/svelte/icons/box';
import Book from '@lucide/svelte/icons/book';
import BookImage from '@lucide/svelte/icons/book-image';
import BookOpen from '@lucide/svelte/icons/book-open';
import Calendar from '@lucide/svelte/icons/calendar';
import ChartColumn from '@lucide/svelte/icons/chart-column';
import CirclePlus from '@lucide/svelte/icons/circle-plus';
import Compass from '@lucide/svelte/icons/compass';
import Dices from '@lucide/svelte/icons/dices';
import Disc3 from '@lucide/svelte/icons/disc-3';
import Film from '@lucide/svelte/icons/film';
import Gamepad2 from '@lucide/svelte/icons/gamepad-2';
import History from '@lucide/svelte/icons/history';
import House from '@lucide/svelte/icons/house';
import Layers from '@lucide/svelte/icons/layers';
import LayoutGrid from '@lucide/svelte/icons/layout-grid';
import List from '@lucide/svelte/icons/list';
import Mic from '@lucide/svelte/icons/mic';
import Sparkles from '@lucide/svelte/icons/sparkles';
import Tag from '@lucide/svelte/icons/tag';
import Tv from '@lucide/svelte/icons/tv';
import { BASE } from '#lib/paths.ts';
import { t } from '#lib/strings.ts';

export interface NavItem {
	label: string;
	href: string;
	icon: Component;
}

/**
 * Screens not rebuilt yet open the Django page (a full page load: they are
 * not SvelteKit routes). Each moves to `/next/...` when its screen ships (P4).
 */
export const PRIMARY: NavItem[] = [
	{ label: t.home, href: `${BASE}/`, icon: House },
	{ label: t.discover, href: `${BASE}/discover`, icon: Compass },
	{ label: t.calendar, href: `${BASE}/calendar`, icon: Calendar }
];

export const LIBRARY_MORE: NavItem[] = [
	{ label: t.lists, href: `${BASE}/lists`, icon: List },
	{ label: t.collection, href: '/collection/', icon: Box },
	{ label: t.tags, href: '/tags', icon: Tag },
	{ label: t.addEntry, href: '/create', icon: CirclePlus }
];

export const YOU: NavItem[] = [
	{ label: t.history, href: `${BASE}/history`, icon: History },
	{ label: t.stats, href: `${BASE}/statistics`, icon: ChartColumn }
];

export const LIBRARY_ICON = LayoutGrid;

const MEDIA_ICONS: Record<string, Component> = {
	tv: Tv,
	season: Layers,
	movie: Film,
	anime: Sparkles,
	manga: BookOpen,
	game: Gamepad2,
	book: Book,
	comic: BookImage,
	boardgame: Dices,
	music: Disc3,
	podcast: Mic
};

export interface LibraryType {
	media_type: string;
	label: string;
}

/**
 * Library types with a web screen: every Library type since P4-B6 (music,
 * podcasts and comics joined the poster grid's types).
 */
export const WEB_LIBRARY_TYPES = new Set([
	'tv',
	'season',
	'movie',
	'anime',
	'manga',
	'game',
	'book',
	'boardgame',
	'music',
	'podcast',
	'comic'
]);

/** Where a Library type opens: the web screen when it has one, else Django's. */
export function libraryHref(mediaType: string, base: string = BASE): string {
	const type = encodeURIComponent(mediaType);
	return WEB_LIBRARY_TYPES.has(mediaType) ? `${base}/library/${type}` : `/medialist/${type}`;
}

/** The user's Library switch (GET user/sidebar/ `library`) as nav items. */
export function libraryItems(types: LibraryType[]): NavItem[] {
	return types.map((type) => ({
		label: type.label,
		href: libraryHref(type.media_type),
		icon: MEDIA_ICONS[type.media_type] ?? LayoutGrid
	}));
}

/** A link to a screen of this app (client navigation), not a Django page. */
export function isAppHref(href: string, base: string = BASE): boolean {
	return href === `${base}/` || href.startsWith(`${base}/`);
}

/**
 * `data-sveltekit-reload` for a link: Django pages load in full; this app's
 * own screens navigate in place ("off").
 */
export function reloadFor(href: string, base: string = BASE): '' | 'off' {
	return isAppHref(href, base) ? 'off' : '';
}

/** Whether a link names the page at `pathname` (Home only at its root). */
export function isCurrentHref(href: string, pathname: string, base: string = BASE): boolean {
	if (!isAppHref(href, base)) return false;
	const path = pathname.endsWith('/') ? pathname : `${pathname}/`;
	if (href === `${base}/`) return path === `${base}/`;
	return path.startsWith(href.endsWith('/') ? href : `${href}/`);
}

/**
 * Django pages with a web screen: a movie, show, manga, game, book, comic or board game
 * (/details/<source>/<movie|tv>/<id>/<title>[?season=N]), a TV episode
 * (.../tv/<id>/<title>/season/<n>/episode/<n>), a person
 * (/person/<source>/<id>/<name>), a music artist
 * (/details/music/artist/<id>/<slug>), an album (.../artist/<id>/<slug>/album/<id>/<slug>)
 * and a podcast show (/details/<pocketcasts|gpodder|audiobookshelf>/podcast/<uuid>[/<title>]).
 */
const WEB_DETAIL = [
	/^\/details\/[^/?#]+\/(?:movie|tv|manga|game|book|comic|boardgame)\/[^/?#]+\/[^/?#]+\/?(?:\?season=\d+)?$/,
	/^\/details\/[^/?#]+\/tv\/[^/?#]+\/[^/?#]+\/season\/\d+\/episode\/\d+\/?$/,
	/^\/person\/[^/?#]+\/[^/?#]+\/[^/?#]+\/?$/,
	// Music artists and albums, and podcast shows (P4-L2).
	/^\/details\/music\/artist\/\d+\/[^/?#]+\/?(?:album\/\d+\/[^/?#]+\/?)?$/,
	/^\/details\/(?:pocketcasts|gpodder|audiobookshelf)\/podcast\/[^/?#]+(?:\/[^/?#]+)?\/?$/,
	// History (P4-E), any of its filters.
	/^\/history\/?(\?|$)/,
	// Discover (P4-G), any type.
	/^\/discover\/?(\?|$)/,
	// Statistics (P4-H), any range; the Monthly recap stays Django.
	/^\/statistics\/?(\?|$)/,
	// The Lists index (P4-I1); a list's own page (/list/...) stays Django until I2.
	/^\/lists\/?(\?|$)/,
	// A list's page (P4-I2): /list/<id or custom URL>, not the actions beside it.
	/^\/list\/(?!(?:bulk-add|create|delete|edit|import-csv|share-view)(?:[/?#]|$))[^/?#]+\/?(?:\?.*)?$/,
	// The settings pages the web draws (P4-J1 to J3, K).
	/^\/settings\/(?:account|appearance|notifications|sidebar|preferences|metadata|export|connected-apps|advanced|about|integrations|rss|import)\/?$/
];

/**
 * Where a title's or person's link opens (P4-C): movie, show, episode and
 * person pages open the web screen; other types keep their Django page.
 */
export function detailHref(href: string, base: string = BASE): string {
	return WEB_DETAIL.some((pattern) => pattern.test(href)) ? `${base}${href}` : href;
}
