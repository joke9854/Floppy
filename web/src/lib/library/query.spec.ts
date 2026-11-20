import { describe, expect, it } from 'vitest';
import { apiQuery, libraryApiPath, withParams } from './query.ts';

describe('Library query', () => {
	it('passes the page filters and layout through, without page', () => {
		const search = new URLSearchParams(
			'sort=score&direction=desc&status=In+progress&status=Paused&layout=table&page=3&genre=Drama'
		);

		expect(apiQuery(search)).toBe(
			'?sort=score&direction=desc&status=In+progress&status=Paused&layout=table&genre=Drama'
		);
		expect(libraryApiPath('tv', search, 2)).toBe(
			'/api/v1/library/tv/?sort=score&direction=desc&status=In+progress&status=Paused&layout=table&genre=Drama&page=2'
		);
		expect(apiQuery(new URLSearchParams())).toBe('');
	});

	it('changes one parameter and starts the list again', () => {
		const url = 'https://example.test/next/library/tv?sort=title&page=4&search=bear';

		expect(withParams(url, { sort: 'score', direction: 'desc' })).toBe(
			'/next/library/tv?sort=score&search=bear&direction=desc'
		);
		expect(withParams(url, { search: null })).toBe('/next/library/tv?sort=title');
		expect(withParams(url, { tag: ['a', 'b'] })).toBe(
			'/next/library/tv?sort=title&search=bear&tag=a&tag=b'
		);
	});
});
