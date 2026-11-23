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
