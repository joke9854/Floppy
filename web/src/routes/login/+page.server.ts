import { redirect } from '@sveltejs/kit';
import { safeNext } from '#lib/paths.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = ({ locals, url }) => {
	const next = safeNext(url.searchParams.get('next'));
	if (locals.user) redirect(303, next);
	return { next };
};
