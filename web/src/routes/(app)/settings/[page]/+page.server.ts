import { error, redirect } from '@sveltejs/kit';
import type { SettingsScreen } from '#lib/settings/types.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, url, params, depends }) => {
	depends('floppy:settings');
	// One call: the settings nav and the page, as the Django page reads it
	// (v2 P4-J). Pages the web does not draw yet open their Django page.
	const response = await fetch(`${url.origin}/api/v1/settings/screen/${encodeURIComponent(params.page)}/`);
	if (!response.ok) error(response.status >= 500 ? 503 : response.status, 'Settings could not load.');
	const screen = (await response.json()) as SettingsScreen;
	if (!screen.handled) redirect(302, screen.django_url);
	return { screen };
};
