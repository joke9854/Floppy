import type { components } from '#lib/api/client.ts';

export type ListsScreen = components['schemas']['ListsScreen'];
export type ListCard = components['schemas']['ListsScreenCard'];

/** The query the index reads (and the API takes), as the Django page writes it. */
export const LIST_KEYS = ['scope', 'q', 'media_type', 'sort', 'direction'] as const;

export function listsQuery(params: { get(key: string): string | null }, changes: Record<string, string | null> = {}): string {
	const query = new URLSearchParams();
	for (const key of LIST_KEYS) {
		const value = key in changes ? changes[key] : params.get(key);
		if (value) query.set(key, value);
	}
	const text = query.toString();
	return text ? `?${text}` : '';
}

/**
 * The direction a sort pick sends (the page): picking the active sort flips
 * it; a new sort starts ascending for Name, descending otherwise.
 */
export function sortDirection(picked: string, current: string, direction: string): string {
	if (picked === current) return direction === 'asc' ? 'desc' : 'asc';
	return picked === 'name' ? 'asc' : 'desc';
}

/** Tags as the form keeps them: trimmed, deduplicated without regard to case. */
export function addTag(tags: string[], value: string): string[] {
	const tag = value.trim();
	if (!tag || tags.some((existing) => existing.toLowerCase() === tag.toLowerCase())) return tags;
	return [...tags, tag];
}

/** The public URL preview: the slug, or the list's own reference. */
export function previewUrl(template: string, slug: string, fallback: string): string {
	return template.replace('__ref__', slug.trim() || fallback);
}

export type DevicePoll =
	| { kind: 'pending'; interval: number }
	| { kind: 'importing' }
	| { kind: 'expired' }
	| { kind: 'error'; message: string };

/** What a Trakt device poll answer means (the imports API's device/poll). */
export function readDevicePoll(status: number, body: { status?: string; interval?: number; detail?: string }): DevicePoll {
	if (status === 200 && body.status === 'importing') return { kind: 'importing' };
	if (status === 200) return { kind: 'pending', interval: Math.max(1, Number(body.interval) || 5) };
	if (status === 410) return { kind: 'expired' };
	return { kind: 'error', message: body.detail || `Trakt answered ${status}.` };
}

/** A list page's query (list_detail): q, repeated type and status, sort, direction, layout. */
export function listPageQuery(
	params: { get(key: string): string | null; getAll(key: string): string[] },
	changes: { q?: string | null; type?: string[]; status?: string[]; sort?: string | null; direction?: string | null; layout?: string | null } = {}
): string {
	const query = new URLSearchParams();
	const q = 'q' in changes ? changes.q : params.get('q');
	if (q) query.set('q', q);
	for (const value of changes.type ?? params.getAll('type')) query.append('type', value);
	for (const value of changes.status ?? params.getAll('status')) query.append('status', value);
	for (const key of ['sort', 'direction', 'layout'] as const) {
		const value = key in changes ? changes[key] : params.get(key);
		if (value) query.set(key, value);
	}
	const text = query.toString();
	return text ? `?${text}` : '';
}

/** Toggle a value in a multi-select; "all" (or none left) clears the filter. */
export function toggleValue(current: string[], value: string, all = 'all'): string[] {
	if (value === all) return [];
	return current.includes(value) ? current.filter((entry) => entry !== value) : [...current.filter((entry) => entry !== all), value];
}
