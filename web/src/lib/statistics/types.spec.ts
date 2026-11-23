import { describe, expect, it } from 'vitest';
import { chooseBucket, hoursBars, screenQuery, withQuery } from './types.ts';

describe('screenQuery', () => {
	it('forwards only the range and compare, never media-type', () => {
		const params = new URLSearchParams('start-date=2026-01-01&end-date=2026-11-23&compare=last_year&media-type=movie');
		expect(screenQuery(params)).toBe('?start-date=2026-01-01&end-date=2026-11-23&compare=last_year');
		expect(screenQuery(new URLSearchParams('media-type=tv'))).toBe('');
	});

	it('changes the page query', () => {
		const params = new URLSearchParams('media-type=tv&compare=none');
		expect(withQuery(params, { compare: null, 'start-date': 'all', 'end-date': 'all' })).toBe(
			'?media-type=tv&start-date=all&end-date=all'
		);
	});
});

describe('chooseBucket', () => {
	const days = (count: number) =>
		Array.from({ length: count }, (_, index) => {
			const date = new Date(2024, 0, 1 + index * 9);
			return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
		});

	it('keeps days for up to 45 days of data, then sizes by span', () => {
		expect(chooseBucket(days(10))).toBe('day');
		expect(chooseBucket(days(46), '2024-01-01', '2024-07-31')).toBe('week');
		expect(chooseBucket(days(46), '2023-01-01', '2024-12-31')).toBe('month');
		expect(chooseBucket(days(46), '2015-01-01', '2024-12-31')).toBe('year');
	});
});

describe('hoursBars', () => {
	it('sums days into months and keeps each type', () => {
		const days = Array.from({ length: 50 }, (_, index) => {
			const date = new Date(2024, 0, 1 + index * 7);
			return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
		});
		const bars = hoursBars(
			{
				days,
				series: [
					{ label: 'Movie', media_type: 'movie', color: '#f00', values: days.map(() => 1) },
					{ label: 'TV Show', media_type: 'tv', color: '#0f0', values: days.map(() => 0.5) }
				]
			},
			'2023-01-01',
			'2024-12-31',
			2026
		);
		expect(bars.labels[0]).toBe('Jan 2024');
		expect(bars.series[0].values[0]).toBe(5);
		expect(bars.series[1].values[0]).toBe(2.5);
		expect(bars.series[0].values.reduce((a, b) => a + b, 0)).toBe(50);
	});
});
