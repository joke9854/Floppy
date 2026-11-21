/**
 * The track dialog's date and status rules (P4-D1), ported from the Django
 * dialog's scripts so the web saves what the page saves:
 * mediaStatusDateHandler.js (end date filled on Completed / In progress,
 * cleared again when the status changes) and dateTimePicker.js (the value
 * format, Start Now, Just Finished, Release Date with the runtime, copy
 * from the other date, Clear).
 *
 * Values are the page's: "YYYY-MM-DD" without TRACK_TIME, else
 * "YYYY-MM-DDTHH:MM[:SS[.ffffff]]" in local wall time. A stored value keeps
 * its fraction, so an untouched date posts back the same instant.
 */

export type DateField = 'start_date' | 'end_date';

export type TrackState = {
	values: Record<string, string>;
	/** Dates this dialog filled itself; a status change clears them again. */
	autoFilled: Record<DateField, boolean>;
	/** The user set the start date: the runtime backfill leaves it alone. */
	manualStart: boolean;
	original: { status: string; endDate: string | null };
	isNew: boolean;
	trackTime: boolean;
};

const COMPLETED = 'Completed';
const IN_PROGRESS = 'In progress';
const pad = (value: number) => String(value).padStart(2, '0');

/** What the page's picker keeps from a field value (normalizeInitialValue). */
export function normalizeInitialValue(value: string, trackTime: boolean): string {
	const trimmed = value.trim();
	if (!trimmed) return '';
	const [datePart, timePart] = trimmed.split(/[T ]/, 2);
	if (!timePart || !trackTime) return datePart;
	const [hour, minute, second] = timePart.split(':');
	const time = `${hour}:${minute}`;
	return second && Number(second) !== 0 ? `${datePart}T${time}:${second}` : `${datePart}T${time}`;
}

