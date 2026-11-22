import { page } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import ActivityDialog from './ActivityDialog.svelte';

const activity = {
	media_type: 'episode',
	entries: [
		{
			id: 31,
			date: 'Nov 17, 2026 20:30',
			instance: null,
			instance_id: 9,
			changes: ['Watched'],
			delete_url: '/media/history/episode/31/delete/'
		}
	]
};

describe('activity history dialog', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('deletes an entry after confirming, edits the play it describes', async () => {
		document.cookie = 'csrftoken=test-token';
		const fetch = vi.fn(async (url: string) =>
			url.startsWith('/api/v1/activity/') ? new Response(JSON.stringify(activity)) : new Response('')
		);
		vi.stubGlobal('fetch', fetch);
		vi.stubGlobal('confirm', () => true);
		const onclose = vi.fn();
		const onedit = vi.fn();
		render(ActivityDialog, {
			props: {
				target: { mediaType: 'episode', source: 'tmdb', mediaId: '1668', season: 1, episode: 1 },
				onclose,
				onedit
			}
		});

		await expect.element(page.getByText('Watched')).toBeVisible();
		expect(fetch.mock.calls[0]?.[0]).toBe('/api/v1/activity/episode/tmdb/1668/?season_number=1&episode_number=1');
		await page.getByRole('button', { name: 'Edit the entry of Nov 17, 2026 20:30' }).click();
		expect(onedit).toHaveBeenCalledWith(9);

		await page.getByRole('button', { name: 'Delete the entry of Nov 17, 2026 20:30' }).click();
		await expect.element(page.getByText("You haven't started tracking it yet.")).toBeVisible();
		const [url, init] = fetch.mock.calls[1] as unknown as [string, RequestInit];
		expect(url).toBe('/media/history/episode/31/delete/');
		expect(init.method).toBe('DELETE');
		expect((init.headers as Record<string, string>)['x-csrftoken']).toBe('test-token');
	});
});
