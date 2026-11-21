import { describe, expect, it } from 'vitest';
import {
	changeStatus,
	clearDate,
	copyFromOther,
	initialState,
	justFinished,
	normalizeInitialValue,
	parseProgressMinutes,
	releaseDate,
	setDate,
	settle,
	startNow
} from './rules.ts';

const NOW = new Date(2026, 10, 21, 20, 15, 30);

const fields = (values: Record<string, string>) =>
	Object.entries(values).map(([name, value]) => ({
		name,
		value,
		kind: name.endsWith('_date') ? 'datetime' : 'text'
	}));

describe('track dialog rules', () => {
	it('keeps a stored value exactly as the page picker does', () => {
		expect(normalizeInitialValue('2026-03-04 20:01:07.123456', true)).toBe('2026-03-04T20:01:07.123456');
		expect(normalizeInitialValue('2026-03-04 20:01:07', true)).toBe('2026-03-04T20:01:07');
		expect(normalizeInitialValue('2026-03-04 20:01:00', true)).toBe('2026-03-04T20:01');
		expect(normalizeInitialValue('2026-03-04 20:01:00.500000', true)).toBe('2026-03-04T20:01:00.500000');
		expect(normalizeInitialValue('2026-03-04 20:01:07', false)).toBe('2026-03-04');
		expect(normalizeInitialValue('', true)).toBe('');
	});

	it('dates a new Completed entry now, and leaves an edit alone', () => {
		const added = initialState(fields({ instance_id: '', status: 'Completed', end_date: '' }), true, NOW);
		expect(added.values.end_date).toBe('2026-11-21T20:15');
		expect(added.autoFilled.end_date).toBe(true);

		const edited = initialState(fields({ instance_id: '7', status: 'Completed', end_date: '' }), true, NOW);
		expect(edited.values.end_date).toBe('');
	});

	it('clears its own dates when the status changes, and fills the end for In progress', () => {
		let state = initialState(fields({ instance_id: '', status: 'Completed', end_date: '' }), true, NOW);
		state = changeStatus(state, 'Planning', NOW);
		expect(state.values.end_date).toBe('');

		state = changeStatus(state, 'In progress', NOW);
		expect(state.values.end_date).toBe('2026-11-21T20:15');
	});

	it('does not refill an end date the entry was saved without', () => {
		let state = initialState(
			fields({ instance_id: '7', status: 'Completed', start_date: '', end_date: '' }),
			true,
			NOW
		);
		state = changeStatus(state, 'Planning', NOW);
		state = changeStatus(state, 'Completed', NOW);

		expect(state.values.end_date).toBe('');
	});

	it('keeps a date the user typed when the status changes', () => {
		let state = initialState(fields({ instance_id: '', status: 'Planning', end_date: '' }), true, NOW);
		state = setDate(state, 'end_date', '2026-01-02T10:00');
		state = changeStatus(state, 'Completed', NOW);

		expect(state.values.end_date).toBe('2026-01-02T10:00');
	});

	it('Start Now and Just Finished set the status and both dates from the runtime', () => {
		const base = initialState(
			fields({ instance_id: '7', status: 'Planning', start_date: '', end_date: '' }),
			true,
			NOW
		);

		const started = startNow(base, 'start_date', 120, NOW);
		expect(started.values).toMatchObject({
			status: 'In progress',
			start_date: '2026-11-21T20:15:30',
			end_date: '2026-11-21T22:15:30'
		});

		const finished = justFinished(base, 'end_date', 90, NOW);
		expect(finished.values).toMatchObject({
			status: 'Completed',
			start_date: '2026-11-21T18:45:30',
			end_date: '2026-11-21T20:15:30'
		});
	});

	it('Release Date keeps the time and backfills the start unless the user set it', () => {
		const base = initialState(
			fields({ instance_id: '7', status: 'Planning', start_date: '', end_date: '2026-05-01T21:30' }),
			true,
			NOW
		);

		const released = releaseDate(base, 'end_date', '1999-03-31', 136, NOW);
		expect(released.values).toMatchObject({
			status: 'Completed',
			end_date: '1999-03-31T21:30',
			start_date: '1999-03-31T19:14'
		});

		const manual = releaseDate(setDate(base, 'start_date', '1999-03-30T10:00'), 'end_date', '1999-03-31', 136, NOW);
		expect(manual.values.start_date).toBe('1999-03-30T10:00');
	});

	it('copies the other date and flags a cleared start', () => {
		let state = initialState(
			fields({ instance_id: '7', status: 'Completed', start_date: '', end_date: '2026-05-01T21:30:05.250000', start_date_cleared: '' }),
			true,
			NOW
		);
		state = copyFromOther(state, 'start_date');
		expect(state.values.start_date).toBe('2026-05-01T21:30:05');
		expect(state.manualStart).toBe(true);

		state = clearDate(state, 'start_date');
		expect(state.values.start_date).toBe('');
		expect(state.values.start_date_cleared).toBe('1');
		expect(state.manualStart).toBe(false);

		state = setDate(state, 'start_date', '2026-05-01T10:00');
		expect(state.values.start_date_cleared).toBe('');
	});

	it('keeps a start a preset or Release Date set when Release Date sets the end', () => {
		const range = fields({ instance_id: '', start_date: '', end_date: '' });
		let state = initialState(range, true, NOW);
		// The Episode Plays range: the first episode's date, then the last's.
		state = releaseDate(state, 'start_date', '2008-01-20', 47, NOW);
		state = releaseDate(state, 'end_date', '2008-03-09', 47, NOW);
		expect(state.values.start_date).toBe('2008-01-20T20:15:30');
		expect(state.values.end_date).toBe('2008-03-09T20:15:30');

		// Just Finished on the end commits the start through the other picker.
		let edit = initialState(range, true, NOW);
		edit = justFinished(edit, 'end_date', 60, NOW);
		edit = releaseDate(edit, 'end_date', '2008-03-09', 47, NOW);
		expect(edit.values.start_date).toBe('2026-11-21T19:15:30');

		// Only the backfill itself leaves the start the dialog's.
		const fresh = releaseDate(initialState(range, true, NOW), 'end_date', '2008-03-09', 47, NOW);
		expect(fresh.values.start_date).toBe('2008-03-09T19:28:30');
		expect(fresh.manualStart).toBe(false);
	});

	it('leaves a tracked artist alone though its form has no instance_id', () => {
		const tracker = fields({ artist_id: '5', status: 'Completed', start_date: '', end_date: '' });

		expect(initialState(tracker, true, NOW, false).values.end_date).toBe('');
		expect(initialState(tracker, true, NOW, true).values.end_date).toBe('2026-11-21T20:15');
	});

	it('reads time played as the page does', () => {
		expect(parseProgressMinutes('2:05')).toBe(125);
		expect(parseProgressMinutes('2h 05min')).toBe(125);
		expect(parseProgressMinutes('1.5')).toBe(90);
		expect(parseProgressMinutes('111 minutes')).toBe(111);
		expect(parseProgressMinutes('4.3 hours')).toBe(258);
		expect(parseProgressMinutes('2:75')).toBeNull();
		expect(parseProgressMinutes('soon')).toBeNull();
		expect(parseProgressMinutes('')).toBeNull();
	});

	const game = (values: Record<string, string>) =>
		initialState(
			Object.entries(values).map(([name, value]) => ({
				name,
				value,
				kind: name.endsWith('_date') ? 'datetime' : name === 'progress' ? 'text' : 'hidden'
			})),
			true,
			NOW
		);

	it('backfills a game start from time played, never on opening an edit', () => {
		const edit = game({
			instance_id: '7',
			status: 'Completed',
			progress: '2h 05min',
			start_date: '',
			end_date: '2026-02-03 21:04:52.987654',
			start_date_cleared: ''
		});
		expect(edit.values.start_date).toBe('');
		expect(edit.values.end_date).toBe('2026-02-03T21:04:52.987654');

		const typed = settle(edit, { ...edit, values: { ...edit.values, progress: '3h' } });
		expect(typed.values.start_date).toBe('2026-02-03T18:04');
		expect(typed.autoFilled.start_date).toBe(true);

		const cleared = settle(typed, { ...typed, values: { ...typed.values, progress: '' } });
		expect(cleared.values.start_date).toBe('');
	});

	it('leaves a start the user set, and fills a new game at once', () => {
		let state = game({ instance_id: '', status: 'Planning', progress: '', start_date: '', end_date: '' });
		state = settle(state, setDate(state, 'start_date', '2026-01-01T08:00'));
		state = settle(state, setDate(state, 'end_date', '2026-01-01T12:00'));
		state = settle(state, { ...state, values: { ...state.values, progress: '1:00' } });
		expect(state.values.start_date).toBe('2026-01-01T08:00');

		const added = game({ instance_id: '', status: 'Completed', progress: '1:30', start_date: '', end_date: '' });
		expect(added.values.end_date).toBe('2026-11-21T20:15');
		expect(added.values.start_date).toBe('2026-11-21T18:45');
	});
});
