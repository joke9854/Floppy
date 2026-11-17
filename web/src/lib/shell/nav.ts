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
	{ label: t.home, href: '/', icon: House },
	{ label: t.discover, href: '/discover', icon: Compass },
	{ label: t.calendar, href: '/calendar', icon: Calendar }
];

export const LIBRARY_MORE: NavItem[] = [
	{ label: t.lists, href: '/lists', icon: List },
	{ label: t.collection, href: '/collection/', icon: Box },
	{ label: t.tags, href: '/tags', icon: Tag },
	{ label: t.addEntry, href: '/create', icon: CirclePlus }
];

export const YOU: NavItem[] = [
	{ label: t.history, href: '/history', icon: History },
	{ label: t.stats, href: '/statistics', icon: ChartColumn }
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

/** The user's Library switch (GET user/sidebar/ `library`) as nav items. */
export function libraryItems(types: LibraryType[]): NavItem[] {
	return types.map((type) => ({
		label: type.label,
		href: `/medialist/${encodeURIComponent(type.media_type)}`,
		icon: MEDIA_ICONS[type.media_type] ?? LayoutGrid
	}));
}
