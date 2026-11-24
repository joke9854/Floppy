import type { components } from '#lib/api/client.ts';
import type { LibraryFilters, ParamChanges } from '#lib/library/filters.ts';

export type ListPageSmart = components['schemas']['ListPageSmart'];
export type SmartRules = components['schemas']['ListPageSmartRules'];

/** A rule's value when it is off (lists/smart_rules.py SMART_FILTER_DEFAULTS). */
const OFF: Partial<Record<keyof SmartRules, string>> = {
	rating: 'all',
	collection: 'all',
	release: 'all',
	tag_mode: 'or',
	completed_date_within_unit: 'days',
	release_date_within_unit: 'days',
	date_added_within_unit: 'days'
};

/** The Library filter menu's values, read from the rules it edits. */
export function rulesFilters(rules: SmartRules): LibraryFilters {
	return {
		rating: rules.rating,
		collection: rules.collection,
		progress: '',
		genre: rules.genre,
		implied_genre: rules.implied_genre,
		year: rules.year,
		completed_date_from: rules.completed_date_from,
		completed_date_to: rules.completed_date_to,
		completed_date_within: rules.completed_date_within,
		completed_date_within_unit: rules.completed_date_within_unit,
		release: rules.release,
		source: rules.source,
		media_status: '',
		language: rules.language,
		country: rules.country,
		platform_mode: '',
		origin: rules.origin,
		format: rules.format,
		author: rules.author,
		provider: rules.provider,
		tag_mode: rules.tag_mode,
		platforms: rules.platform ? [rules.platform] : [],
		tags: rules.tag
	};
}

/**
 * Apply a filter menu change to the rules. Only rule keys change; null turns
 * a rule off. The smart builder takes one platform (filter_platform_multi
 * off), so a platform pick keeps the newly picked one.
 */
export function applyRuleChanges(rules: SmartRules, changes: ParamChanges): SmartRules {
	const next = { ...rules } as Record<string, unknown>;
	for (const [key, value] of Object.entries(changes)) {
		if (key === 'platform') {
			const picked = Array.isArray(value) ? value : value ? [value] : [];
			next.platform = picked.find((entry) => entry !== rules.platform) ?? '';
			continue;
		}
		if (!(key in rules)) continue;
		const off = OFF[key as keyof SmartRules] ?? '';
		if (Array.isArray((rules as Record<string, unknown>)[key])) {
			next[key] = value === null ? [] : Array.isArray(value) ? value : [value];
		} else {
			next[key] = value === null ? off : Array.isArray(value) ? (value.at(-1) ?? off) : value;
		}
	}
	return next as SmartRules;
}

/**
 * The picker's selection from the saved types: none saved means every
 * broad type (season and episode are offered but stay out of "all").
 */
export function selectedTypes(saved: string[], available: string[], granular: string[]): string[] {
	return saved.length ? saved : available.filter((value) => !granular.includes(value));
}

/** The saved types from the picker's selection: every broad type and no granular one saves as all. */
export function typesForSubmit(selected: string[], available: string[], granular: string[]): string[] {
	const broad = available.filter((value) => !granular.includes(value));
	const all = broad.length > 0 && broad.every((value) => selected.includes(value));
	return all && !selected.some((value) => granular.includes(value)) ? [] : selected;
}

/** "All Types" on the picker: every broad type on, or off, keeping granular picks. */
export function toggleAllTypes(selected: string[], available: string[], granular: string[]): string[] {
	const broad = available.filter((value) => !granular.includes(value));
	const kept = selected.filter((value) => granular.includes(value));
	const all = broad.length > 0 && broad.every((value) => selected.includes(value));
	return all ? kept : [...broad, ...kept];
}

/**
 * Saves one at a time, and only the latest pending: a slow save never lands
 * after a newer one. `save()` resolves once nothing is left to send.
 */
export function saveQueue(send: () => Promise<boolean>, onsettled: (ok: boolean) => void) {
	let running = false;
	let again = false;
	return async function save() {
		if (running) {
			again = true;
			return;
		}
		running = true;
		let ok = true;
		try {
			do {
				again = false;
				ok = await send().catch(() => false);
			} while (again);
		} finally {
			running = false;
		}
		onsettled(ok);
	};
}
