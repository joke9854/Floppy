<script lang="ts">
	import ExternalLink from '@lucide/svelte/icons/external-link';
	import { ABOUT_RESOURCES, st } from './strings.ts';
	import type { SettingsScreen } from './types.ts';

	/**
	 * About (about.html): the description, installing the PWA, project links,
	 * the API documents (open or download), metadata attributions, the
	 * license, and the running version.
	 */
	let { screen }: { screen: SettingsScreen } = $props();
	const about = $derived(screen.about!);

	const specs = $derived([
		{
			name: 'API Reference',
			purpose: 'Interactive index, tasks, authentication recipes, and curl cheat sheets',
			format: 'HTML Docs',
			href: about.urls.docs,
			download: ''
		},
		{
			name: 'Verified API Schema',
			purpose: 'Reviewed 41-operation subset for stable integrations and MCP grounding',
			format: 'OpenAPI 3.0.3 (YAML)',
			href: about.urls.openapi,
			download: 'openapi.yaml'
		},
		{
			name: 'Domain Context (JSON-LD)',
			purpose: 'Semantic RDF / schema.org vocabulary mapping for Floppy entities',
			format: 'JSON-LD 1.1',
			href: about.urls.jsonld,
			download: 'context.jsonld'
		},
		{
			name: 'Full Diagnostic API Schema',
			purpose: 'Dynamically generated OpenAPI schema covering all active routes on this instance',
			format: 'Live OpenAPI (YAML)',
			href: about.urls.schema,
			download: 'openapi-live.yaml'
		},
		{
			name: 'Asynchronous Channels (AsyncAPI)',
			purpose: 'Inbound webhook routes, Celery queues, and worker concurrency profiles',
			format: 'AsyncAPI 3.0.0 (JSON)',
			href: about.urls.asyncapi,
			download: 'asyncapi.json'
		}
	]);

	const providers = [
		{ name: 'The Movie Database (TMDB)', media: 'Movies, TV Shows, Seasons, Episodes & Cast/Crew Credits', href: 'https://www.themoviedb.org/' },
		{ name: 'IGDB', media: 'Video Games, Platforms, Developers & Publishers', href: 'https://www.igdb.com/' },
		{ name: 'MusicBrainz', media: 'Music Releases, Artists, Discographies & Tracklists', href: 'https://musicbrainz.org/' },
		{ name: 'Hardcover & Open Library', media: 'Books, Authors, Editions & Page Counts', href: 'https://hardcover.app/' },
		{ name: 'JustWatch', media: 'Streaming, Rent & Buy Availability Across Regions', href: 'https://www.justwatch.com/' },
		{ name: 'OpenSubtitles', media: 'Multilingual Subtitles Synchronization', href: 'https://www.opensubtitles.com/' },
		{ name: 'Pocket Casts', media: 'Podcast RSS Directories, Episode Feeds & Artwork', href: 'https://pocketcasts.com/' }
	];

	// The browser's install prompt, when the shell kept one (window.floppyPwa).
	type Pwa = { deferredPrompt?: { prompt(): Promise<void>; userChoice: Promise<{ outcome: string }> } | null; isStandalone?: () => boolean };
	let canInstall = $state(false);
	let installStatus = $state('');
	$effect(() => {
		const pwa = (window as unknown as { floppyPwa?: Pwa }).floppyPwa;
		canInstall = Boolean(pwa?.deferredPrompt) && !pwa?.isStandalone?.();
	});

	async function install() {
		const pwa = (window as unknown as { floppyPwa?: Pwa }).floppyPwa;
		const prompt = pwa?.deferredPrompt;
		canInstall = false;
		if (!prompt || !pwa) return;
		pwa.deferredPrompt = null;
		try {
			await prompt.prompt();
			const choice = await prompt.userChoice;
			installStatus =
				choice.outcome === 'accepted'
					? 'Installing Floppy. Look for it alongside your other apps.'
					: 'Installation dismissed. You can still add Floppy using the steps below.';
		} catch {
			installStatus = 'Your browser could not open the install prompt. Use the steps below instead.';
		}
	}
</script>

<section class="ct-settings-section">
	<h2>{st.about}</h2>
	<h3>{st.description}</h3>
	<p class="ct-settings-note">{st.descriptionBody}</p>
	<p class="ct-settings-note">{st.forkNote}</p>
	<p class="ct-settings-note">{st.editionNote}</p>
</section>

<section class="ct-settings-section">
	<h2>{st.install}</h2>
	<p class="ct-settings-note">{st.installNote}</p>
	{#if canInstall}<div><button type="button" class="ct-settings-button is-primary" onclick={install}>{st.install}</button></div>{/if}
	{#if installStatus}<p class="ct-settings-status" role="status">{installStatus}</p>{/if}
	<p class="ct-settings-note">{st.installSteps}</p>
</section>

<section class="ct-settings-section">
	<h2>{st.resources}</h2>
	<ul class="ct-settings-rows">
		{#each ABOUT_RESOURCES as resource (resource.name)}
			<li class="ct-settings-row">
				<span>{resource.name}<small>{resource.purpose}</small></span>
				<a class="ct-settings-link" href={resource.href} target="_blank" rel="noopener noreferrer">
					{resource.action} <ExternalLink class="inline size-3" aria-hidden="true" /><span class="sr-only">{st.newTab}</span>
				</a>
			</li>
		{/each}
	</ul>
</section>

<section class="ct-settings-section">
	<h2>{st.specs}</h2>
	<ul class="ct-settings-rows">
		{#each specs as spec (spec.name)}
			<li class="ct-settings-row">
				<span>{spec.name}<small>{spec.purpose} · {spec.format}</small></span>
				<a class="ct-settings-link" href={spec.href} target="_blank" rel="noopener noreferrer">{st.open}<span class="sr-only">{st.newTab}</span></a>
				{#if spec.download}<a class="ct-settings-link" href={spec.href} download={spec.download}>{st.download}</a>{/if}
			</li>
		{/each}
	</ul>
</section>

<section class="ct-settings-section">
	<h2>Metadata & Attributions</h2>
	<ul class="ct-settings-rows">
		{#each providers as provider (provider.name)}
			<li class="ct-settings-row">
				<span>{provider.name}<small>{provider.media}</small></span>
				<a class="ct-settings-link" href={provider.href} target="_blank" rel="noopener noreferrer"
					><ExternalLink class="size-4" aria-hidden="true" /><span class="sr-only">{provider.name} {st.newTab}</span></a
				>
			</li>
		{/each}
	</ul>
</section>

<section class="ct-settings-section">
	<h2>{st.license}</h2>
	<ul class="ct-settings-rows">
		<li class="ct-settings-row">
			<span>Floppy Application<small>GNU Affero General Public License v3.0 (AGPL-3.0)</small></span>
			<a class="ct-settings-link" href="https://github.com/dannyvfilms/Floppy/blob/release/LICENSE" target="_blank" rel="noopener noreferrer"
				>{st.viewLicense}<span class="sr-only">{st.newTab}</span></a
			>
		</li>
		<li class="ct-settings-row">
			<span>Upstream Heritage<small>Yamtrack (Original codebase fork; CSV exports supported)</small></span>
			<a class="ct-settings-link" href="https://github.com/FuzzyGrim/Yamtrack" target="_blank" rel="noopener noreferrer"
				>Upstream Repo<span class="sr-only">{st.newTab}</span></a
			>
		</li>
	</ul>
	<p class="ct-settings-status">{st.version} <b>{about.version}</b>{#if about.commit} ({about.commit}){/if}</p>
</section>
