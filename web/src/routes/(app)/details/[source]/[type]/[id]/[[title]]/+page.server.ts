import { error, redirect } from '@sveltejs/kit';
import { detailApiPath, type DetailSections, type DetailShell } from '#lib/details/api.ts';
import type { PageServerLoad } from './$types';

const WEB_TYPES = new Set(['movie', 'tv']);

export const load: PageServerLoad = async ({ fetch, url, params }) => {
	const django =
		`/details/${encodeURIComponent(params.source)}/${encodeURIComponent(params.type)}/` +
		`${encodeURIComponent(params.id)}/${encodeURIComponent(params.title ?? 'title')}${url.search}`;
	// Movies and shows only (P4-C1); other types keep their Django page.
	if (!WEB_TYPES.has(params.type)) redirect(307, django);

	// The page's two phases at once: the hero (caches only, awaited) and the
	// sections, which may read the provider and stream in after first paint.
	const season = url.searchParams.get('season');
	const sections: Promise<DetailSections | null> = fetch(
		`${url.origin}${detailApiPath(params.type, params.source, params.id, 'sections', season)}`
	)
		.then((response) => (response.ok ? (response.json() as Promise<DetailSections>) : null))
		.catch(() => null);
	const response = await fetch(
		`${url.origin}${detailApiPath(params.type, params.source, params.id)}`
	);
	if (response.status === 400) redirect(307, django);
	if (!response.ok) {
		error(response.status >= 500 ? 503 : response.status, 'This page could not load.');
	}
	return { shell: (await response.json()) as DetailShell, sections };
};
