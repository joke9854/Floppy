import { describe, expect, it } from 'vitest';
import { consumptionTiles, ratingBars, rhythmTiers, statusSlices } from './charts.ts';

const status = {
	labels: ['TV Show', 'Movie'],
	series: [
		{ label: 'Completed', media_type: '', color: '#0f0', values: [0, 20] },
		{ label: 'Planning', media_type: '', color: '#00f', values: [3, 40] },
		{ label: 'Dropped', media_type: '', color: '#f00', values: [0, 0] }
	]
};

describe('statusSlices', () => {
	it('sums every type, or takes the picked type, without empty statuses', () => {
		expect(statusSlices(status, 'all').map((slice) => [slice.label, slice.value])).toEqual([
			['Completed', 20],
			['Planning', 43]
		]);
		expect(statusSlices(status, 'tv').map((slice) => [slice.label, slice.value])).toEqual([['Planning', 3]]);
		expect(statusSlices(status, 'game')).toEqual([]);
	});
});

describe('ratingBars', () => {
	it('counts items per score for every type or one', () => {
		const ratings = {
			labels: ['8', '9'],
			series: [
				{ label: 'Movie', media_type: '', color: '', values: [2, 1] },
				{ label: 'Game', media_type: '', color: '', values: [0, 1] }
			]
		};
		expect(ratingBars(ratings, 'all').total).toBe(4);
		expect(ratingBars(ratings, 'movie').bars.series[0].values).toEqual([2, 1]);
	});
});

describe('rhythmTiers', () => {
	it('puts empty cells in tier 0 and the busiest in the top tier', () => {
		const tiers = rhythmTiers([[0, 1, 2, 3, 4, 5, 6]]);
		expect(tiers[0][0]).toBe(0);
		expect(tiers[0][6]).toBe(6);
		expect(tiers[0][1]).toBe(1);
	});
});

describe('consumptionTiles', () => {
	it('writes per year, month and day with the secondary metric and bonuses', () => {
		const tiles = consumptionTiles({
			has_data: true,
			primary: { label: 'Hours Played', unit: 'Hours', per_year: 120, per_month: 10, per_day: 0.33 },
			secondary: { label: 'Sessions', unit: 'Sessions', per_year: 50, per_month: 4.2, per_day: 0.1 },
			bonuses: [{ kind: 'playtime', label: '', unit: '', value: 0.5 }]
		});
		expect(tiles.map((tile) => tile.value)).toEqual(['120.0 hrs', '10.0 hrs', '0.3 hrs', '30 min']);
		expect(tiles[0].caption).toBe('50.0 Sessions');
		expect(tiles[3].label).toBe('Average Playtime');
	});
});
