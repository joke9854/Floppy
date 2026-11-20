import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import Page from './+page.svelte';

const POSTER = 'data:image/gif;base64,R0lGODlhAQABAAAAACw=';

const credit = (n: number, mediaType: string, watched = false) => ({
	title: `Credit ${n}`,
	url: `/details/tmdb/${mediaType}/${n}/credit-${n}`,
	thumb: POSTER,
	year: String(2000 + n),
	role: `Role ${n}`,
	media_type: mediaType,
	type_label: mediaType === 'tv' ? 'TV Show' : 'Movie',
	departments: [],
	watched
});

const person = {
	name: 'Jane Star',
	image: POSTER,
	department: 'Acting',
	born: 'Born Jan. 1, 1990 (36)',
	place_of_birth: 'Los Angeles',
	is_author: false,
	stats: { titles: 1, movies: 1, shows: 0, books: 0, together: null },
	history_url: '/history?person_source=tmdb&person_id=1',
	source_url: 'https://www.themoviedb.org/person/1',
	source_label: 'The Movie Database',
	biography: 'A biography.',
	watched: [
		{ title: 'Credit 1', url: '/details/tmdb/movie/1/credit-1', poster: POSTER, year: '2001', media_type: 'movie', watched: true }
	],
	known_for: [],
	filmography: Array.from({ length: 25 }, (_, index) =>
		credit(index + 1, index % 2 ? 'tv' : 'movie', index === 0)
	)
};

describe('/next person page', () => {
	it('shows the person, the numbers and the first 20 credits', async () => {
		render(Page, { props: { data: { person, username: 'reader', library: [] } } as never });

		await expect.element(page.getByRole('heading', { name: 'Jane Star', level: 1 })).toBeVisible();
		await expect.element(page.getByText('1 title watched')).toBeVisible();
		await expect.element(page.getByText('All 25 credits')).toBeVisible();
		await expect.element(page.getByText('Credit 20', { exact: true })).toBeInTheDocument();
		await expect.element(page.getByText('Credit 21', { exact: true })).not.toBeInTheDocument();
		await expect
			.element(page.getByRole('link', { name: /Credit 1 / }).first())
			.toHaveAttribute('href', '/details/tmdb/movie/1/credit-1');
	});

	it('filters the filmography by type', async () => {
		render(Page, { props: { data: { person, username: 'reader', library: [] } } as never });

		await page.getByRole('tab', { name: 'Shows' }).click();

		await expect.element(page.getByText('Credit 2', { exact: true })).toBeInTheDocument();
		await expect.element(page.getByText('Credit 3', { exact: true })).not.toBeInTheDocument();
	});
});
