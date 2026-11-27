import { describe, expect, it } from 'vitest';
import { mediaTypesForm, moveEntry, notificationsForm, readAnswer } from './types.ts';

describe('moveEntry', () => {
	it('swaps with the neighbour and ignores the ends', () => {
		expect(moveEntry(['a', 'b', 'c'], 1, -1)).toEqual(['b', 'a', 'c']);
		expect(moveEntry(['a', 'b', 'c'], 1, 1)).toEqual(['a', 'c', 'b']);
		expect(moveEntry(['a', 'b'], 0, -1)).toEqual(['a', 'b']);
		expect(moveEntry(['a', 'b'], 1, 1)).toEqual(['a', 'b']);
	});
});

describe('mediaTypesForm', () => {
	it('posts the enabled types, the whole order and the overlay box', () => {
		const types = [
			{ value: 'tv', label: 'TV Shows', enabled: true },
			{ value: 'movie', label: 'Movies', enabled: false },
			{ value: 'anime', label: 'Anime', enabled: true }
		];
		expect(mediaTypesForm(types, true)).toEqual({
			media_types_checkboxes: ['tv', 'anime'],
			sidebar_media_type_order: 'tv,movie,anime',
			clickable_media_cards: 'on'
		});
		expect('clickable_media_cards' in mediaTypesForm(types, false)).toBe(false);
	});
});

describe('notificationsForm', () => {
	it('posts every field, checkboxes only when set', () => {
		expect(
			notificationsForm({
				notification_urls: 'json://x',
				daily_digest_enabled: true,
				release_notifications_enabled: false,
				premiere_notifications_enabled: true
			})
		).toEqual({ notification_urls: 'json://x', daily_digest_enabled: 'on', premiere_notifications_enabled: 'on' });
	});
});

describe('readAnswer', () => {
	it('reads saved and errors', async () => {
		expect(await readAnswer(new Response(JSON.stringify({ saved: true }), { status: 200 }))).toEqual({
			saved: true,
			errors: undefined,
			message: undefined
		});
		const bad = await readAnswer(new Response(JSON.stringify({ saved: false, errors: { username: ['Taken'] } }), { status: 400 }));
		expect(bad.saved).toBe(false);
		expect(bad.errors).toEqual({ username: ['Taken'] });
		expect((await readAnswer(new Response('<html>', { status: 500 }))).saved).toBe(false);
	});
});
