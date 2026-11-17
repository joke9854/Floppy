import { createApi } from '#lib/api/client.ts';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async ({ fetch, locals, url }) => {
	// The Library switch (user/sidebar/ `library`). A failed call leaves the
	// Library empty; it never fails the page.
	let library: { media_type: string; label: string }[] = [];
	try {
		const { data } = await createApi(fetch, url.origin).GET('/api/v1/user/sidebar/');
		library = data?.library ?? [];
	} catch {
		library = [];
	}
	return { username: locals.user?.username ?? '', library };
};
