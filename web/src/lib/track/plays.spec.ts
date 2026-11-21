import { describe, expect, it } from 'vitest';
import { initialRange, playsData, rangeEpisodes, summary, syncEpisode, type Plays } from './plays.ts';

const episode = (order: number, season: number, number: number, extra: object = {}) => ({
	order,
	season_number: season,
	episode_number: number,
	episode_title: `Episode ${number}`,
	selector_label: '',
	existing_play_count: 0,
	runtime_minutes: 47,
	air_date: '2008-01-20',
	...extra
});

const field = (name: string, value: string, choices: string[] = []) => ({
	name,
	label: name,
	kind: (name.endsWith('_date') ? 'datetime' : choices.length ? 'select' : 'hidden') as 'datetime' | 'select' | 'hidden',
	value,
	choices: choices.map((choice) => ({ value: choice, label: choice })),
	required: false,
	min: null,
	max: null,
	step: null,
	placeholder: '',
	help_text: ''
});

const plays = {
	tab_label: 'Episode Plays',
	submit_label: 'Save plays',
	save_url: '/episode_bulk_save',
	mode_notice: '',
	hidden: [field('media_id', '1396'), field('source', 'tmdb'), field('media_type', 'tv'), field('instance_id', '')],
	first: { season_number: 1, episode_number: 1 },
	last: { season_number: 2, episode_number: 2 },
	write_mode: field('write_mode', 'add', ['add', 'replace']),
	distribution_mode: field('distribution_mode', 'air_date', ['air_date', 'even']),
	start_date: field('start_date', '2026-11-21 20:15:00'),
	end_date: field('end_date', '2026-11-21 20:15:00'),
	seasons: [
		{ season_number: 1, season_title: 'Season 1' },
		{ season_number: 2, season_title: 'Season 2' }
	],
	episodes: {
		'1': [episode(1, 1, 1), episode(2, 1, 2, { existing_play_count: 2 }), episode(3, 1, 3)],
		'2': [episode(4, 2, 1), episode(5, 2, 2, { air_date: '' })]
	},
	locked_season_number: null,
	hide_season_selectors: false,
	labels: {
		first_selection: '',
		last_selection: '',
		season_field: '',
		episode_field: '',
		noun: '',
		noun_plural: '',
		target: '',
		date_shortcut: ''
	},
	missing_target_fallback: 'even'
} satisfies Plays;

describe('episode plays rules', () => {
	it('runs the range by watch order across seasons', () => {
		const range = initialRange(plays);

		expect(rangeEpisodes(plays, range).map((e) => e.order)).toEqual([1, 2, 3, 4, 5]);
	});

	it('moves to the season’s first or last episode when the pick is not in it', () => {
		const range = syncEpisode(plays, { ...initialRange(plays), lastSeason: '1', lastEpisode: '2' }, 'last');
		expect(range.lastEpisode).toBe('2');

		const moved = syncEpisode(plays, { ...range, firstSeason: '2', firstEpisode: '3' }, 'first');
		expect(moved.firstEpisode).toBe('1');
		const last = syncEpisode(plays, { ...range, lastSeason: '2', lastEpisode: '7' }, 'last');
		expect(last.lastEpisode).toBe('2');
	});

	it('says what saving will do, as the page does', () => {
		const all = initialRange(plays);
		expect(summary(plays, all, 'add', 'air_date')).toEqual({
			text: 'This will add plays for 5 ordered items using the target dates within the selected date range.',
			warning: '1 selected item has no target date. Saving will fall back to even distribution.'
		});

		const season1 = { ...all, lastSeason: '1', lastEpisode: '3' };
		expect(summary(plays, season1, 'replace', 'even')).toEqual({
			text: 'This will replace plays for 3 ordered items using an even distribution across the date range.',
			warning: 'This will delete 2 existing plays in the selected range before adding the new ordered pass.'
		});
		expect(summary(plays, season1, 'add', 'even').warning).toBe(
			'This range already has 2 logged plays. New plays will be appended in order.'
		);
		expect(summary(plays, { ...all, lastEpisode: '9' }, 'add', 'even').text).toBe(
			'Choose a valid ordered range to log plays.'
		);
	});

	it('posts the page form’s fields with the range count', () => {
		const data = playsData(plays, initialRange(plays), {
			start_date: '2008-01-20T20:00',
			end_date: '2008-03-09T21:00',
			write_mode: 'replace'
		});

		expect(data).toEqual({
			media_id: '1396',
			source: 'tmdb',
			media_type: 'tv',
			instance_id: '',
			first_season_number: '1',
			first_episode_number: '1',
			last_season_number: '2',
			last_episode_number: '2',
			write_mode: 'replace',
			distribution_mode: 'air_date',
			start_date: '2008-01-20T20:00',
			end_date: '2008-03-09T21:00',
			episode_count: '5'
		});
	});
});
