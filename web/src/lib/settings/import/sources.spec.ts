import { describe, expect, it } from 'vitest';
import {
	ALL_LIBRARIES,
	contentKindFields,
	defaultContentKind,
	initialSelection,
	plexLibraryLabel,
	plexPrimaryLabel,
	plexSubmitDisabled,
	reconcileSelection,
	sectionToLibrary,
	toggleLibrary
} from './plex.ts';
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
			expect(account.syncLabel({ frequency: 'once', pollInterval: 5, absPollInterval: 5 })).toBe('Sync Now');
			expect(account.syncLabel({ frequency: 'daily', pollInterval: 5, absPollInterval: 5 })).toBe('Schedule Sync');
		}
	});
	it('puts the Last.fm poll interval in its texts', () => {
		const account = IMPORT_SOURCES.lastfm.account!;
		expect(account.disconnected({ frequency: 'once', pollInterval: 7, absPollInterval: 7 })).toContain('every 7 minutes');
		expect(account.connected({ frequency: 'once', pollInterval: 7, absPollInterval: 7 })).toContain('every 7 minutes');
	});
	it('defaults the GPodder server', () => {
		expect(IMPORT_SOURCES.gpodder.account?.connectFields.find((field) => field.name === 'server_url')?.value).toBe('https://gpodder.net');
	});
	it('has every K3 source with the right kind', () => {
		const kinds = { plex: 'plex', radarr: 'arr', sonarr: 'arr', stremio: 'account', audiobookshelf: 'account', storyteller: 'storyteller', koreader: 'koreader' };
		for (const [key, kind] of Object.entries(kinds)) expect(IMPORT_SOURCES[key]?.kind, key).toBe(kind);
	});
	it('lets Stremio connect with an auth key, or email and password', () => {
		const ready = IMPORT_SOURCES.stremio.account!.connectReady!;
		expect(ready({ auth_key: 'abc' })).toBe(true);
		expect(ready({ email: 'a@b.c', password: 'pw' })).toBe(true);
		expect(ready({ email: 'a@b.c' })).toBe(false);
		expect(ready({})).toBe(false);
	});
	it('puts the Audiobookshelf poll interval in its connected text', () => {
		const text = IMPORT_SOURCES.audiobookshelf.account!.connected({ frequency: 'once', pollInterval: 5, absPollInterval: 30 });
		expect(text).toBe('Sync Audiobook progress from Audiobookshelf every 30 minutes.');
	});
});

describe('plex dialog logic', () => {
	const music = { value: 'm::1', label: 'Music', is_music: true, audiobook_hint: true, content_kind: 'auto' };
	const movies = { value: 'm::2', label: 'Movies', is_music: false, audiobook_hint: false, content_kind: 'auto' };
	it('labels a section as Django does', () => {
		expect(plexLibraryLabel({ id: 1, title: 'Films', server_name: 'Home', type: 'movie', machine_identifier: 'm' })).toBe('Films - Home (Movie)');
		expect(plexLibraryLabel({ id: 1, machine_identifier: 'm' })).toBe('Unknown library');
		expect(sectionToLibrary({ id: 3, title: 'T', machine_identifier: 'abc', is_music: true }).value).toBe('abc::3');
	});
	it('defaults the content kind', () => {
		expect(defaultContentKind({ audiobook_hint: true, content_kind: 'auto' })).toBe('audiobook');
		expect(defaultContentKind({ audiobook_hint: false, content_kind: 'auto' })).toBe('auto');
		expect(defaultContentKind({ audiobook_hint: true, content_kind: 'music' })).toBe('music');
	});
	it('toggles libraries, keeping all exclusive', () => {
		let selection = toggleLibrary(initialSelection(), music);
		expect(selection).toEqual({ libraries: ['m::1'], kinds: { 'm::1': 'audiobook' } });
		selection = toggleLibrary(selection, movies);
		expect(selection.libraries).toEqual(['m::1', 'm::2']);
		selection = toggleLibrary(selection, music);
		expect(selection).toEqual({ libraries: ['m::2'], kinds: {} });
		expect(reconcileSelection(selection, [music]).libraries).toEqual([]);
		expect(reconcileSelection(initialSelection(), []).libraries).toEqual([ALL_LIBRARIES]);
		expect(contentKindFields({ 'm::1': 'music' })).toEqual(['m::1::music']);
	});
	it('words the primary button and disables it', () => {
		expect(plexPrimaryLabel('update_collection', false)).toBe('Update');
		expect(plexPrimaryLabel('watchlist', false)).toBe('Enable Sync');
		expect(plexPrimaryLabel('watchlist', true)).toBe('Sync Now');
		expect(plexPrimaryLabel('new', true)).toBe('Import');
		expect(plexSubmitDisabled('error', 'new', initialSelection(), true)).toBe(true);
		expect(plexSubmitDisabled('connected', 'new', initialSelection(), false)).toBe(true);
		expect(plexSubmitDisabled('connected', 'new', { libraries: [], kinds: {} }, true)).toBe(true);
		expect(plexSubmitDisabled('connected', 'watchlist', { libraries: [], kinds: {} }, false)).toBe(false);
		expect(plexSubmitDisabled('connected', 'new', initialSelection(), true)).toBe(false);
	});
});
