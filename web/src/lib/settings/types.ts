import type { components } from '#lib/api/client.ts';

export type SettingsScreen = components['schemas']['SettingsScreen'];
export type SettingsNavSection = components['schemas']['SettingsNavSection'];
export type SettingsMediaType = components['schemas']['SettingsMediaType'];
export type SettingsItem = components['schemas']['SettingsItem'];
export type SettingsPreferences = components['schemas']['SettingsPreferences'];
export type SettingsAutoPauseRule = components['schemas']['SettingsAutoPauseRule'];
export type SettingsProvider = components['schemas']['SettingsProvider'];

/** A form answer from a Django settings view (Accept: application/json). */
export type SavedAnswer = {
	saved: boolean;
	errors?: Record<string, string[]>;
	message?: string;
	changed?: boolean;
	/** Metadata: existing anime in the other shape after a provider change. */
	anime_shape_prompt_count?: number;
};

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

/**
 * Read a settings form's answer, whatever the status. Views wrapped in
 * helpers.answers_json fail with `error` (a string); it becomes `message`.
 */
export async function readAnswer(response: Response): Promise<SavedAnswer> {
	const body = (await response.json().catch(() => ({}))) as Partial<SavedAnswer> & { error?: string };
	const saved = response.ok && body.saved !== false;
	const answer: SavedAnswer = { saved, errors: body.errors, message: saved ? body.message : body.error || body.message };
	if (typeof body.changed === 'boolean') answer.changed = body.changed;
	if (typeof body.anime_shape_prompt_count === 'number') answer.anime_shape_prompt_count = body.anime_shape_prompt_count;
	return answer;
}

/**
 * The Preferences form: every field (the view resets the auto-pause rules,
 * region and language when they are missing). Auto-pause is on while there
 * is a rule, as on the Django page.
 */
export function preferencesForm(values: Record<string, string>, rules: SettingsAutoPauseRule[]): Record<string, string> {
	return {
		...values,
		auto_pause_enabled: rules.length ? '1' : '0',
		auto_pause_rules: JSON.stringify(rules.map((rule) => ({ library: rule.library, weeks: Math.max(1, Math.round(rule.weeks) || 1) })))
	};
}

/** A server time as the browser's local date and time ("" for none). */
export function when(iso: string | null | undefined): string {
	if (!iso) return '';
	const date = new Date(iso);
	return Number.isNaN(date.getTime()) ? '' : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

/** The file name a download answer names (Content-Disposition), or `fallback`. */
export function downloadName(response: Response, fallback: string): string {
	const match = /filename="?([^";]+)"?/i.exec(response.headers.get('content-disposition') ?? '');
	return match?.[1] ?? fallback;
}
