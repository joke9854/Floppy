import { page } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import SessionsDialog from './SessionsDialog.svelte';

const body = {
	days: [
		{
			key: '2026-03-09',
			weekday: 'Monday',
			date: 'Mar 9, 2026',
			meta: '1 item · 7h 3m',
			more_url: '',
			remaining: 0,
			entries: [
				{
					key: 'game-1',
					media_type: 'game',
					item_id: 5,
					time: '8:05 PM',
					time_title: '',
					href: '',
					poster: '',
					square: false,
					title: 'Hades',
					code: '',
					subtitle: 'Game',
					runtime: '7h 3m',
					score: null,
					history_query: 'media_type=game',
					track: {
						media_type: 'game',
						source: 'igdb',
						media_id: '113112',
						season_number: null,
						episode_number: null,
						instance_id: 12
					}
				}
			]
		}
	],
	stats: [{ label: 'Longest streak', value: '2 days' }],
	capped: true,
	max_days: 400
};

describe('sessions dialog', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('reads the opener query, lists the days and says when it is capped', async () => {
		const fetch = vi.fn(async () => new Response(JSON.stringify(body), { status: 200 }));
		vi.stubGlobal('fetch', fetch);
		const query = 'media_type=game&media_id=113112&source=igdb&logging_style=sessions';
		render(SessionsDialog, { props: { query, onedit: vi.fn() } });

		await expect.element(page.getByText('Hades')).toBeVisible();
		expect((fetch.mock.calls[0] as unknown as [string])[0]).toBe(`/api/v1/history/sessions/?${query}`);
		await expect.element(page.getByText('Monday Mar 9, 2026')).toBeVisible();
		await expect.element(page.getByText('Longest streak')).toBeVisible();
		await expect.element(page.getByText('Showing the latest 400 days.')).toBeVisible();
	});

	it('hands the row to the track dialog on Edit', async () => {
		vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
		const onedit = vi.fn();
		render(SessionsDialog, { props: { query: 'media_type=game', onedit } });

		await page.getByRole('button', { name: 'Edit tracking' }).click();

		expect(onedit).toHaveBeenCalledWith({
			mediaType: 'game',
			source: 'igdb',
			mediaId: '113112',
			season: null,
			episode: null,
			instanceId: 12
		});
	});

	it('says so when the history cannot load', async () => {
		vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 500 })));
		render(SessionsDialog, { props: { query: 'media_type=game', onedit: vi.fn() } });

		await expect.element(page.getByRole('alert')).toHaveTextContent('could not load');
	});
});
