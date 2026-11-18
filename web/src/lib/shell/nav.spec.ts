import { describe, expect, it } from 'vitest';
import {
	LIBRARY_MORE,
	PRIMARY,
	YOU,
	detailHref,
	isCurrentHref,
	libraryHref,
	libraryItems,
	reloadFor
} from './nav.ts';

describe('libraryItems', () => {
	it('keeps the order and names from the API and links each type to its Library', () => {
		const items = libraryItems([
			{ media_type: 'movie', label: 'Movies' },
			{ media_type: 'tv', label: 'TV Shows' },
			{ media_type: 'mystery', label: 'Mystery' }
		]);

		expect(items.map((item) => [item.label, item.href])).toEqual([
			['Movies', '/library/movie'],
			['TV Shows', '/library/tv'],
			['Mystery', '/medialist/mystery']
		]);
		expect(items.every((item) => item.icon)).toBe(true);
	});
});

describe('shell links', () => {
	it('point at the Django pages until their screens move to /next', () => {
		const hrefs = [...PRIMARY, ...LIBRARY_MORE, ...YOU].map((item) => item.href);

		expect(hrefs).toEqual([
			'/',
			'/discover',
			'/calendar',
			'/lists',
			'/collection/',
			'/tags',
			'/create',
			'/history',
			'/statistics'
		]);
	});
});

describe('app links', () => {
	it('open the web Library for the types it has, Django for the rest', () => {
		expect(libraryHref('tv', '/next')).toBe('/next/library/tv');
		expect(libraryHref('music', '/next')).toBe('/medialist/music');
	});

	it('navigate in place inside the app and reload into Django pages', () => {
		expect(reloadFor('/next/', '/next')).toBe('off');
		expect(reloadFor('/next/library/tv', '/next')).toBe('off');
		expect(reloadFor('/history', '/next')).toBe('');
		expect(reloadFor('/nextcloud', '/next')).toBe('');
	});

	it('mark the current screen, Home only at its root', () => {
		expect(isCurrentHref('/next/', '/next/', '/next')).toBe(true);
		expect(isCurrentHref('/next/', '/next/library/tv', '/next')).toBe(false);
		expect(isCurrentHref('/next/library/tv', '/next/library/tv', '/next')).toBe(true);
		expect(isCurrentHref('/next/library/tv', '/next/library/tvx', '/next')).toBe(false);
		expect(isCurrentHref('/history', '/history', '/next')).toBe(false);
	});
});

describe('detail links', () => {
	it('opens movie and show pages on the web, everything else on Django', () => {
		expect(detailHref('/details/tmdb/movie/238/the-godfather', '/next')).toBe(
			'/next/details/tmdb/movie/238/the-godfather'
		);
		expect(detailHref('/details/tmdb/tv/1399/got?season=2', '/next')).toBe(
			'/next/details/tmdb/tv/1399/got?season=2'
		);
		expect(detailHref('/details/tmdb/tv/1399/got/season/1/episode/2', '/next')).toBe(
			'/details/tmdb/tv/1399/got/season/1/episode/2'
		);
		expect(detailHref('/details/mal/anime/1/cowboy-bebop', '/next')).toBe(
			'/details/mal/anime/1/cowboy-bebop'
		);
		expect(detailHref('/details/tmdb/movie/238/x?fragment=secondary', '/next')).toBe(
			'/details/tmdb/movie/238/x?fragment=secondary'
		);
	});
});
