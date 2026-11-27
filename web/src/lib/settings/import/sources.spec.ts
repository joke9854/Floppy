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
	it('has every K2 source with the right kind', () => {
		const kinds = { trakt: 'trakt', anilist: 'anilist', lastfm: 'account', koito: 'account', steam: 'username', xbox: 'account', psn: 'account', pocketcasts: 'account', gpodder: 'account' };
		for (const [key, kind] of Object.entries(kinds)) expect(IMPORT_SOURCES[key]?.kind, key).toBe(kind);
		expect(IMPORT_SOURCES.steam.url).toBe('steam');
	});
	it('keys every account entry by its own key', () => {
		for (const [key, source] of Object.entries(IMPORT_SOURCES)) if (source.kind === 'account') expect(source.account?.key, key).toBe(key);
	});
	it('labels the console sync by frequency', () => {
		for (const key of ['xbox', 'psn']) {
			const account = IMPORT_SOURCES[key].account!;
			expect(account.syncLabel({ frequency: 'once', pollInterval: 5 })).toBe('Sync Now');
			expect(account.syncLabel({ frequency: 'daily', pollInterval: 5 })).toBe('Schedule Sync');
		}
	});
	it('puts the Last.fm poll interval in its texts', () => {
		const account = IMPORT_SOURCES.lastfm.account!;
		expect(account.disconnected({ frequency: 'once', pollInterval: 7 })).toContain('every 7 minutes');
		expect(account.connected({ frequency: 'once', pollInterval: 7 })).toContain('every 7 minutes');
	});
	it('defaults the GPodder server', () => {
		expect(IMPORT_SOURCES.gpodder.account?.connectFields.find((field) => field.name === 'server_url')?.value).toBe('https://gpodder.net');
	});
});