/** A picker value from a local Date (formatValueFromDate): seconds only when not zero. */
export function formatValue(date: Date, trackTime: boolean): string {
	const day = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
	if (!trackTime) return day;
	const minute = `${day}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
	return date.getSeconds() ? `${minute}:${pad(date.getSeconds())}` : minute;
}

/** The status handler's "now" (getCurrentDateTime): to the minute, or the date. */
export function currentValue(date: Date, trackTime: boolean): string {
	const day = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
	return trackTime ? `${day}T${pad(date.getHours())}:${pad(date.getMinutes())}` : day;
}

/** A local Date from a picker value; null for an empty or broken one. */
export function parseValue(value: string): Date | null {
	const match = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?)?$/.exec(value.trim());
	if (!match) return null;
	const [, y, m, d, h = '0', min = '0', s = '0', fraction = ''] = match;
	const ms = fraction ? Math.floor(Number(`0.${fraction}`) * 1000) : 0;
	return new Date(Number(y), Number(m) - 1, Number(d), Number(h), Number(min), Number(s), ms);
}

export function initialState(
	fields: { name: string; kind: string; value: string }[],
	trackTime: boolean,
	now: Date
): TrackState {
	const values: Record<string, string> = {};
	for (const field of fields) {
		values[field.name] =
			field.kind === 'datetime' || field.kind === 'date'
				? normalizeInitialValue(field.value, field.kind === 'datetime')
				: field.value;
	}
	const isNew = !values.instance_id;
	const state: TrackState = {
		values,
		autoFilled: { start_date: false, end_date: false },
		manualStart: false,
		original: { status: values.status ?? '', endDate: values.end_date || null },
		isNew,
		trackTime
	};
	// A new entry that starts Completed or In progress is dated now.
	if (isNew && 'end_date' in values && !values.end_date && [COMPLETED, IN_PROGRESS].includes(values.status)) {
		values.end_date = currentValue(now, trackTime);
		state.autoFilled.end_date = true;
	}
	return state;
}

/** The status select changed (mediaStatusDateHandler's change handler). */
export function changeStatus(state: TrackState, status: string, now: Date): TrackState {
	const values: Record<string, string> = { ...state.values, status };
	const autoFilled = { ...state.autoFilled };
	for (const field of ['start_date', 'end_date'] as const) {
		if (autoFilled[field] && field in values) {
			values[field] = '';
			autoFilled[field] = false;
		}
	}
	const returning =
		(status === COMPLETED || status === IN_PROGRESS) &&
		state.original.status === status &&
		state.original.endDate === null;
	if ((status === COMPLETED || status === IN_PROGRESS) && 'end_date' in values && !values.end_date && !returning) {
		values.end_date = currentValue(now, state.trackTime);
		autoFilled.end_date = true;
	}
	return { ...state, values, autoFilled };
}

/** The user picked a date (the picker's commit). */
export function setDate(state: TrackState, field: DateField, value: string): TrackState {
	return {
		...state,
		values: { ...state.values, [field]: value },
		autoFilled: { ...state.autoFilled, [field]: false },
		manualStart: field === 'start_date' ? true : state.manualStart
	};
}

/** Clear a date; clearing the start tells the server it was cleared on purpose. */
export function clearDate(state: TrackState, field: DateField): TrackState {
	const values = { ...state.values, [field]: '' };
	let manualStart = state.manualStart;
	if (field === 'start_date') {
		manualStart = false;
		if ('start_date_cleared' in values) values.start_date_cleared = '1';
	}
	return { ...state, values, autoFilled: { ...state.autoFilled, [field]: false }, manualStart };
}

const other = (field: DateField): DateField => (field === 'start_date' ? 'end_date' : 'start_date');

/** Set the status for a preset without the status rule's autofill (setStatusForPreset). */
function presetStatus(state: TrackState, status: string): TrackState {
	if (!('status' in state.values) || state.values.status === status) return state;
	return { ...state, values: { ...state.values, status } };
}

/** Set the other date for a preset (commitPairedValue): not a manual start. */
function setPaired(state: TrackState, field: DateField, value: string): TrackState {
	if (!(field in state.values)) return state;
	return {
		...state,
		values: { ...state.values, [field]: value },
		autoFilled: { ...state.autoFilled, [field]: false }
	};
}

/** Start Now: In progress, start now and end after the runtime. */
export function startNow(state: TrackState, field: DateField, runtime: number | null, now: Date): TrackState {
	const next = presetStatus(state, IN_PROGRESS);
	const start = formatValue(now, state.trackTime);
	const end = formatValue(new Date(now.getTime() + (runtime ?? 0) * 60000), state.trackTime);
	return field === 'start_date'
		? setPaired(setDate(next, 'start_date', start), 'end_date', end)
		: setPaired(setDate(next, 'end_date', end), 'start_date', start);
}

/** Just Finished: Completed, end now and start a runtime before. */
export function justFinished(state: TrackState, field: DateField, runtime: number | null, now: Date): TrackState {
	const next = presetStatus(state, COMPLETED);
	const end = formatValue(now, state.trackTime);
	const start = formatValue(new Date(now.getTime() - (runtime ?? 0) * 60000), state.trackTime);
	return field === 'start_date'
		? setPaired(setDate(next, 'start_date', start), 'end_date', end)
		: setPaired(setDate(next, 'end_date', end), 'start_date', start);
}

/**
 * Release Date: Completed, the release day at the field's current time (the
 * time now when it is empty), and for the end date the start a runtime
 * before it unless the user set the start (applySuggestion and
 * backfillStartDateIfNeeded).
 */
export function releaseDate(
	state: TrackState,
	field: DateField,
	isoDate: string,
	runtime: number | null,
	now: Date
): TrackState {
	const [y, m, d] = isoDate.slice(0, 10).split('-').map(Number);
	if (!isoDate || [y, m, d].some(Number.isNaN)) return state;
	let next = presetStatus(state, COMPLETED);
	const time = parseValue(next.values[field] ?? '') ?? now;
	const at = new Date(y, m - 1, d, time.getHours(), time.getMinutes(), time.getSeconds());
	next = setDate(next, field, formatValue(at, state.trackTime));
	if (field === 'end_date' && runtime && runtime > 0 && state.trackTime && !next.manualStart && 'start_date' in next.values) {
		next = setPaired(next, 'start_date', formatValue(new Date(at.getTime() - runtime * 60000), state.trackTime));
	}
	return next;
}

/** Copy the other date into this one (copyFromOther); a copy into start is a manual start. */
export function copyFromOther(state: TrackState, field: DateField): TrackState {
	const source = parseValue(state.values[other(field)] ?? '');
	if (!source) return state;
	return setDate(state, field, formatValue(source, state.trackTime));
}

/** The fields to post: every value, the start-cleared flag only once set. */
export function formData(state: TrackState): Record<string, string> {
	return { ...state.values };
}
