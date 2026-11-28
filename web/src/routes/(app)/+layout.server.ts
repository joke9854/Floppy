import { createApi } from '#lib/api/client.ts';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async ({ fetch, locals, url, depends }) => {
	// Saving Appearance invalidates this, so the shell redraws without a reload.
	depends('floppy:settings');
	// The Library switch (user/sidebar/ `library`). A failed call leaves the
	// Library empty; it never fails the page.
	let library: { media_type: string; label: string }[] = [];
	let sidebarStyle = 'attached';
	let floatingSidebar = 'hover';
	try {
		const { data } = await createApi(fetch, url.origin).GET('/api/v1/user/sidebar/');
		library = data?.library ?? [];
		sidebarStyle = data?.sidebar_style || sidebarStyle;
		floatingSidebar = data?.floating_sidebar || floatingSidebar;
	} catch {
		library = [];
	}
	return { username: locals.user?.username ?? '', library, sidebarStyle, floatingSidebar };
};
