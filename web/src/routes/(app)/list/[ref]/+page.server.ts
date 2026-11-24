import { error, redirect } from '@sveltejs/kit';
import type { components } from '#lib/api/client.ts';
import type { PageServerLoad } from './$types';

export type ListPage = components['schemas']['ListPage'];

export const load: PageServerLoad = async ({ fetch, url, params, depends }) => {
	depends('floppy:list');
	// One call: the Django list page's own context (v2 P4-I2, smart lists I3). Lists the web
	// does not draw (read-only, missing) open their Django page.
	const response = await fetch(
		`${url.origin}/api/v1/lists/page/${encodeURIComponent(params.ref)}/${url.search}`
	);
	if (!response.ok) error(response.status >= 500 ? 503 : response.status, 'The list could not load.');
	const page = (await response.json()) as ListPage;
	if (!page.handled) redirect(302, page.django_url + url.search);
	return { page };
};
