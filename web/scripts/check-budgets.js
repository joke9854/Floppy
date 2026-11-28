// @ts-check
/**
 * Bundle budgets (v2 P3-D): what one page makes the browser download, gzip
 * sizes, from the client build. Run after `npm run build`.
 *
 * A page loads SvelteKit's entry files, its layouts and its page component
 * with their imports and CSS. The route files are found through the nodes
 * SvelteKit generates, so the budget follows the app, not a folder total
 * that grows with every screen.
 *
 * 115 kB for pages with the shell (raised from 110 on 2026-11-23, P4-I1):
 * every new route grows the shared route table and re-splits shared code, so
 * Library, Discover and the detail page had no headroom left. New sections
 * still load lazily where they can.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { gzipSync } from 'node:zlib';

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
const CLIENT = join(ROOT, 'build/client/next');
const VITE_MANIFEST = join(ROOT, '.svelte-kit/output/client/.vite/manifest.json');
const NODES = '.svelte-kit/generated/build/client-optimized/nodes/';

/** Page name, its route files (layouts first), and its gzip budget in kB. */
const PAGES = [
	{
		name: 'Sign-in',
		routes: ['src/routes/+layout.svelte', 'src/routes/login/+page.svelte'],
		budgetKb: 60
	},
	{
		name: 'Start page with the shell',
		routes: [
			'src/routes/+layout.svelte',
			'src/routes/(app)/+layout.svelte',
			'src/routes/(app)/+page.svelte'
		],
		budgetKb: 115
	},
	{
		name: 'Library with the shell',
		routes: [
			'src/routes/+layout.svelte',
			'src/routes/(app)/+layout.svelte',
			'src/routes/(app)/library/[type]/+page.svelte'
		],
		budgetKb: 115
	},
	{
		name: 'Detail page with the shell',
		routes: [
			'src/routes/+layout.svelte',
			'src/routes/(app)/+layout.svelte',
			'src/routes/(app)/details/[source]/[type]/[id]/[[title]]/+page.svelte'
		],
		budgetKb: 115
	},
	{
		name: 'Episode page with the shell',
		routes: [
			'src/routes/+layout.svelte',
			'src/routes/(app)/+layout.svelte',
			'src/routes/(app)/details/[source]/tv/[id]/[title]/season/[season]/episode/[episode]/+page.svelte'
		],
		budgetKb: 115
	},
	{
		name: 'Anime episode page with the shell',
		routes: [
			'src/routes/+layout.svelte',
			'src/routes/(app)/+layout.svelte',
			'src/routes/(app)/details/[source]/anime/[id]/[title]/season/[season]/episode/[episode]/+page.svelte'
		],
		budgetKb: 115
	},
	{
		name: 'List page with the shell',
		routes: [
			'src/routes/+layout.svelte',
			'src/routes/(app)/+layout.svelte',
			'src/routes/(app)/list/[ref]/+page.svelte'
		],
		budgetKb: 115
	},
	{
		name: 'Settings with the shell',
		routes: [
			'src/routes/+layout.svelte',
			'src/routes/(app)/+layout.svelte',
			'src/routes/(app)/settings/[page]/+page.svelte'
		],
		budgetKb: 115
	},
	{
		name: 'Lists with the shell',
		routes: [
			'src/routes/+layout.svelte',
			'src/routes/(app)/+layout.svelte',
			'src/routes/(app)/lists/+page.svelte'
		],
		budgetKb: 115
	},
	{
		name: 'Statistics with the shell',
		routes: [
			'src/routes/+layout.svelte',
			'src/routes/(app)/+layout.svelte',
			'src/routes/(app)/statistics/+page.svelte'
		],
		budgetKb: 115
	},
	{
		name: 'Discover with the shell',
		routes: [
			'src/routes/+layout.svelte',
			'src/routes/(app)/+layout.svelte',
			'src/routes/(app)/discover/+page.svelte'
		],
		budgetKb: 115
	},
	{
		name: 'Calendar with the shell',
		routes: [
			'src/routes/+layout.svelte',
			'src/routes/(app)/+layout.svelte',
			'src/routes/(app)/calendar/+page.svelte'
		],
		budgetKb: 115
	},
	{
		name: 'History with the shell',
		routes: [
			'src/routes/+layout.svelte',
			'src/routes/(app)/+layout.svelte',
			'src/routes/(app)/history/+page.svelte'
		],
		budgetKb: 115
	},
	{
		name: 'Person page with the shell',
		routes: [
			'src/routes/+layout.svelte',
			'src/routes/(app)/+layout.svelte',
			'src/routes/(app)/person/[source]/[id]/[[name]]/+page.svelte'
		],
		budgetKb: 115
	},
	{
		name: 'Studio page with the shell',
		routes: [
			'src/routes/+layout.svelte',
			'src/routes/(app)/+layout.svelte',
			'src/routes/(app)/studio/[source]/[id]/[[name]]/+page.svelte'
		],
		budgetKb: 115
	},
	{
		name: 'Artist page with the shell',
		routes: [
			'src/routes/+layout.svelte',
			'src/routes/(app)/+layout.svelte',
			'src/routes/(app)/details/music/artist/[artistId]/[slug]/+page.svelte'
		],
		budgetKb: 115
	},
	{
		name: 'Album page with the shell',
		routes: [
			'src/routes/+layout.svelte',
			'src/routes/(app)/+layout.svelte',
			'src/routes/(app)/details/music/artist/[artistId]/[slug]/album/[albumId]/[albumSlug]/+page.svelte'
		],
		budgetKb: 115
	},
	{
		name: 'Podcast page with the shell',
		routes: [
			'src/routes/+layout.svelte',
			'src/routes/(app)/+layout.svelte',
			'src/routes/(app)/details/[source]/podcast/[id]/[[title]]/+page.svelte'
		],
		budgetKb: 115
	}
];

