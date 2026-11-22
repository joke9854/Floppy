import { describe, expect, it } from 'vitest';
import { actionFields, discoverQuery, rebuildDone, stillRefreshing } from './types.ts';

describe('discoverQuery', () => {
	it('writes a type tab and the rest of the rows as the page does', () => {
		expect(discoverQuery('movie')).toBe('?media_type=movie');
		expect(discoverQuery('all', true)).toBe('?media_type=all&show_more=1');
	});
});

describe('actionFields', () => {
	it('posts the card fields with the action and no debug', () => {
		const fields = {
			candidate_media_type: 'movie',
			identity_media_type: '',
			library_media_type: '',
			source: 'tmdb',
			media_id: '603',
			season_number: '',
			active_media_type: 'all',
			show_more: '0',
			row_key: 'top_picks_for_you',
			title: 'The Matrix',
			image: 'https://image.tmdb.org/t/p/w500/m.jpg',
			release_date: '1999-03-31'
		};
		expect(actionFields('dismiss', fields)).toEqual({ action: 'dismiss', ...fields, discover_debug: '0' });
	});
});

describe('stillRefreshing', () => {
	it('waits while a rebuild runs or is scheduled', () => {
		expect(stillRefreshing({ is_refreshing: true })).toBe(true);
		expect(stillRefreshing({ refresh_scheduled: true })).toBe(true);
		expect(stillRefreshing({ is_refreshing: false, refresh_scheduled: false })).toBe(false);
	});
});

describe('rebuildDone', () => {
	it('needs fresh rows after a manual Refresh, any rows otherwise', () => {
		const built = { exists: true, is_stale: false, recently_built: true };
		expect(rebuildDone({ ...built, is_refreshing: true }, true)).toBe(false);
		expect(rebuildDone(built, true)).toBe(true);
		expect(rebuildDone({ ...built, recently_built: false }, true)).toBe(false);
		expect(rebuildDone({ ...built, recently_built: false }, false)).toBe(true);
		expect(rebuildDone({ exists: false }, false)).toBe(false);
	});
});
