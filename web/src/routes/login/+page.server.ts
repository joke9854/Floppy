import { redirect } from '@sveltejs/kit';
import { safeNext } from '#lib/paths.ts';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = ({ locals, url }) => {
	const next = safeNext(url.searchParams.get('next'));
	if (locals.user) redirect(303, next);
	return { next };
};

export const actions: Actions = {
	/**
	 * Only reached without the page's script (it signs in from the browser):
	 * the posted password is not read, and the Django sign-in page takes over.
	 */
	default: ({ url }) => {
		const next = safeNext(url.searchParams.get('next'));
		redirect(303, `/accounts/login/?next=${encodeURIComponent(next)}`);
	}
};
