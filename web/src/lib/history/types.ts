import type { components } from '#lib/api/client.ts';

export type HistoryScreen = components['schemas']['HistoryScreen'];
export type HistoryDay = components['schemas']['HistoryScreenDay'];
export type HistoryEntry = components['schemas']['HistoryScreenEntry'];
export type HistoryChoice = components['schemas']['HistoryScreenChoice'];

/** The History query with `changes` applied; `null` removes a key, and the page resets. */
export function historyQuery(current: { toString(): string }, changes: Record<string, string | null>): string {
	const next = new URLSearchParams(current.toString());
	next.delete('page');
	for (const [key, value] of Object.entries(changes)) {
		if (value === null || value === '') next.delete(key);
		else next.set(key, value);
	}
	const query = next.toString();
	return query ? `?${query}` : '';
}
