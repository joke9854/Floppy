import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import Page from './+page.svelte';

const POSTER = 'data:image/gif;base64,R0lGODlhAQABAAAAACw=';

const emptyHome = {
	summary: { catch_up: 0, catch_up_shows: 0, airing_count: 0 },
	in_progress: [],
	in_progress_kinds: [],
	airing: [],
	recent: [],
	coming_soon: []
};

const progressCard = (key: number, kind: 'movie' | 'show', title: string) => ({
	key,
	kind,
	media_type: kind === 'movie' ? 'movie' : 'tv',
	title,
	url: `/details/${key}`,
	poster: POSTER,
	poster_srcset: '',
	backdrop: null,
	progress_percent: 40,
	episode: kind === 'show' ? { season_number: 2, episode_number: 5, title: 'The One' } : null,
	check:
		kind === 'show'
			? {
					source: 'tmdb',
					media_id: String(key),
					season_number: 2,
					episode_number: 5,
					library_media_type: 'tv'
				}
			: null,
	time_left: null,
	episodes_left: kind === 'show' ? 3 : null,
	remaining_seconds: kind === 'movie' ? 5400 : null,
	remaining_label: kind === 'movie' ? '1h 30m' : null,
	is_rewatch: false,
	year: null
});

const release = (key: number, day: string, tag: 'premiere' | 'finale' | null) => ({
	key,
	title: `Show ${key}`,
	url: `/episode/${key}`,
	poster: POSTER,
	poster_srcset: '',
	day,
	is_today: false,
	time: '21:00',
	label: `S1 E${key}`,
	tag
});

const renderHome = (home: object) =>
	render(Page, { props: { data: { home, username: 'reader', library: [] } } as never });

describe('/next Home', () => {
	it('shows the empty state when no section has entries', async () => {
		renderHome(emptyHome);

		await expect.element(page.getByRole('heading', { level: 1 })).toHaveTextContent('Home');
		await expect.element(page.getByText('Nothing to show yet')).toBeVisible();
	});

	it('shows the header counts and every section with its cards', async () => {
		renderHome({
			summary: { catch_up: 4, catch_up_shows: 2, airing_count: 3 },
			in_progress: [progressCard(1, 'show', 'Friends'), progressCard(2, 'movie', 'Heat')],
			in_progress_kinds: ['movie', 'show'],
			airing: [release(9, '2026-11-18', null), release(10, '2026-11-19', 'finale')],
			recent: [
				{
					key: 3,
					media_type: 'movie',
					title: 'Alien',
					url: '/details/3',
					poster: POSTER,
					poster_srcset: '',
					subtitle: 'Yesterday',
					status: 'Completed',
					progress: null
				}
			],
			coming_soon: [release(1, '2026-12-01', 'premiere')]
		});

		await expect.element(page.getByText('4 episodes to catch up on across 2 shows')).toBeVisible();
		await expect.element(page.getByText('3 airing this week')).toBeVisible();
		await expect
			.element(page.getByRole('button', { name: 'Mark Friends S2 E5 watched' }))
			.toBeVisible();
		await expect.element(page.getByText('S2 E5')).toBeVisible();
		await expect.element(page.getByText('1h 30m left')).toBeVisible();
		await expect.element(page.getByRole('heading', { name: 'Airing This Week' })).toBeVisible();
		await expect.element(page.getByText('Finale', { exact: true })).toBeVisible();
		await expect.element(page.getByText('Yesterday')).toBeVisible();
		await expect.element(page.getByText('Tue 1 Dec')).toBeVisible();
		await expect.element(page.getByText('Premiere', { exact: true })).toBeVisible();
	});

	it('filters In Progress by type', async () => {
		renderHome({
			...emptyHome,
			in_progress: [progressCard(1, 'show', 'Friends'), progressCard(2, 'movie', 'Heat')],
			in_progress_kinds: ['movie', 'show']
		});

		await page.getByRole('button', { name: 'Movies' }).click();

		await expect.element(page.getByRole('link', { name: 'Heat' })).toBeVisible();
		await expect.element(page.getByRole('link', { name: 'Friends' })).not.toBeInTheDocument();
	});
});
