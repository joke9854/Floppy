import { page } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import PlaysDialog from './PlaysDialog.svelte';
import { toIsoWithOffset, toLocalInput } from './media.ts';

const plays = [
	{ history_id: 41, end_date: '2026-03-09T08:05:00+00:00' },
	{ history_id: 40, end_date: '2026-03-01T21:15:30+00:00' }
];

function mount(props: Record<string, unknown> = {}) {
	return render(PlaysDialog, {
		props: {
			open: true,
			title: 'Alison',
			kind: 'music',
			plays,
			suggestion: { label: 'Release date', local: '1993-06-01T00:00:00' },
			body: { album_id: 7, track_id: 3, recording_id: 'rec-1' },
			onchange: vi.fn(),
			...props
		}
	});
}

describe('plays dialog', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('deletes a play after confirming, with the history id and the csrf token', async () => {
		document.cookie = 'csrftoken=test-token';
		const fetch = vi.fn(async () => new Response(null, { status: 204 }));
		vi.stubGlobal('fetch', fetch);
		vi.stubGlobal('confirm', () => true);
		mount();

		const first = page.getByRole('button', { name: /^Delete the play of/ }).first();
		await first.click();

		await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
		const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toBe('/api/v1/history/music/41/');
		expect(init.method).toBe('DELETE');
		expect((init.headers as Record<string, string>)['x-csrftoken']).toBe('test-token');
		// The deleted play leaves the list; the other stays.
		await expect.element(page.getByRole('button', { name: /^Delete the play of/ })).toBeVisible();
	});

	it('does not delete when the confirmation is refused', async () => {
		document.cookie = 'csrftoken=test-token';
		const fetch = vi.fn(async () => new Response(null, { status: 204 }));
		vi.stubGlobal('fetch', fetch);
		vi.stubGlobal('confirm', () => false);
		mount();

		await page.getByRole('button', { name: /^Delete the play of/ }).first().click();

		expect(fetch).not.toHaveBeenCalled();
	});

	it('adds a play with the exact instant and its offset, then reloads the page data', async () => {
		document.cookie = 'csrftoken=test-token';
		const fetch = vi.fn(async () => new Response('{}', { status: 201 }));
		vi.stubGlobal('fetch', fetch);
		const onchange = vi.fn();
		mount({ onchange });

		await page.getByLabelText('Played at').fill('2026-03-02T21:15:30');
		await page.getByRole('button', { name: 'Add play' }).click();

		await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
		const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toBe('/api/v1/music/songs/plays/');
		expect(init.method).toBe('POST');
		expect((init.headers as Record<string, string>)['x-csrftoken']).toBe('test-token');
		const body = JSON.parse(init.body as string);
		expect(body).toMatchObject({ album_id: 7, track_id: 3, recording_id: 'rec-1' });
		// The exact second the user picked, with the browser's offset; the same instant.
		expect(body.end_date).toMatch(/^2026-03-02T21:15:30[+-]\d\d:\d\d$/);
		expect(new Date(body.end_date).getTime()).toBe(new Date('2026-03-02T21:15:30').getTime());
		await vi.waitFor(() => expect(onchange).toHaveBeenCalledTimes(1));
	});

	it('posts a podcast play to the episodes endpoint and fills the suggestion', async () => {
		document.cookie = 'csrftoken=test-token';
		const fetch = vi.fn(async () => new Response('{}', { status: 201 }));
		vi.stubGlobal('fetch', fetch);
		mount({
			kind: 'podcast',
			plays: [],
			suggestion: { label: 'Published', local: '2026-01-05T12:00:00' },
			body: { show_id: 4, episode_id: 9 }
		});

		await expect.element(page.getByText('No plays yet.')).toBeVisible();
		await page.getByRole('button', { name: 'Published' }).click();
		await page.getByRole('button', { name: 'Add play' }).click();

		await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
		const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toBe('/api/v1/podcasts/episodes/plays/');
		const body = JSON.parse(init.body as string);
		expect(body).toMatchObject({ show_id: 4, episode_id: 9 });
		expect(body.end_date.startsWith('2026-01-05T12:00:00')).toBe(true);
	});
});

describe('instants', () => {
	it('keeps the second and the offset of a local date and time', () => {
		const local = toLocalInput(new Date(2026, 2, 1, 21, 15, 30));
		expect(local).toBe('2026-03-01T21:15:30');
		expect(toIsoWithOffset(local)).toMatch(/^2026-03-01T21:15:30[+-]\d\d:\d\d$/);
		expect(toIsoWithOffset('not a date')).toBeNull();
	});
});
