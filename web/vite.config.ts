import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vitest/config';
import { playwright } from '@vitest/browser-playwright';
import adapter from '@sveltejs/adapter-node';
import { sveltekit } from '@sveltejs/kit/vite';
import { appVersion } from './scripts/app-version.js';

// Served beside the Django pages until the cutover (v2 P5). Vitest's browser
// runner cannot reach its page under a base path, and the tests don't depend
// on it, so tests run at the root.
const base = process.env.VITEST ? '' : '/next';

export default defineConfig({
	define: { __FLOPPY_BASE__: JSON.stringify(base) },
	// `npm run dev` only: Django's own paths go to a local Django, as nginx
	// does in the container, so signing in and the Django pages work in dev.
	server: {
		proxy: Object.fromEntries(
			// The Django endpoints the web posts to (same origin behind nginx in production).
			[
				'/api',
				'/_allauth',
				'/accounts',
				'/static',
				'/image-cache',
				'/bulk',
				'/list/',
				'/tag_bulk_toggle',
				'/medialist',
				'/media_save',
				'/media_delete',
				'/media_rewatch',
				'/episode_save',
				// The tracker dialogs (P4-D2b).
				'/music/artist/save',
				'/music/artist/delete',
				'/music/album/save',
				'/music/album/delete',
				'/podcast/show/save',
				'/podcast/show/delete',
				// The Episode Plays tab (P4-D3).
				'/episode_bulk_save',
				'/music/bulk_save',
				// The Discover tab (P4-D4).
				'/discover/toggle-hidden',
				// The Collection tab (P4-D5): collection/add/ and collection/<id>/remove/.
				'/collection/',
				// The Metadata tab (P4-D6a).
				'/details/provider/',
				'/details/language/',
				'/details/image/',
				'/details/metadata/'
			].map((path) => [
				path,
				{ target: process.env.FLOPPY_DJANGO_ORIGIN ?? 'http://127.0.0.1:8001', xfwd: true }
			])
		)
	},
	plugins: [
		tailwindcss(),
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			adapter: adapter(),
			paths: { base },
			// A hash of the web app's own files: a Django-only commit keeps the
			// version, so open tabs are not asked to reload for nothing. Checked
			// on focus, on server responses and every 15 minutes.
			version: { name: appVersion(import.meta.dirname), pollInterval: 15 * 60 * 1000 }
		})
	],
	test: {
		expect: { requireAssertions: true },
		projects: [
			{
				extends: './vite.config.ts',
				// Components loaded with import() (the Library filter menu, the
				// detail sections, the trailer player) pull these in mid-run; a
				// dependency Vite finds then reloads the browser test run.
				optimizeDeps: {
					include: [
						'bits-ui',
						'@lucide/svelte/icons/arrow-down',
						'@lucide/svelte/icons/arrow-up',
						'@lucide/svelte/icons/check',
						'@lucide/svelte/icons/chevron-left',
						'@lucide/svelte/icons/chevron-right',
						'@lucide/svelte/icons/columns-3',
						'@lucide/svelte/icons/eye-off',
						'@lucide/svelte/icons/funnel',
						'@lucide/svelte/icons/info',
						'@lucide/svelte/icons/minus',
						'@lucide/svelte/icons/plus',
						'@lucide/svelte/icons/play',
						'@lucide/svelte/icons/repeat',
						'@lucide/svelte/icons/star',
						'@lucide/svelte/icons/ellipsis',
						'@lucide/svelte/icons/settings-2',
						'@lucide/svelte/icons/layout-grid',
						'@lucide/svelte/icons/table-2',
						'@lucide/svelte/icons/x'
					]
				},
				test: {
					name: 'client',
					browser: {
						enabled: true,
						provider: playwright(),
						instances: [{ browser: 'chromium', headless: true }],
						// Windows reserves the default port (63315) on some machines.
						...(process.env.VITEST_BROWSER_PORT
							? { api: Number(process.env.VITEST_BROWSER_PORT) }
							: {})
					},
					include: ['src/**/*.svelte.{test,spec}.{js,ts}'],
					exclude: ['src/lib/server/**']
				}
			},

			{
				extends: './vite.config.ts',
				test: {
					name: 'server',
					environment: 'node',
					include: ['src/**/*.{test,spec}.{js,ts}'],
					exclude: ['src/**/*.svelte.{test,spec}.{js,ts}']
				}
			}
		]
	}
});
