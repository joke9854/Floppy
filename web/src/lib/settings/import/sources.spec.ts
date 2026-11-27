import { describe, expect, it } from 'vitest';
import { IMPORT_SOURCES, sharedFields, standardImportsDisabled } from './sources.ts';

describe('import sources', () => {
	it('posts the page settings with every form', () => {
		expect(sharedFields({ frequency: 'once', time: '03:00', mode: 'new' })).toEqual({ frequency: 'once', time: '03:00', mode: 'new' });
	});
	it('turns standard imports off for watchlist and collection modes', () => {
		expect(standardImportsDisabled('watchlist')).toBe(true);
		expect(standardImportsDisabled('update_collection')).toBe(true);
		expect(standardImportsDisabled('overwrite')).toBe(false);
	});
	it('names the field each upload view reads', () => {
		expect(IMPORT_SOURCES.yamtrack.files?.[0].name).toBe('yamtrack_csv');
		expect(IMPORT_SOURCES.tvtime.files?.map((file) => file.name)).toEqual(['tvtime_shows_csv', 'tvtime_movies_csv']);
		expect(IMPORT_SOURCES.myanimelist.url).toBe('mal');
	});
});
