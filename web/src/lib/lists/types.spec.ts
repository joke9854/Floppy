import { describe, expect, it } from 'vitest';
import {
	addTag,
	listPageQuery,
	listsQuery,
	previewUrl,
	readDevicePoll,
	sortDirection,
	toggleValue
} from './types.ts';

describe('listsQuery', () => {
	it('keeps the page query and applies changes', () => {
		const params = new URLSearchParams('scope=shared&q=star&page=3');
		expect(listsQuery(params)).toBe('?scope=shared&q=star');
		expect(listsQuery(params, { q: null, sort: 'name' })).toBe('?scope=shared&sort=name');
	});
});

describe('sortDirection', () => {
	it('flips the active sort and starts a new one as the page does', () => {
		expect(sortDirection('name', 'name', 'asc')).toBe('desc');
		expect(sortDirection('name', 'items_count', 'desc')).toBe('asc');
		expect(sortDirection('items_count', 'name', 'asc')).toBe('desc');
	});
});

describe('addTag', () => {
	it('trims and drops duplicates regardless of case', () => {
		expect(addTag(['Faves'], ' faves ')).toEqual(['Faves']);
		expect(addTag(['Faves'], ' Weekend ')).toEqual(['Faves', 'Weekend']);
		expect(addTag([], '   ')).toEqual([]);
	});
});

describe('previewUrl', () => {
	it('shows the slug or the list reference', () => {
		expect(previewUrl('https://f.example/list/__ref__', 'my-list', '42')).toBe('https://f.example/list/my-list');
		expect(previewUrl('https://f.example/list/__ref__', '', '42')).toBe('https://f.example/list/42');
	});
});

describe('readDevicePoll', () => {
	it('reads pending, importing, expired and errors', () => {
		expect(readDevicePoll(200, { status: 'pending', interval: 7 })).toEqual({ kind: 'pending', interval: 7 });
		expect(readDevicePoll(200, { status: 'importing' })).toEqual({ kind: 'importing' });
		expect(readDevicePoll(410, {})).toEqual({ kind: 'expired' });
		expect(readDevicePoll(400, { detail: 'Denied' })).toEqual({ kind: 'error', message: 'Denied' });
	});
});

describe('listPageQuery', () => {
	it('repeats type and status and applies changes', () => {
		const params = new URLSearchParams('q=star&type=movie&type=tv&status=Completed&sort=title&page=2');
		expect(listPageQuery(params)).toBe('?q=star&type=movie&type=tv&status=Completed&sort=title');
		expect(listPageQuery(params, { type: [], sort: 'custom', layout: 'table' })).toBe(
			'?q=star&status=Completed&sort=custom&layout=table'
		);
	});
});

describe('toggleValue', () => {
	it('adds, removes and clears with all', () => {
		expect(toggleValue([], 'movie')).toEqual(['movie']);
		expect(toggleValue(['movie', 'tv'], 'movie')).toEqual(['tv']);
		expect(toggleValue(['movie'], 'all')).toEqual([]);
	});
});
