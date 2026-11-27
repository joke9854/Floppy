<script lang="ts">
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import { invalidate, pushState } from '$app/navigation';
	import { page } from '$app/state';
	import ApiPanel from './integrations/ApiPanel.svelte';
	import EmbyPanel from './integrations/EmbyPanel.svelte';
	import JellyfinPanel from './integrations/JellyfinPanel.svelte';
	import KodiPanel from './integrations/KodiPanel.svelte';
	import NuvioPanel from './integrations/NuvioPanel.svelte';
	import PlexPanel from './integrations/PlexPanel.svelte';
	import SeerrPanel from './integrations/SeerrPanel.svelte';
	import StremioPanel from './integrations/StremioPanel.svelte';
	import SyncPanel from './integrations/SyncPanel.svelte';
	import { postForm } from './integrations/actions.ts';
	import { st } from './strings.ts';
	import type { SettingsScreen } from './types.ts';

	/**
	 * Integrations (integrations.html): the card grid, one panel per service,
	 * matching review and the onboarding banner. The open panel is a tag kept in
	 * the URL with shallow routing, so no data reloads when it changes.
	 */
	let { screen }: { screen: SettingsScreen } = $props();
	const integrations = $derived(screen.integrations!);

	const local = {
		intro: 'Connect the places you watch. Floppy marks plays as they happen.',
		servers: 'Media servers',
		apps: 'Apps & services',
		more: 'API key, app tokens, watched-state sync and Nuvio',
		back: 'Integrations',
		review: 'Matching review',
		reviewNote: 'These provider identities were not safe to match automatically.',
		saved: 'Saved match decisions',
		savedNote: 'These decisions are applied to future Plex and Trakt imports.',
		fix: 'Fix match',
		edit: 'Edit',
		ignore: 'Ignore',
		remove: 'Remove',
		onboarding: "You're setting this up as part of guided setup. Finish here, then continue the wizard.",
		continue: 'Continue Guided Setup'
	};
	const tags = ['grid', 'api', 'jellyfin', 'plex', 'emby', 'kodi', 'stremio', 'seerr', 'nuvio', 'sync', 'all'];

	const open = $derived.by(() => {
		const tag = page.state.open ?? page.url.searchParams.get('open') ?? 'grid';
		return tags.includes(tag) ? tag : 'grid';
	});
	const onboarding = $derived(Boolean(page.url.searchParams.get('onboarding')));
	const show = (...panels: string[]) => panels.includes(open);

	let busy = $state(false);
	let notice = $state<{ text: string; failed: boolean } | null>(null);

	function openPanel(tag: string) {
		const url = new URL(page.url.href);
		if (tag === 'grid') url.searchParams.delete('open');
		else url.searchParams.set('open', tag);
		url.hash = '';
		pushState(url, { open: tag });
		window.scrollTo(0, 0);
	}

	function stateText(card: { key: string; state: string; count: number }) {
		if (card.state === 'broken') return 'Needs attention';
		if (card.state === 'connected') {
			const base = card.key === 'trakt' ? 'Configured' : 'Connected';
			return card.count > 0 ? `${base} · ${card.count} ${card.count === 1 ? 'library' : 'libraries'}` : base;
		}
		return card.state === 'unknown' ? '' : 'Not connected';
	}

	function actionText(state: string) {
		return state === 'broken' ? 'Fix' : state === 'connected' ? 'Manage' : state === 'unknown' ? 'Set up' : 'Connect';
	}

	async function decide(url: string) {
		busy = true;
		notice = null;
		try {
			const answer = await postForm(url);
			notice = { text: answer.saved ? answer.message || st.saved : (answer.message ?? st.failed), failed: !answer.saved };
			if (answer.saved) await invalidate('floppy:settings');
		} catch {
			notice = { text: st.failed, failed: true };
		} finally {
			busy = false;
		}
	}
</script>