/** @type {Record<string, {file: string, imports?: string[], css?: string[], isEntry?: boolean, src?: string}>} */
const manifest = JSON.parse(readFileSync(VITE_MANIFEST, 'utf8'));

/** The manifest key of the generated node that renders `route`. */
function nodeFor(route) {
	for (const key of Object.keys(manifest)) {
		if (!key.startsWith(NODES)) continue;
		const source = readFileSync(join(ROOT, key), 'utf8');
		if (source.includes(`/${route}"`)) return key;
	}
	throw new Error(`No client node renders ${route}`);
}

/** Every file a manifest entry loads: itself, its static imports and CSS. */
function closure(keys) {
	const files = new Set();
	const seen = new Set();
	const visit = (key) => {
		if (seen.has(key)) return;
		seen.add(key);
		const entry = manifest[key];
		files.add(entry.file);
		for (const css of entry.css ?? []) files.add(css);
		for (const imported of entry.imports ?? []) visit(imported);
	};
	keys.forEach(visit);
	return files;
}

const entries = Object.keys(manifest).filter(
	(key) => manifest[key].isEntry && !key.startsWith(NODES)
);
const gzipKb = (file) => gzipSync(readFileSync(join(CLIENT, file))).length / 1024;

let failed = false;
for (const page of PAGES) {
	const files = closure([...entries, ...page.routes.map(nodeFor)]);
	const js = [...files]
		.filter((file) => file.endsWith('.js'))
		.reduce((sum, file) => sum + gzipKb(file), 0);
	const css = [...files]
		.filter((file) => file.endsWith('.css'))
		.reduce((sum, file) => sum + gzipKb(file), 0);
	const total = js + css;
	const ok = total <= page.budgetKb;
	failed ||= !ok;
	console.log(
		`${ok ? 'ok  ' : 'OVER'} ${page.name}: ${total.toFixed(1)} kB gzip (JS ${js.toFixed(1)}, CSS ${css.toFixed(1)}; ${files.size} files) / budget ${page.budgetKb} kB`
	);
}
if (failed) {
	console.error(
		'A page is over its bundle budget. Trim it, or raise the budget in scripts/check-budgets.js on purpose.'
	);
	process.exit(1);
}
