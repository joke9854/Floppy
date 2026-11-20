import { describe, expect, it } from 'vitest';
import {
	clearFilters,
	completedLabel,
	filterLabel,
	matching,
	nextMode,
	toggled,
	type LibraryFilterOptions,
	type LibraryFilters
} from './filters.ts';

const none: LibraryFilters = {
	rating: 'all',
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
};

const options = {
	relative_date_units: [
		{ value: 'days', label: 'Days' },
		{ value: 'weeks', label: 'Weeks' }
	],
	show_languages: true,
	show_platforms: true
} as unknown as LibraryFilterOptions;

describe('filterLabel', () => {
	it('says All with no filter, else the first one and how many more', () => {
		expect(filterLabel(none, options)).toBe('All');
		expect(filterLabel({ ...none, rating: 'rated' }, options)).toBe('Rated');
		expect(filterLabel({ ...none, rating: 'rated', genre: 'Drama', year: '2016' }, options)).toBe(
			'Rated +2'
		);
		expect(filterLabel({ ...none, tags: ['a', 'b'], tag_mode: 'and' }, options)).toBe('+a & b');
		expect(filterLabel({ ...none, tags: ['a'], tag_mode: 'not' }, options)).toBe('-a');
		expect(filterLabel({ ...none, language: 'en' }, options)).toBe('EN');
	});

	it('names the completed date as a year, a range or a window', () => {
		const year = { ...none, completed_date_from: '2024-01-01', completed_date_to: '2024-12-31' };
		expect(completedLabel(year, options)).toBe('2024');
		expect(completedLabel({ ...none, completed_date_from: '2024-03-01' }, options)).toBe(
			'2024-03-01 – …'
		);
		const window = { ...none, completed_date_within: '2', completed_date_within_unit: 'weeks' };
		expect(completedLabel(window, options)).toBe('Last 2 weeks');
		expect(filterLabel(window, options)).toBe('Completed: Last 2 weeks');
	});
});

describe('filter helpers', () => {
	it('clears every filter parameter and nothing else', () => {
		const changes = clearFilters();
		expect(changes.tag).toBeNull();
		expect(changes.completed_date_within).toBeNull();
		expect('sort' in changes).toBe(false);
		expect('status' in changes).toBe(false);
	});

	it('cycles modes, toggles values and searches labels', () => {
		expect([nextMode('or'), nextMode('not'), nextMode('and')]).toEqual(['not', 'and', 'or']);
		expect(toggled(['a'], 'b')).toEqual(['a', 'b']);
		expect(toggled(['a', 'b'], 'a')).toEqual(['b']);
		const list = [{ label: 'Science Fiction' }, { label: 'Drama' }];
		expect(matching(list, 'fic')).toEqual([{ label: 'Science Fiction' }]);
		expect(matching(list, '  ')).toEqual(list);
	});
});
