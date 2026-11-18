import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
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
	it('shows the header, the menus and the cards', async () => {
		renderLibrary();

		await expect.element(page.getByText('2 tv shows · 1 in progress')).toBeVisible();
		await expect
			.element(page.getByRole('link', { name: 'Shows', exact: true }))
			.toHaveAttribute('aria-current', 'page');
		await expect
			.element(page.getByRole('button', { name: 'All', exact: true }))
			.toHaveAttribute('aria-pressed', 'true');
		await expect.element(page.getByRole('button', { name: 'Sort' })).toHaveTextContent('Rating');
		await expect.element(page.getByText('Severance')).toBeVisible();
		await expect.element(page.getByText('S2 E3 next')).toBeVisible();
		await expect.element(page.getByText('8.5/10')).toBeVisible();
		await expect.element(page.getByTitle('Completed')).toBeVisible();
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
