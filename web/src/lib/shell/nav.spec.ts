import { describe, expect, it } from 'vitest';
import { LIBRARY_MORE, PRIMARY, YOU, libraryItems } from './nav.ts';

describe('libraryItems', () => {
	it('keeps the order and names from the API and links to the Django library', () => {
		const items = libraryItems([
			{ media_type: 'movie', label: 'Movies' },
			{ media_type: 'tv', label: 'TV Shows' },
			{ media_type: 'mystery', label: 'Mystery' }
		]);

		expect(items.map((item) => [item.label, item.href])).toEqual([
			['Movies', '/medialist/movie'],
			['TV Shows', '/medialist/tv'],
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
