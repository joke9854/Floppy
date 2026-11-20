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
					{ media_type: 'music', label: 'Music' }
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

	it('links types without a web Library to the Django page', async () => {
		renderLibrary();

		await expect
			.element(page.getByRole('link', { name: 'Music' }))
			.toHaveAttribute('href', '/medialist/music');
	});

	it('says when nothing matches', async () => {
		renderLibrary({ count: 0, in_progress: 0, results: [], search: 'zzz' });

		await expect.element(page.getByText('No tv shows match.')).toBeVisible();
	});
});
