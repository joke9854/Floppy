import { page } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import RatingsGraph from './RatingsGraph.svelte';

const graph = {
	title: 'Episode Ratings',
	row_label: 'E',
	seasons: [
		{ label: 'S1', episodes: 2 },
		{ label: 'S2', episodes: 1 }
	],
	rows: [
		{
			episode: 1,
			cells: [
				{ score: 8.8, votes: 1200, color: '#2d9e5f' },
				{ score: 7.1, votes: 1, color: '#c9970a' }
			]
		},
		{
			episode: 2,
			cells: [
				{ score: 9.4, votes: 15, color: '#1d6e3e' },
				{ score: null, votes: null, color: null }
			]
		}
	],
	legend: [{ label: 'Awesome', color: '#1d6e3e' }]
};

describe('ratings graph', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('draws the heatmap from the graphs read with the votes in each cell title', async () => {
		const fetch = vi.fn(
			async () => new Response(JSON.stringify({ provider: graph, trakt: null, imdb: null }), { status: 200 })
		);
		vi.stubGlobal('fetch', fetch);
		const url = '/api/v1/details/tv/tmdb/1396/graphs/';
		render(RatingsGraph, { props: { kind: 'provider', url } });

		await expect.element(page.getByText('9.4')).toBeVisible();
		expect((fetch.mock.calls[0] as unknown as [string])[0]).toBe(url);
		await expect.element(page.getByText('S2')).toBeVisible();
		await expect.element(page.getByText('E2')).toBeVisible();
		expect(document.querySelector('[title="8.8 · 1,200 votes"]')).not.toBeNull();
		expect(document.querySelector('[title="7.1 · 1 vote"]')).not.toBeNull();
		await expect.element(page.getByText('Awesome')).toBeVisible();
	});

	it('says so when the kind has nothing stored', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => new Response(JSON.stringify({ provider: null, trakt: null, imdb: null }), { status: 200 }))
		);
		render(RatingsGraph, { props: { kind: 'trakt', url: '/x/' } });

		await expect.element(page.getByText('No ratings stored yet.')).toBeVisible();
	});
});
