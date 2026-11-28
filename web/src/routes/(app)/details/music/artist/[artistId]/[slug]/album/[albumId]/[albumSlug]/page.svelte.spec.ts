import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import Page from './+page.svelte';
// The Plays dialog loads with import() on the page; load it before the tests run.
await import('#lib/details/PlaysDialog.svelte');

const ART = 'data:image/gif;base64,R0lGODlhAQABAAAAACw=';

const screen = {
	album: {
		id: 9,
		title: 'Souvlaki',
		image: ART,
		url: '/details/music/artist/7/slowdive-7/album/9/souvlaki-9/',
		artists: [{ id: 7, name: 'Slowdive', url: '/details/music/artist/7/slowdive-7/' }],
		musicbrainz_url: null
	},
	activity: { primary_text: 'Progress: 1/2', date_start: null, date_end: null },
	tracker: null,
	genres: [{ name: 'Shoegaze', url: '/medialist/music?genre=Shoegaze' }],
	details: [
		{ label: 'Format', value: 'Album' },
		{ label: 'Tracks', value: '2' }
	],
	release: null,
	tracks: [
		{
			track_id: 1,
			recording_id: 'rec-1',
			title: 'Alison',
			disc: 1,
			number: 1,
			duration: '3:53',
			music_id: 5,
			play_count: 2,
			last_played: '2026-03-09T08:05:00+00:00',
			plays: [
				{ history_id: 12, end_date: '2026-03-09T08:05:00+00:00' },
				{ history_id: 11, end_date: '2026-03-01T21:15:30+00:00' }
			]
		},
		{
			track_id: 2,
			recording_id: 'rec-2',
			title: 'Machine Gun',
			disc: 1,
			number: 2,
			duration: '4:23',
			music_id: null,
			play_count: 0,
			last_played: null,
			plays: []
		}
	],
	total_tracks: 2,
	total_runtime: '8m',
	release_date: '1993-06-01',
	history_url: '/history?album=9',
	sync_url: '/api/v1/music/albums/9/resync/',
	links: []
};

describe('/next album page', () => {
	it('lists the tracks with their play counts, and opens a track\'s plays', async () => {
		render(Page, { props: { data: { screen } } as never });

		await expect.element(page.getByRole('heading', { name: 'Souvlaki' })).toBeVisible();
		await expect.element(page.getByRole('link', { name: 'Slowdive' })).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'Track' })).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'Sync' })).toBeVisible();
		await expect.element(page.getByText('Progress: 1/2')).toBeVisible();
		await expect.element(page.getByText(/3:53 · 2 plays/)).toBeVisible();
		await expect.element(page.getByText('4:23')).toBeVisible();

		await page.getByRole('button', { name: 'Plays of Alison' }).click();
		await expect.element(page.getByRole('heading', { name: 'Plays: Alison' })).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'Add play' })).toBeVisible();
	});
});
