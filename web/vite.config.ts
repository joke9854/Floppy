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
			['/api', '/_allauth', '/accounts', '/static', '/image-cache'].map((path) => [
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
				test: {
					name: 'client',
					browser: {
						enabled: true,
						provider: playwright(),
						instances: [{ browser: 'chromium', headless: true }]
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
