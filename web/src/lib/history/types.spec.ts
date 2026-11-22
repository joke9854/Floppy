import { describe, expect, it } from 'vitest';
import { historyQuery } from './types.ts';

describe('history query', () => {
	it('applies changes, drops empty values and resets the page', () => {
		const current = new URLSearchParams('media_type=tv&page=3&genre=Drama');
		expect(historyQuery(current, { media_type: 'movie' })).toBe('?media_type=movie&genre=Drama');
		expect(historyQuery(current, { genre: null, media_type: '' })).toBe('');
		expect(historyQuery(current, { page: '2' })).toBe('?media_type=tv&genre=Drama&page=2');
	});
});
