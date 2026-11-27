import type { components } from '#lib/api/client.ts';

export type SettingsScreen = components['schemas']['SettingsScreen'];
export type SettingsNavSection = components['schemas']['SettingsNavSection'];
export type SettingsMediaType = components['schemas']['SettingsMediaType'];
export type SettingsItem = components['schemas']['SettingsItem'];

/** A form answer from a Django settings view (Accept: application/json). */
export type SavedAnswer = { saved: boolean; errors?: Record<string, string[]>; message?: string; changed?: boolean };

/** Move one entry up (-1) or down (+1); out of range leaves the list as it is. */
export function moveEntry<T>(list: T[], index: number, direction: -1 | 1): T[] {
	const target = index + direction;
	if (index < 0 || target < 0 || target >= list.length) return list;
	const next = [...list];
	[next[index], next[target]] = [next[target], next[index]];
	return next;
}

/**
 * The Media types form as the Django page posts it: every enabled type, the
 * whole order (a type left out of the order goes last, one left out of the
 * checkboxes is turned off), and the card overlay checkbox.
 */
export function mediaTypesForm(types: SettingsMediaType[], clickable: boolean): Record<string, string | string[]> {
	const form: Record<string, string | string[]> = {
		media_types_checkboxes: types.filter((type) => type.enabled).map((type) => type.value),
		sidebar_media_type_order: types.map((type) => type.value).join(',')
	};
	if (clickable) form.clickable_media_cards = 'on';
	return form;
}

/** The Notifications form: every field, checkboxes as "on" when set. */
export function notificationsForm(values: {
	notification_urls: string;
	daily_digest_enabled: boolean;
	release_notifications_enabled: boolean;
	premiere_notifications_enabled: boolean;
}): Record<string, string> {
	const form: Record<string, string> = { notification_urls: values.notification_urls };
	for (const key of ['daily_digest_enabled', 'release_notifications_enabled', 'premiere_notifications_enabled'] as const) {
		if (values[key]) form[key] = 'on';
	}
	return form;
}

/** Read a settings form's answer, whatever the status. */
export async function readAnswer(response: Response): Promise<SavedAnswer> {
	const body = (await response.json().catch(() => ({}))) as Partial<SavedAnswer>;
	const answer: SavedAnswer = { saved: response.ok && body.saved !== false, errors: body.errors, message: body.message };
	if (typeof body.changed === 'boolean') answer.changed = body.changed;
	return answer;
}
