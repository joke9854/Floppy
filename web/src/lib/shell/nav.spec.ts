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
	it('open the web Library for every Library type, Django for anything else', () => {
		expect(libraryHref('tv', '/next')).toBe('/next/library/tv');
		expect(libraryHref('music', '/next')).toBe('/next/library/music');
		expect(libraryHref('episode', '/next')).toBe('/medialist/episode');
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
	it('opens movie, show, episode and person pages on the web, everything else on Django', () => {
		expect(detailHref('/details/tmdb/movie/238/the-godfather', '/next')).toBe(
			'/next/details/tmdb/movie/238/the-godfather'
		);
		expect(detailHref('/details/openlibrary/book/OL1W/dune', '/next')).toBe(
			'/next/details/openlibrary/book/OL1W/dune'
		);
		expect(detailHref('/details/igdb/game/7/zelda', '/next')).toBe('/next/details/igdb/game/7/zelda');
		expect(detailHref('/details/comicvine/comic/4050-1/saga', '/next')).toBe(
			'/next/details/comicvine/comic/4050-1/saga'
		);
		// Anime and a comic issue keep their Django page.
		expect(detailHref('/details/mal/anime/1/bebop', '/next')).toBe('/details/mal/anime/1/bebop');
		expect(detailHref('/details/comicvine/comicissue/4000-1/one', '/next')).toBe(
			'/details/comicvine/comicissue/4000-1/one'
		);
		expect(detailHref('/details/tmdb/tv/1399/got?season=2', '/next')).toBe(
			'/next/details/tmdb/tv/1399/got?season=2'
		);
		expect(detailHref('/details/tmdb/tv/1399/got/season/1/episode/2', '/next')).toBe(
			'/next/details/tmdb/tv/1399/got/season/1/episode/2'
		);
		expect(detailHref('/details/music/artist/7/slowdive-7/', '/next')).toBe(
			'/next/details/music/artist/7/slowdive-7/'
		);
		expect(detailHref('/details/music/artist/7/slowdive-7/album/9/souvlaki-9/', '/next')).toBe(
			'/next/details/music/artist/7/slowdive-7/album/9/souvlaki-9/'
		);
		expect(detailHref('/details/music/album/9/releases', '/next')).toBe('/details/music/album/9/releases');
		expect(detailHref('/details/pocketcasts/podcast/abc-123/test-cast', '/next')).toBe(
			'/next/details/pocketcasts/podcast/abc-123/test-cast'
		);
		expect(detailHref('/details/gpodder/podcast/abc-123/', '/next')).toBe(
			'/next/details/gpodder/podcast/abc-123/'
		);
		expect(detailHref('/details/tmdb/podcast/abc-123/test-cast', '/next')).toBe(
			'/details/tmdb/podcast/abc-123/test-cast'
		);
		expect(detailHref('/person/tmdb/9273/amy-adams', '/next')).toBe(
			'/next/person/tmdb/9273/amy-adams'
		);
		expect(detailHref('/history?media_type=movie&media_id=238&source=tmdb', '/next')).toBe(
			'/next/history?media_type=movie&media_id=238&source=tmdb'
		);
		expect(detailHref('/history/sessions', '/next')).toBe('/history/sessions');
		expect(detailHref('/discover?media_type=movie', '/next')).toBe('/next/discover?media_type=movie');
		expect(detailHref('/discover/rows', '/next')).toBe('/discover/rows');
		expect(detailHref('/statistics?start-date=all&end-date=all', '/next')).toBe(
			'/next/statistics?start-date=all&end-date=all'
		);
		expect(detailHref('/statistics/recap?month=2026-11', '/next')).toBe('/statistics/recap?month=2026-11');
		expect(detailHref('/lists?scope=shared', '/next')).toBe('/next/lists?scope=shared');
		expect(detailHref('/list/7', '/next')).toBe('/next/list/7');
		expect(detailHref('/list/my-list?sort=custom', '/next')).toBe('/next/list/my-list?sort=custom');
		expect(detailHref('/list/create', '/next')).toBe('/list/create');
		expect(detailHref('/list/7/add', '/next')).toBe('/list/7/add');
		expect(detailHref('/list/7/rss', '/next')).toBe('/list/7/rss');
		expect(detailHref('/settings/notifications', '/next')).toBe('/next/settings/notifications');
		expect(detailHref('/settings/sidebar', '/next')).toBe('/next/settings/sidebar');
		expect(detailHref('/settings/preferences', '/next')).toBe('/next/settings/preferences');
		expect(detailHref('/settings/connected-apps', '/next')).toBe('/next/settings/connected-apps');
		expect(detailHref('/settings/integrations', '/next')).toBe('/next/settings/integrations');
		expect(detailHref('/settings/rss', '/next')).toBe('/next/settings/rss');
		expect(detailHref('/settings/import', '/next')).toBe('/next/settings/import');
		expect(detailHref('/details/tmdb/tv/1399/got/season/1', '/next')).toBe(
			'/details/tmdb/tv/1399/got/season/1'
		);
		expect(detailHref('/details/mal/anime/1/cowboy-bebop', '/next')).toBe(
			'/details/mal/anime/1/cowboy-bebop'
		);
		expect(detailHref('/details/tmdb/movie/238/x?fragment=secondary', '/next')).toBe(
			'/details/tmdb/movie/238/x?fragment=secondary'
		);
	});
});
