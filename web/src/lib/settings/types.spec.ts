import { describe, expect, it } from 'vitest';
import { downloadName, mediaTypesForm, moveEntry, notificationsForm, preferencesForm, readAnswer } from './types.ts';

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

describe('preferencesForm', () => {
	it('posts every value and derives auto-pause from the rules', () => {
		const form = preferencesForm({ rating_scale: '5', watch_provider_region: 'GB' }, [{ library: 'all', weeks: 8 }]);
		expect(form).toEqual({
			rating_scale: '5',
			watch_provider_region: 'GB',
			auto_pause_enabled: '1',
			auto_pause_rules: '[{"library":"all","weeks":8}]'
		});
		expect(preferencesForm({}, []).auto_pause_enabled).toBe('0');
		expect(preferencesForm({}, [{ library: 'tv', weeks: 0 }]).auto_pause_rules).toBe('[{"library":"tv","weeks":1}]');
	});
});

describe('readAnswer', () => {
	it('reads an answers_json failure', async () => {
		const answer = await readAnswer(new Response(JSON.stringify({ saved: false, error: 'Nope.' }), { status: 400 }));
		expect(answer).toMatchObject({ saved: false, message: 'Nope.' });
	});
	it('fails a bare refusal', async () => {
		expect((await readAnswer(new Response('', { status: 403 }))).saved).toBe(false);
	});
});

describe('downloadName', () => {
	it('reads the attachment name', () => {
		const response = new Response('', { headers: { 'content-disposition': 'attachment; filename="floppy_2026.csv"' } });
		expect(downloadName(response, 'x.csv')).toBe('floppy_2026.csv');
		expect(downloadName(new Response(''), 'x.csv')).toBe('x.csv');
	});
});
