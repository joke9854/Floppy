<script lang="ts">
	import { page } from '$app/state';
	import Download from '@lucide/svelte/icons/download';
	import ExternalLink from '@lucide/svelte/icons/external-link';
	import FileUp from '@lucide/svelte/icons/file-up';
	import Check from '@lucide/svelte/icons/check';
	import ImportActivity from './import/ImportActivity.svelte';
	import ImportDialog from './import/ImportDialog.svelte';
	import { IMPORT_SOURCES } from './import/sources.ts';
	import { postForm } from './integrations/actions.ts';
	import { st } from './strings.ts';
	import type { SettingsScreen } from './types.ts';

	/**
	 * Import (import_data.html): the import preferences, a tile grid of sources
	 * (a web dialog for the K1 sources, the Django page for the rest) and the
	 * activity panel. Frequency, time and mode are also what every import form
	 * posts.
	 */
	let { screen }: { screen: SettingsScreen } = $props();
	const data = $derived(screen.import_!);
	const urls = $derived(data.urls);

	// svelte-ignore state_referenced_locally
	let frequency = $state(screen.import_!.settings.frequency);
	// svelte-ignore state_referenced_locally
	let time = $state(screen.import_!.settings.time);
	// svelte-ignore state_referenced_locally
	let mode = $state(screen.import_!.settings.mode);
	let tag = $state('all');
	let saving = $state(false);
	let notice = $state<{ text: string; failed: boolean } | null>(null);
	let activity = $state<{ refresh: () => Promise<void> }>();

	const onboarding = $derived(!!page.url.searchParams.get('onboarding'));
	// svelte-ignore state_referenced_locally
	const deepLink = page.url.searchParams.get('open') ?? '';
	// svelte-ignore state_referenced_locally
	let openKey = $state(
		screen.import_!.tiles.some((tile) => tile.key === deepLink && tile.web) && IMPORT_SOURCES[deepLink] ? deepLink : ''
	);

	const modeHint = $derived(data.settings.mode_choices.find((choice) => choice.value === mode)?.hint ?? '');
	const tagLabel = $derived(data.media_tags.find((item) => item.value === tag)?.label ?? '');
	const tiles = $derived(data.tiles.filter((tile) => tag === 'all' || tile.tags.includes(tag)));

	async function save() {
		saving = true;
		notice = null;
		try {
			const answer = await postForm(data.settings.save_url, { import_frequency: frequency, import_time: time, import_mode: mode });
			notice = { text: answer.saved ? st.saved : (answer.message ?? st.failed), failed: !answer.saved };
		} catch {
			notice = { text: st.failed, failed: true };
		} finally {
			saving = false;
		}
	}

	function openTile(key: string) {
		if (IMPORT_SOURCES[key]) openKey = key;
	}
</script>

{#if onboarding}
	<section class="ct-settings-section">
		<p class="ct-settings-note">You're connecting this service as part of guided setup. Finish here, then continue the wizard.</p>
		<div class="ct-settings-actions" style="justify-content: flex-start">
			<a class="ct-settings-button is-primary" href={urls.onboarding} data-sveltekit-reload>Continue Guided Setup</a>
		</div>
	</section>
{/if}

<section class="ct-settings-section">
	<div>
		<h2>Import Settings</h2>
		<p class="ct-settings-note">Configure your import preferences.</p>
	</div>
	<label class="ct-settings-field">
		Import Frequency
		<select bind:value={frequency} disabled={data.is_demo || saving} onchange={save}>
			{#each data.settings.frequency_choices as choice (choice.value)}<option value={choice.value} title={choice.hint}>{choice.label}</option>{/each}
		</select>
	</label>
	{#if frequency !== 'once'}
		<label class="ct-settings-field">
			Import Time
			<input type="time" bind:value={time} disabled={data.is_demo || saving} onchange={save} />
		</label>
	{/if}
	<label class="ct-settings-field">
		Import Mode
		<select bind:value={mode} disabled={data.is_demo || saving} onchange={save}>
			{#each data.settings.mode_choices as choice (choice.value)}<option value={choice.value} title={choice.hint}>{choice.label}</option>{/each}
		</select>
		{#if modeHint}<small class="ct-settings-note">{modeHint}</small>{/if}
	</label>
	{#if notice}<p class={['ct-settings-status', notice.failed && 'is-error']} role="status">{notice.text}</p>{/if}
</section>

<section class="ct-settings-section">
	<div class="ct-settings-actions is-split">
		<h2>Import Sources</h2>
		<a class="ct-settings-button" href={urls.restart_setup} data-sveltekit-reload>Run guided setup</a>
	</div>
	<p class="ct-settings-note">
		Some of these require additional configuration, check the
		<a class="ct-settings-link" href={urls.guide} target="_blank" rel="noopener noreferrer"
			>import configuration guide <ExternalLink class="inline size-4" aria-hidden="true" /><span class="sr-only">{st.newTab}</span></a
		>.
	</p>
	<div class="ct-import-filter">
		<span class="ct-settings-note" id="ct-import-filter-label">Browse by media type:</span>
		<div class="ct-settings-actions" role="group" aria-labelledby="ct-import-filter-label" style="justify-content: flex-start">
			{#each data.media_tags as item (item.value)}
				<button
					type="button"
					class={['ct-settings-button', tag === item.value && 'is-primary']}
					aria-pressed={tag === item.value}
					onclick={() => (tag = item.value)}>{item.label}</button
				>
			{/each}
		</div>
		<p class="ct-settings-note">Showing {tagLabel}.</p>
	</div>
	<ul class="ct-import-grid">
		{#each tiles as tile (tile.key)}
			<li>
				{#snippet body()}
					<span class="ct-import-tile-logo">
						{#if tile.logo}<img src={tile.logo} alt="" />{:else}<FileUp class="size-6" aria-hidden="true" />{/if}
					</span>
					<span class="ct-import-tile-name">
						{tile.name}
						{#if tile.connected}<span class="ct-import-check" title={tile.badge}><Check class="size-3" aria-hidden="true" /><span class="sr-only">{tile.badge}</span></span>{/if}
					</span>
					<small>{tile.description}</small>
				{/snippet}
				{#if tile.web}
					<button type="button" class="ct-import-tile" onclick={() => openTile(tile.key)}>{@render body()}</button>
				{:else}
					<a class="ct-import-tile" href={tile.django_url} data-sveltekit-reload>{@render body()}</a>
				{/if}
			</li>
		{/each}
		{#if tag !== 'none'}
			<li>
				<a class="ct-import-tile" href={urls.template} download>
					<span class="ct-import-tile-logo"><Download class="size-6" aria-hidden="true" /></span>
					<span class="ct-import-tile-name">Import Template</span>
					<small>Download a starter template, then re-upload it to your library.</small>
				</a>
			</li>
		{/if}
	</ul>
</section>

<ImportActivity bind:this={activity} initial={data.activity} url={urls.activity} />

{#if openKey}
	<ImportDialog
		sourceKey={openKey}
		{data}
		{frequency}
		{time}
		{mode}
		onclose={() => (openKey = '')}
		onsaved={() => void activity?.refresh()}
	/>
{/if}
