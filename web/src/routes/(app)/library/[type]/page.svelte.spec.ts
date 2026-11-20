import { page } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import Page from './+page.svelte';

const POSTER = 'data:image/gif;base64,R0lGODlhAQABAAAAACw=';

const card = (key: number, title: string, status: string, extra: object = {}) => ({
	key,
	media_type: 'tv',
	title,
	url: `/details/${key}`,
	poster: POSTER,
	poster_srcset: '',
	status,
	progress: null,
	subtitle: status,
	detail: '',
	repeats: null,
	cells: [],
	shape: 'poster',
	history_url: `/history?media_type=tv&media_id=${key}&source=tmdb`,
	next_episode_url: '',
	...extra
});

const screen = {
	media_type: 'tv',
	title: 'TV Shows',
	count: 2,
	in_progress: 1,
	views: [
		{ media_type: 'tv', label: 'Shows' },
		{ media_type: 'season', label: 'Seasons' }
	],
	subviews: [],
	subview: '',
	sort: 'score',
	direction: 'desc',
	sorts: [
		{ value: 'score', label: 'Rating' },
		{ value: 'title', label: 'Title' }
	],
	statuses: [],
	status_choices: [
		{ value: 'In progress', label: 'In Progress' },
		{ value: 'Completed', label: 'Completed' }
	],
	search: '',
	filters: {
		rating: 'rated',
		collection: 'all',
		progress: 'all',
		genre: '',
		implied_genre: '',
		year: '',
		completed_date_from: '',
		completed_date_to: '',
		completed_date_within: '',
		completed_date_within_unit: 'days',
		release: 'all',
		source: '',
		media_status: '',
		language: '',
		country: '',
		platforms: [],
		platform_mode: 'or',
		origin: '',
		format: '',
		author: '',
		provider: '',
		tags: [],
		tag_mode: 'or'
	},
	filter_options: {
		genres: [{ value: 'Drama', label: 'Drama' }],
		implied_genres: [],
		years: [{ value: '2024', label: '2024' }],
		sources: [],
		media_statuses: [],
		languages: [],
		countries: [],
		platforms: [],
		origins: [],
		formats: [],
		authors: [],
		providers: [],
		all_providers: [],
		relative_date_units: [{ value: 'days', label: 'Days' }],
		tags: [{ value: 'cozy', label: 'cozy', count: 2 }],
		show_progress: true,
		show_languages: false,
		show_countries: false,
		show_platforms: false,
		show_origins: false,
		show_formats: false,
		show_authors: false,
		show_providers: false
	},
	page: 1,
	has_next: false,
	layout: 'grid',
	columns: [],
	column_config: [],
	column_defaults: [],
	bulk: {
		statuses: [
			{ value: 'Completed', label: 'Completed' },
			{ value: 'Planning', label: 'Planning' }
		],
		lists: [{ value: '7', label: 'Weekend' }],
		tags: ['cozy']
	},
	entry_grouping: null,
	results: [
		card(1, 'Severance', 'In progress', {
			subtitle: 'S2 E3 next',
			progress: { percent: 40, paused: false },
			detail: '8.5/10'
		}),
		card(2, 'The Bear', 'Completed')
	]
};

const renderLibrary = (overrides: object = {}) =>
	render(Page, {
		props: {
			data: {
				screen: { ...screen, ...overrides },
				username: 'reader',
				library: [
					{ media_type: 'tv', label: 'TV Shows' },
					{ media_type: 'music', label: 'Music' },
					{ media_type: 'episode', label: 'Episodes' }
				]
			}
		} as never
	});

