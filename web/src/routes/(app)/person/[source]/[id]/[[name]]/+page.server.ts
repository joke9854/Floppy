import { error, redirect } from '@sveltejs/kit';
import { personApiPath, type PersonScreen } from '#lib/details/api.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, url, params }) => {
	const response = await fetch(`${url.origin}${personApiPath(params.source, params.id)}`);
	if (response.status === 400) {
		// No person page for this source: the Django page says so.
		redirect(
			307,
			`/person/${encodeURIComponent(params.source)}/${encodeURIComponent(params.id)}/` +
				encodeURIComponent(params.name ?? 'person')
		);
	}
	if (!response.ok) {
		error(response.status >= 500 ? 503 : response.status, 'This page could not load.');
	}
	return { person: (await response.json()) as PersonScreen };
};
