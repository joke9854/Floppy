import { djangoForm } from '#lib/csrf.ts';

/**
 * The Library's writes (P4-B4, B5): the Django page's own endpoints, posted
 * as its forms post them. Each returns the page's message, or throws.
 */

type Outcome = { message: string };

async function json(response: Response): Promise<Outcome> {
	if (!response.ok) throw new Error(String(response.status));
	const body = (await response.json()) as { success?: boolean; message?: string; error?: string };
	if (body.success === false) throw new Error(body.error ?? 'failed');
	return { message: body.message ?? '' };
}

const ids = (itemIds: number[]) => ({ item_ids: itemIds.map(String) });

/** Update Status (bulk_status_update). */
export async function bulkStatus(itemIds: number[], status: string): Promise<Outcome> {
	return json(await djangoForm('/bulk/status', { ...ids(itemIds), status }));
}

/** Add to List (bulk_list_add); one item from a card's menu too. */
export async function addToList(itemIds: number[], listId: string): Promise<Outcome> {
	return json(await djangoForm('/list/bulk-add', { ...ids(itemIds), custom_list_id: listId }));
}

/** Add to Collection (bulk_collection_quick_add). */
export async function addToCollection(itemIds: number[]): Promise<Outcome> {
	return json(await djangoForm('/bulk/collection', ids(itemIds)));
}

/** Apply Tag: add or remove one tag (tag_bulk_toggle answers 204). */
export async function bulkTag(itemIds: number[], tag: string, action: 'add' | 'remove'): Promise<void> {
	const response = await djangoForm('/tag_bulk_toggle', { ...ids(itemIds), tag_name: tag, action });
	if (!response.ok) throw new Error(String(response.status));
}

/**
 * Share View (list_share_view): the view's filters become the user's public
 * smart list; returns its URL. The URL's parameters are the page's own.
 */
export async function shareView(mediaType: string, search: Iterable<[string, string]>): Promise<string> {
	const fields: Record<string, string[]> = {};
	for (const [key, value] of search) {
		if (key === 'page' || key === 'layout') continue;
		(fields[key] ??= []).push(value);
	}
	fields.media_type = [mediaType];
	const response = await djangoForm('/list/share-view', fields);
	if (!response.ok) throw new Error(String(response.status));
	const body = (await response.json()) as { url?: string };
	if (!body.url) throw new Error('no url');
	return body.url;
}

/** "Show matching entries separately" (medialist_entry_grouping redirects back). */
export async function setEntryGrouping(mediaType: string, separate: boolean): Promise<void> {
	const response = await djangoForm(`/medialist/${encodeURIComponent(mediaType)}/entry-grouping/`, {
		show_separate_entries: separate ? 'true' : 'false'
	});
	if (response.type !== 'opaqueredirect' && !response.ok) throw new Error(String(response.status));
}
