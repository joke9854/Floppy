import { describe, expect, it } from 'vitest';
import { allOn, exportUrl, filterLabel, loadFilter, shows, type FilterType } from './filter.ts';

const types: FilterType[] = [
	{
		value: 'movie',
		label: 'Movie',
		in_month: true,
		statuses: [
			{ value: 'Planning', label: 'Planning' },
			{ value: 'In progress', label: 'In Progress' }
		],
		month_statuses: ['Planning']
	},
	{ value: 'tv', label: 'TV Show', in_month: false, statuses: [], month_statuses: [] }
];

const release = (media_type: string, status: string) =>
	({ media_type, status }) as Parameters<typeof shows>[0];

describe('calendar filter', () => {
	it('starts with everything on and reads the page saved filter', () => {
		expect(filterLabel(types, allOn(types))).toBe('All Types');
		const saved = loadFilter(
			JSON.stringify({ selectedMediaTypes: ['movie', 'gone'], selectedStatusesByType: { movie: ['Planning', 'x'] } }),
			types
		);
		expect(saved.selectedMediaTypes).toEqual(['movie']);
		expect(saved.selectedStatusesByType).toEqual({ movie: ['Planning'], tv: [] });
		expect(filterLabel(types, saved)).toBe('Movie ·');
		expect(loadFilter('{broken', types)).toEqual(allOn(types));
	});

	it('hides a release by type or by its status, as the page', () => {
		const filter = { selectedMediaTypes: ['movie'], selectedStatusesByType: { movie: ['Planning'] } };
		expect(shows(release('movie', 'Planning'), filter)).toBe(true);
		expect(shows(release('movie', 'In progress'), filter)).toBe(false);
		expect(shows(release('movie', ''), filter)).toBe(true);
		expect(shows(release('tv', ''), filter)).toBe(false);
		expect(filterLabel(types, { selectedMediaTypes: [], selectedStatusesByType: {} })).toBe('No Types');
	});

	it('writes the export link with repeated params', () => {
		expect(exportUrl('https://x/calendar/download/t', ['tv', 'movie'], ['Planning'])).toBe(
			'https://x/calendar/download/t?media_types=tv&media_types=movie&status=Planning'
		);
		expect(exportUrl('https://x/c', [], [])).toBe('https://x/c');
	});
});
