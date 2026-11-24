import { describe, expect, it } from 'vitest';
import { applyRuleChanges, rulesFilters, saveQueue, selectedTypes, toggleAllTypes, typesForSubmit, type SmartRules } from './smart.ts';

const rules = {
	media_types: [],
	status: [],
	rating: 'rated',
	rating_min: '',
	rating_max: '',
	collection: 'all',
	genre: 'Drama',
	implied_genre: '',
	year: '',
	completed_date_from: '',
	completed_date_to: '',
	completed_date_within: '',
	completed_date_within_unit: 'days',
	release: 'all',
	release_date_from: '',
	release_date_to: '',
	release_date_within: '',
	release_date_within_unit: 'days',
	date_added_from: '',
	date_added_to: '',
	date_added_within: '',
	date_added_within_unit: 'days',
	source: '',
	search: '',
	sort: '',
	sort_direction: '',
	language: '',
	country: '',
	platform: 'PC',
	origin: '',
	format: '',
	author: '',
	provider: '',
	tag: ['Faves'],
	tag_mode: 'or',
	list: [3]
} satisfies SmartRules;

describe('applyRuleChanges', () => {
	it('turns rules off with their defaults and keeps the rest', () => {
		const next = applyRuleChanges(rules, { rating: null, genre: 'Comedy', tag: ['A', 'B'], progress: 'caught_up' });
		expect(next.rating).toBe('all');
		expect(next.genre).toBe('Comedy');
		expect(next.tag).toEqual(['A', 'B']);
		expect(next.list).toEqual([3]);
		expect('progress' in next).toBe(false);
	});

	it('keeps one platform, the newly picked', () => {
		expect(applyRuleChanges(rules, { platform: ['PC', 'Switch'] }).platform).toBe('Switch');
		expect(applyRuleChanges(rules, { platform: [] }).platform).toBe('');
		expect(applyRuleChanges(rules, { platform: null }).platform).toBe('');
	});
});

describe('rulesFilters', () => {
	it('reads the menu values from the rules', () => {
		const filters = rulesFilters(rules);
		expect(filters.platforms).toEqual(['PC']);
		expect(filters.tags).toEqual(['Faves']);
		expect(filters.rating).toBe('rated');
	});
});

describe('media types', () => {
	const available = ['anime', 'episode', 'movie', 'season', 'tv'];
	const granular = ['episode', 'season'];

	it('shows every broad type for none saved and saves them back as none', () => {
		const selected = selectedTypes([], available, granular);
		expect(selected).toEqual(['anime', 'movie', 'tv']);
		expect(typesForSubmit(selected, available, granular)).toEqual([]);
		expect(typesForSubmit([...selected, 'season'], available, granular)).toEqual(['anime', 'movie', 'tv', 'season']);
		expect(typesForSubmit(['movie'], available, granular)).toEqual(['movie']);
	});

	it('toggles all broad types and keeps granular picks', () => {
		expect(toggleAllTypes(['anime', 'movie', 'tv', 'episode'], available, granular)).toEqual(['episode']);
		expect(toggleAllTypes(['episode'], available, granular)).toEqual(['anime', 'movie', 'tv', 'episode']);
	});
});

describe('saveQueue', () => {
	it('sends one at a time and only the latest pending', async () => {
		const sent: number[] = [];
		let value = 0;
		let release: () => void = () => {};
		const settled: boolean[] = [];
		const save = saveQueue(
			() =>
				new Promise<boolean>((resolve) => {
					sent.push(value);
					release = () => resolve(true);
				}),
			(ok) => settled.push(ok)
		);
		value = 1;
		const first = save();
		value = 2;
		void save();
		value = 3;
		void save();
		release();
		await new Promise((resolve) => setTimeout(resolve, 0));
		release();
		await first;
		expect(sent).toEqual([1, 3]);
		expect(settled).toEqual([true]);
	});
});