{#snippet group(title: string, section: string)}
	<section class="ct-settings-section">
		<h2>{title}</h2>
		<ul class="ct-settings-rows">
			{#each integrations.cards.filter((card) => card.section === section) as card (card.key)}
				{@const action = actionText(card.state)}
				<li class="ct-settings-row">
					<img src={card.logo} alt="" width="28" height="28" class="size-7 shrink-0" />
					<span>
						{card.name}
						<small>{card.method}{stateText(card) ? ` · ${stateText(card)}` : ''}</small>
					</span>
					{#if card.href}
						<a class="ct-settings-button" href={card.href} data-sveltekit-reload aria-label="{action} {card.name}">{action}</a>
					{:else}
						<button type="button" class="ct-settings-button" aria-label="{action} {card.name}" onclick={() => openPanel(card.key)}>{action}</button>
					{/if}
				</li>
			{/each}
		</ul>
	</section>
{/snippet}

{#if onboarding}
	<section class="ct-settings-section" role="status">
		<p class="ct-settings-note">{local.onboarding}</p>
		<div class="ct-settings-actions">
			<a class="ct-settings-button is-primary" href={integrations.onboarding_url} data-sveltekit-reload>{local.continue}</a>
		</div>
	</section>
{/if}

{#if open === 'grid'}
	<p class="ct-settings-note">{local.intro}</p>
	{@render group(local.servers, 'servers')}
	{@render group(local.apps, 'apps')}
	<button type="button" class="ct-settings-link text-left" onclick={() => openPanel('api')}>{local.more}</button>
{:else}
	<div>
		<button type="button" class="ct-settings-button" onclick={() => openPanel('grid')}>
			<ChevronLeft class="size-4" aria-hidden="true" />{local.back}
		</button>
	</div>
{/if}

{#if integrations.matches.review.length}
	<section class="ct-settings-section">
		<div>
			<h2>{local.review}</h2>
			<p class="ct-settings-note">{local.reviewNote}</p>
		</div>
		<ul class="ct-settings-rows">
			{#each integrations.matches.review as reference (reference.id)}
				<li class="ct-settings-row">
					<span>{reference.title} ({reference.integration})</span>
					{#if reference.fix_url}<a class="ct-settings-button" href={reference.fix_url} data-sveltekit-reload>{local.fix}</a>{/if}
					<button type="button" class="ct-settings-button" disabled={busy} onclick={() => decide(reference.ignore_url)}>{local.ignore}</button>
				</li>
			{/each}
		</ul>
		{#if notice}<span class={['ct-settings-status', notice.failed && 'is-error']} role="status">{notice.text}</span>{/if}
	</section>
{/if}

{#if integrations.matches.saved.length}
	<section class="ct-settings-section">
		<div>
			<h2>{local.saved}</h2>
			<p class="ct-settings-note">{local.savedNote}</p>
		</div>
		<ul class="ct-settings-rows">
			{#each integrations.matches.saved as reference (reference.id)}
				<li class="ct-settings-row">
					<span>{reference.title} ({reference.integration})<small>{reference.status}</small></span>
					{#if reference.edit_url}<a class="ct-settings-button" href={reference.edit_url} data-sveltekit-reload>{local.edit}</a>{/if}
					<button type="button" class="ct-settings-button" disabled={busy} onclick={() => decide(reference.remove_url)}>{local.remove}</button>
				</li>
			{/each}
		</ul>
		{#if notice && !integrations.matches.review.length}<span class={['ct-settings-status', notice.failed && 'is-error']} role="status">{notice.text}</span>{/if}
	</section>
{/if}

{#if show('api')}<ApiPanel {integrations} />{/if}
{#if show('jellyfin', 'all')}<JellyfinPanel {integrations} />{/if}
{#if show('plex', 'all')}<PlexPanel {integrations} />{/if}
{#if show('emby', 'all')}<EmbyPanel {integrations} />{/if}
{#if show('kodi', 'all')}<KodiPanel {integrations} />{/if}
{#if show('stremio', 'all')}<StremioPanel {integrations} />{/if}
{#if show('seerr', 'all')}<SeerrPanel {integrations} />{/if}
{#if show('api', 'sync', 'all')}<SyncPanel {integrations} />{/if}
{#if show('api', 'nuvio', 'all')}<NuvioPanel {integrations} />{/if}
