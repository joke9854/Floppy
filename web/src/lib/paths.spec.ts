import { describe, expect, it } from 'vitest';
import { safeNext } from './paths';

describe('safeNext', () => {
	it('keeps paths inside the app', () => {
		expect(safeNext('/next/library?page=2', '/next')).toBe('/next/library?page=2');
		expect(safeNext('/next', '/next')).toBe('/next');
	});

	it('sends anything else to the start page', () => {
		for (const next of [null, '', 'https://evil.example/', '//evil.example/next/', '/\evil', '/admin/', '/nextdoor']) {
			expect(safeNext(next, '/next')).toBe('/next/');
		}
	});
});