describe('/next Library', () => {
	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it('shows the header, the menus and the cards', async () => {
		renderLibrary();

		await expect.element(page.getByText('2 tv shows · 1 in progress')).toBeVisible();
		await expect
			.element(page.getByRole('link', { name: 'Shows', exact: true }))
			.toHaveAttribute('aria-current', 'page');
		// The test browser is phone-sized: the status segment is the Status menu there.
		await expect.element(page.getByRole('button', { name: 'Status' })).toHaveTextContent('All');
		await expect.element(page.getByRole('button', { name: 'Sort' })).toHaveTextContent('Rating');
		await expect.element(page.getByText('Severance')).toBeVisible();
		await expect.element(page.getByText('S2 E3 next')).toBeVisible();
		await expect.element(page.getByText('8.5/10')).toBeVisible();
		await expect.element(page.getByTitle('Completed')).toBeVisible();
	});

	it('opens the filter menu on its root list, with the active filter', async () => {
		renderLibrary();

		const trigger = page.getByRole('button', { name: 'Filter', exact: true });
		await expect.element(trigger).toHaveAttribute('data-active', 'true');
		await trigger.click();

		await expect.element(page.getByRole('button', { name: /^Rating/ })).toHaveTextContent('Rated');
		await expect.element(page.getByRole('button', { name: /^Genre/ })).toBeVisible();
		await expect.element(page.getByRole('button', { name: /^Tag/ })).toBeVisible();
		await page.getByRole('button', { name: /^Genre/ }).click();
		await expect.element(page.getByRole('button', { name: 'Drama' })).toBeVisible();
	});

	it('adds the next page as the grid scrolls', async () => {
		const next = {
			...screen,
			page: 2,
			has_next: false,
			results: [card(3, 'Shogun', 'Planning')]
		};
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => new Response(JSON.stringify(next), { status: 200 }))
		);
		renderLibrary({ has_next: true });

		document.querySelector('.ct-library-more')?.scrollIntoView();

		// The second page is shown, not only fetched (a proxied state once lost it).
		await expect.element(page.getByText('Shogun')).toBeVisible();
		await expect.element(page.getByText('Severance')).toBeVisible();
	});

	it('links music to the web Library and unknown types to Django', async () => {
		renderLibrary();

		await expect
			.element(page.getByRole('link', { name: 'Music' }))
			.toHaveAttribute('href', '/library/music');
		await expect
			.element(page.getByRole('link', { name: 'Episodes' }))
			.toHaveAttribute('href', '/medialist/episode');
	});

	it('draws the table layout with the cells and notes', async () => {
		const cell = (key: string, text: string | null, note: string | null = null, items: string[] = []) => ({
			key,
			text,
			note,
			items
		});
		renderLibrary({
			layout: 'table',
			columns: [
				{ key: 'image', label: '', align: 'start', role: 'image' },
				{ key: 'title', label: 'Title', align: 'start', role: 'title' },
				{ key: 'score', label: 'Score', align: 'center', role: 'score' },
				{ key: 'progress', label: 'Progress', align: 'center', role: 'text' },
				{ key: 'genres', label: 'Genres', align: 'start', role: 'list' }
			],
			column_config: [{ key: 'score', label: 'Score', visible: true }],
			column_defaults: [{ key: 'score', label: 'Score', visible: true }],
			results: [
				card(1, 'Severance', 'In progress', {
					repeats: 2,
					cells: [
						cell('score', '8.5', 'Latest'),
						cell('progress', '19', 'Total (2 repeats)'),
						cell('genres', null, null, ['Drama', 'Mystery'])
					]
				}),
				card(2, 'The Bear', 'Completed', {
					cells: [cell('score', null), cell('progress', null), cell('genres', null)]
				})
			]
		});

		await expect.element(page.getByRole('columnheader', { name: 'Progress' })).toBeVisible();
		await expect.element(page.getByRole('link', { name: 'Severance' })).toHaveAttribute('href', '/details/1');
		await expect.element(page.getByText('Total (2 repeats)')).toBeVisible();
		await expect.element(page.getByText('Latest')).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'Mystery' })).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'Table' })).toHaveAttribute('aria-pressed', 'true');
		await expect.element(page.getByRole('button', { name: 'Columns' })).toBeVisible();
		expect(document.querySelector('.ct-library-grid')).toBeNull();
	});

	it('selects cards and posts a bulk status to the page endpoint', async () => {
		const fetch = vi.fn(
			async () => new Response(JSON.stringify({ success: true, message: 'Updated 1 item(s).' }))
		);
		vi.stubGlobal('fetch', fetch);
		document.cookie = 'csrftoken=test-token';
		renderLibrary();

		await page.getByRole('button', { name: 'View settings' }).click();
		await page.getByRole('menuitem', { name: 'Select Items' }).click();
		await page.getByRole('button', { name: /Severance/ }).click();

		await expect.element(page.getByText('1 selected')).toBeVisible();
		await page.getByRole('button', { name: 'Update Status' }).click();
		await page.getByRole('menuitem', { name: 'Completed' }).click();

		await expect.poll(() => fetch.mock.calls.length).toBeGreaterThan(0);
		const [path, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
		expect(path).toBe('/bulk/status');
		expect(String(init.body)).toBe('item_ids=1&status=Completed');
	});

	it('shows the card menu and the Next ep link', async () => {
		renderLibrary({
			results: [card(1, 'Severance', 'In progress', { next_episode_url: '/details/tmdb/tv/1/s/season/2/episode/4' })]
		});

		await expect.element(page.getByRole('link', { name: /Next ep/ })).toBeInTheDocument();
		await page.getByRole('button', { name: 'Actions for Severance' }).click();
		await expect.element(page.getByRole('menuitem', { name: 'Edit tracking' })).toBeVisible();
		await expect.element(page.getByRole('menuitem', { name: 'View your activity history' })).toBeVisible();
		await expect.element(page.getByRole('menuitem', { name: /Add to List/ })).toBeVisible();
	});

	it('switches music views and draws square art', async () => {
		renderLibrary({
			media_type: 'music',
			title: 'Music',
			views: [],
			subviews: [
				{ value: 'artists', label: 'Artists' },
				{ value: 'albums', label: 'Albums' },
				{ value: 'tracks', label: 'Tracks' }
			],
			subview: 'artists',
			bulk: null,
			results: [card(9, 'Björk', 'Completed', { media_type: 'music', shape: 'square' })]
		});

		await expect
			.element(page.getByRole('button', { name: 'Artists' }))
			.toHaveAttribute('aria-pressed', 'true');
		expect(document.querySelector('[data-shape="square"]')).not.toBeNull();
	});

	it('says when nothing matches', async () => {
		renderLibrary({ count: 0, in_progress: 0, results: [], search: 'zzz' });

		await expect.element(page.getByText('No tv shows match.')).toBeVisible();
	});
});
