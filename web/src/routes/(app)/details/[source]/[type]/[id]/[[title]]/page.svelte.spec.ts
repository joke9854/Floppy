import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import Page from './+page.svelte';
// The sections load with import() on the page; load them before the tests run.
await import('#lib/details/Sections.svelte');

const POSTER = 'data:image/gif;base64,R0lGODlhAQABAAAAACw=';

const shell = (overrides: object = {}) => ({
	media_type: 'tv',
	source: 'tmdb',
	media_id: '1399',
	title: 'Test Show',
	page_url: '/details/tmdb/tv/1399/test-show',
	poster: POSTER,
	poster_srcset: '',
	backdrop: null,
	fanart_poster: null,
	logo: null,
	links: [{ title: 'Links', links: [{ label: 'IMDb', url: 'https://imdb.test/tt1', logo: null, fallback: 'IMDB' }] }],
	meta: {
		type_label: 'TV Show',
		genres: ['Drama'],
		year: '2011',
		runtime: null,
		certification: null,
		seasons: 2,
		percent: 25
	},
	scores: [{ key: 'provider', label: 'The Movie Database', short: 'TMDB', rating: '8.4', count: 1200 }],
	my_score: null,
	status: 'In progress',
	action: {
		kind: 'episode',
		episode: {
			source: 'tmdb',
			media_id: '1399',
			season_number: 1,
			episode_number: 2,
			library_media_type: 'season'
		}
	},
	synopsis: 'Houses at war.',
	watch_on: null,
	track_time: true,
	...overrides
});

const episode = (number: number, watched: boolean) => ({
	episode_number: number,
	display_number: String(number),
	title: `Episode ${number}`,
	still: POSTER,
	still_srcset: '',
	placeholder: false,
	air_date: 'April 17, 2011',
	aired: true,
	runtime: '55m',
	overview: '',
	blurred: false,
	watched,
	history: watched ? 'Watched' : '',
	is_next: !watched,
	url: `/details/tmdb/tv/1399/test-show/season/1/episode/${number}`,
	check: {
		source: 'tmdb',
		media_id: '1399',
		season_number: 1,
		episode_number: number,
		library_media_type: 'episode'
	}
});

const sections = {
	backdrop: null,
	watch_on: null,
	sections: ['episodes', 'cast', 'details'],
	seasons: [
		{ number: 1, label: 'Season 1', short: 'S1', image: null, current: true },
		{ number: 2, label: 'Season 2', short: 'S2', image: null, current: false }
	],
	season: {
		number: 1,
		info: {
			title: 'Season 1',
			poster: null,
			year: '2011',
			episodes: 2,
			runtime: null,
			score: null,
			synopsis: '',
			cast: []
		},
		progress: { watched: 1, total: 2, percent: 50, dashes: [] },
		episodes: [episode(1, true), episode(2, false)],
		load_more: null
	},
	plays: [],
	history_url: '/history',
	related: [],
	cast: [
		{
			name: 'Sean Bean',
			role: 'Ned Stark',
			image: null,
			character_image: null,
			url: '/person/tmdb/1/sean-bean'
		}
	],
	crew: [
		{ name: 'David Benioff', role: 'Creator', image: null, character_image: null, url: null }
	],
	fanart_poster: null,
	logo: null,
	cast_view_all_url: null,
	recommendations: [],
	info: [{ label: 'Status', value: 'Ended' }]
};

const renderDetail = (shellOverrides: object = {}, sectionsValue: object | null = sections) =>
	render(Page, {
		props: {
			data: {
				shell: shell(shellOverrides),
				sections: Promise.resolve(sectionsValue),
				username: 'reader',
				library: []
			}
		} as never
	});

describe('/next detail page', () => {
	it('shows the hero, the next episode and the Django page for the rest', async () => {
		renderDetail();

		await expect.element(page.getByRole('heading', { name: 'Test Show', level: 1 })).toBeVisible();
		await expect.element(page.getByText('2 Seasons')).toBeVisible();
		await expect
			.element(page.getByRole('button', { name: 'Mark S1 E2 as watched' }))
			.toBeVisible();
		await expect
			.element(page.getByRole('link', { name: 'Track' }))
			.toHaveAttribute('href', '/details/tmdb/tv/1399/test-show');
	});

	it('lists the season, the cast and the information once the sections load', async () => {
		renderDetail();

		await expect.element(page.getByText('1 of 2 episodes watched')).toBeVisible();
		await expect.element(page.getByText('Episode 2')).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'Watched', exact: true })).toBeVisible();
		await expect.element(page.getByText('Ned Stark')).toBeVisible();
		await page.getByRole('tab', { name: 'Crew' }).click();
		await expect.element(page.getByText('David Benioff')).toBeVisible();
		await expect.element(page.getByText('Ended')).toBeVisible();
	});

	it('posts the Django form to mark an untracked movie', async () => {
		renderDetail({ media_type: 'movie', action: { kind: 'mark', episode: null } }, {
			...sections,
			sections: ['details'],
			seasons: [],
			season: null
		});

		const button = page.getByRole('button', { name: 'Mark as watched' });
		await expect.element(button).toBeVisible();
		await expect.element(button).toBeEnabled();
	});

	it('says when the sections could not load', async () => {
		renderDetail({}, null);

		await expect.element(page.getByText('This part of the page could not load.')).toBeVisible();
	});
});
