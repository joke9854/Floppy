import { page } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
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
	graphs: [],
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
	info: [{ label: 'Status', value: 'Ended' }],
	// Empty for a movie or show (P4-L1).
	issues: [],
	issues_more: null,
	// Empty unless a flat MAL anime (P4-L3a).
	flat_episodes: [],
	flat_more: null,
	flat_note: '',
	game_lengths: null,
	authors: [],
	studios: [],
	genres: []
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
	afterEach(() => vi.unstubAllGlobals());

	it('shows the hero, the next episode and the Track button', async () => {
		renderDetail();

		await expect.element(page.getByRole('heading', { name: 'Test Show', level: 1 })).toBeVisible();
		await expect.element(page.getByText('2 Seasons')).toBeVisible();
		await expect
			.element(page.getByRole('button', { name: 'Mark S1 E2 as watched' }))
			.toBeVisible();
		// Track opens the web track dialog (P4-D1), no longer the Django page.
		await expect.element(page.getByRole('button', { name: 'Track' })).toBeVisible();
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

	it('shows a book with its series and progress, a Track button and no primary action', async () => {
		renderDetail(
			{
				media_type: 'book',
				source: 'openlibrary',
				media_id: 'OL1W',
				title: 'Test Book',
				action: null,
				meta: {
					type_label: 'Book',
					genres: ['Fantasy'],
					year: '1999',
					runtime: null,
					certification: null,
					seasons: null,
					percent: null,
					series: 'The Cycle #2',
					progress: 'Progress: 120/300'
				}
			},
			{
				...sections,
				sections: ['details', 'genres'],
				seasons: [],
				season: null,
				info: [{ label: 'Format', value: 'Hardcover' }],
				authors: [{ name: 'A. Writer', url: '/person/openlibrary/OL9A/a-writer' }],
				genres: [{ name: 'Fantasy', url: '/medialist/book?genre=Fantasy' }],
				studios: [],
				issues: [],
				issues_more: null,
				game_lengths: null
			}
		);

		await expect.element(page.getByText('The Cycle #2')).toBeVisible();
		await expect.element(page.getByText('Progress: 120/300')).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'Track' })).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'Mark as watched' })).not.toBeInTheDocument();
		await expect.element(page.getByText('Hardcover')).toBeVisible();
		await expect.element(page.getByRole('link', { name: 'A. Writer' })).toBeVisible();
		await expect.element(page.getByRole('link', { name: 'Fantasy', exact: true })).toBeVisible();
	});

	it('lists a comic volume\'s issues with a Read mark and a way to load more', async () => {
		const issue = (number: number, read: boolean) => ({
			number: String(number),
			title: `Issue title ${number}`,
			image: POSTER,
			cover_date: `2020-01-0${number}`,
			read,
			url: `/details/comicvine/comicissue/4000-${number}/issue-title-${number}`,
			media_type: 'comicissue',
			source: 'comicvine',
			media_id: `4000-${number}`
		});
		renderDetail(
			{ media_type: 'comic', source: 'comicvine', media_id: '4050-1', title: 'Test Volume', action: null },
			{
				...sections,
				sections: ['episodes'],
				seasons: [],
				season: null,
				issues: [issue(1, true), issue(2, false)],
				issues_more: { page: 2, label: 'Issues 3 to 4' },
				game_lengths: null,
				authors: [],
				genres: [],
				studios: []
			}
		);

		await expect.element(page.getByRole('heading', { name: 'Issues' })).toBeVisible();
		await expect.element(page.getByText('Issue title 1')).toBeVisible();
		await expect.element(page.getByText('Issue #2 · 2020-01-02')).toBeVisible();
		await expect.element(page.getByText('Read', { exact: true })).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'Show Issues 3 to 4' })).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'Track Issue title 2' })).toBeVisible();
	});

	it('checks an anime episode into the anime bucket', async () => {
		document.cookie = 'csrftoken=test-token';
		// The save answers `created`; the page then re-reads its hero and season.
		const answer = (url: string) => {
			if (url.includes('/episodes/ensure/')) return { results: [{ status: 'created' }] };
			if (url.includes('/trailers/')) return { trailers: [] };
			if (url.includes('/season/')) return sections.season;
			return shell({ media_type: 'anime', action: null });
		};
		const fetch = vi.fn(
			async (url: string, _init?: RequestInit) =>
				new Response(JSON.stringify(answer(String(url))), { status: 200 })
		);
		vi.stubGlobal('fetch', fetch);
		const animeEpisode = (number: number) => ({
			...episode(number, false),
			url: `/details/tmdb/anime/1399/test-show/season/1/episode/${number}`,
			check: {
				source: 'tmdb',
				media_id: '1399',
				season_number: 1,
				episode_number: number,
				library_media_type: 'anime'
			}
		});
		renderDetail(
			{ media_type: 'anime', action: null },
			{ ...sections, season: { ...sections.season, episodes: [animeEpisode(1), animeEpisode(2)] } }
		);

		await page.getByRole('button', { name: 'Mark E2 Episode 2 as watched' }).click();

		await vi.waitFor(() =>
			expect(fetch.mock.calls.some(([url]) => String(url).includes('/episodes/ensure/'))).toBe(true)
		);
		const call = fetch.mock.calls.find(([url]) => String(url).includes('/episodes/ensure/'))!;
		expect(String(call[0])).toBe('/api/v1/media/tv/tmdb/1399/episodes/ensure/');
		const body = JSON.parse(String(call[1]?.body));
		expect(body.library_media_type).toBe('anime');
		expect(body.events[0].episode_number).toBe(2);
	});

	it('lists a flat MAL anime mapped episodes without a check', async () => {
		renderDetail(
			{ media_type: 'anime', source: 'mal', media_id: '52991', title: 'Frieren', action: null },
			{
				...sections,
				sections: ['episodes'],
				seasons: [],
				season: null,
				flat_episodes: [
					{
						...episode(1, false),
						title: 'Mapped 1',
						check: null,
						url: '/details/tvdb/anime/9350138/frieren/season/1/episode/1'
					}
				],
				flat_note: 'This entry maps to TVDB Season 1.'
			}
		);

		await expect.element(page.getByText('Mapped 1')).toBeVisible();
		await expect.element(page.getByText('This entry maps to TVDB Season 1.')).toBeVisible();
		await expect.element(page.getByRole('button', { name: /as watched/ })).not.toBeInTheDocument();
		await expect.element(page.getByRole('button', { name: 'Track' })).toBeVisible();
	});

	it('says when the sections could not load', async () => {
		renderDetail({}, null);

		await expect.element(page.getByText('This part of the page could not load.')).toBeVisible();
	});
});
