<script lang="ts">
	import { onMount } from 'svelte';
	import { postForm } from '../integrations/actions.ts';
	import { type SavedAnswer, type SettingsImport, when } from '../types.ts';
	import OAuthForm from './OAuthForm.svelte';
	import {
		ALL_LIBRARIES,
		contentKindFields,
		getJson,
		initialSelection,
		PLEX_KINDS,
		type PlexLibrary,
		type PlexSection,
		plexPrimaryLabel,
		plexStatusLabel,
		plexSubmitDisabled,
		reconcileSelection,
		sectionToLibrary,
		selectAllLibraries,
		toggleLibrary
	} from './plex.ts';
	import { sharedFields } from './sources.ts';

	/** Plex (import_data.html's Plex dialog): connect, then import with live status and libraries. */
	let {
		data,
		frequency,
		time,
		mode,
		busy,
		run
	}: {
		data: SettingsImport;
		frequency: string;
		time: string;
		mode: string;
		busy: boolean;
		run: (send: () => Promise<SavedAnswer>) => Promise<SavedAnswer | null>;
	} = $props();

	const plex = $derived(data.plex);
	const urls = $derived(data.urls);
	const watchlist = $derived(mode === 'watchlist');

	let liveState = $state('checking');
	let liveError = $state('');
	let live = $state<PlexLibrary[] | null>(null);
	let loading = $state(true);
	let selection = $state(initialSelection());
	let usernames = $state<string | null>(null);

	const libraries = $derived(live ?? plex?.libraries ?? []);
	const usernamesValue = $derived(usernames ?? plex?.usernames ?? '');
	const hasLibraries = $derived(libraries.length > 0);
	const disabled = $derived(busy || plexSubmitDisabled(liveState, mode, selection, hasLibraries));
	const allSelected = $derived(selection.libraries.includes(ALL_LIBRARIES));
	const musicSelected = $derived(libraries.filter((library) => library.is_music && selection.libraries.includes(library.value)));

	onMount(() => {
		if (!data.plex) return;
		const controller = new AbortController();
		void checkStatus(controller.signal);
		void loadSections(controller.signal);
		return () => controller.abort();
	});

	async function checkStatus(signal: AbortSignal) {
		try {
			const { ok, body } = await getJson<{ state?: string; error?: string }>(urls.plex_status, signal);
			if (!ok) throw new Error(body.error || 'Could not verify Plex connection.');
			liveState = body.state || 'error';
			liveError = body.error || '';
			if (liveState === 'error') {
				live = [];
				loading = false;
			}
		} catch (error) {
			if (signal.aborted) return;
			liveState = 'error';
			liveError = (error as Error).message || 'Could not verify Plex connection.';
			live = [];
			loading = false;
		}
	}

	async function loadSections(signal: AbortSignal) {
		loading = true;
		try {
			const { ok, body } = await getJson<{ sections?: PlexSection[]; error?: string }>(urls.plex_sections, signal);
			if (!ok) throw new Error(body.error || 'Could not load Plex libraries.');
			if (Array.isArray(body.sections) && liveState !== 'error') {
				live = body.sections.map(sectionToLibrary);
				selection = reconcileSelection(selection, live);
			}
			if (body.error) liveError = body.error;
			else if (liveState !== 'error') liveError = '';
		} catch (error) {
			if (signal.aborted) return;
			if (!liveError) liveError = (error as Error).message || 'Could not load Plex libraries.';
		} finally {
			if (!signal.aborted) loading = false;
		}
	}

	function submit(event: SubmitEvent) {
		event.preventDefault();
		if (disabled) return;
		void run(() =>
			postForm(urls.plex_import, {
				...sharedFields({ frequency, time, mode }),
				library: selection.libraries.length ? selection.libraries : [ALL_LIBRARIES],
				library_content_kind: contentKindFields(selection.kinds),
				plex_usernames: usernamesValue
			})
		);
	}

	const post = (url: string) => {
		if (!busy) void run(() => postForm(url));
	};
</script>

{#if !plex}
	<p class="ct-settings-note">Import watch and listening history from your Plex server.</p>
	<OAuthForm action={urls.plex_connect} button="Connect Plex" note="You will sign in on Plex and come back here." extra={{ auto_import: '0' }} {frequency} {time} {mode} />
{:else}
	<p>
		<span class={['ct-settings-badge', liveState === 'connected' && 'is-on']}>{plexStatusLabel(liveState)}</span>
	</p>
	{#if watchlist}
		<p class="ct-settings-note">
			Sync the connected Plex account's watchlist into Planning every {plex.watchlist_interval} minutes. Plex usernames still control webhook filtering.
		</p>
		<p class="ct-settings-note">Recurring sync: {plex.watchlist_sync_enabled ? 'Enabled' : 'Disabled'}</p>
		{#if plex.watchlist_last_synced_at}<p class="ct-settings-note">Last sync: {when(plex.watchlist_last_synced_at)}</p>{/if}
	{:else}
		<p class="ct-settings-note">Import Plex watch/listen history. Comma-separate username(s) to filter events sent to your webhook.</p>
	{/if}
	{#if liveError}<p class="ct-settings-status is-error" role="status">{liveError}</p>{/if}
	{#if watchlist && plex.watchlist_last_error}
		<p class="ct-settings-status is-error"><strong>Last watchlist sync error:</strong> {plex.watchlist_last_error}</p>
	{/if}
	{#if liveState === 'error'}
		<OAuthForm action={urls.plex_connect} button="Reconnect Plex" extra={{ auto_import: '0' }} {frequency} {time} {mode} />
	{/if}

	<form onsubmit={submit}>
		{#if !watchlist}
			<fieldset class="ct-settings-field ct-import-libraries">
				<legend>Libraries</legend>
				<label class="ct-import-check-row">
					<input type="checkbox" checked={allSelected} disabled={busy} onchange={() => (selection = selectAllLibraries())} />
					All libraries
				</label>
				{#each libraries as library (library.value)}
					<label class="ct-import-check-row">
						<input
							type="checkbox"
							checked={selection.libraries.includes(library.value)}
							disabled={busy}
							onchange={() => (selection = toggleLibrary(selection, library))}
						/>
						{library.label}
					</label>
				{/each}
			</fieldset>
			{#if !hasLibraries && loading}
				<p class="ct-settings-note">Checking Plex libraries...</p>
			{:else if !hasLibraries && liveState === 'error'}
				<p class="ct-settings-note">Reconnect Plex to refresh libraries.</p>
			{:else if !hasLibraries}
				<p class="ct-settings-note">No libraries detected yet. Reconnect Plex to refresh.</p>
			{/if}
			{#each musicSelected as library (library.value)}
				<label class="ct-settings-field">
					Content Type: {library.label}
					<select
						value={selection.kinds[library.value] ?? 'auto'}
						disabled={busy}
						onchange={(event) => (selection = { ...selection, kinds: { ...selection.kinds, [library.value]: event.currentTarget.value } })}
					>
						{#each PLEX_KINDS as [kind, label] (kind)}
							<option value={kind}>{label}</option>
						{/each}
					</select>
				</label>
			{/each}
			<p class="ct-settings-note">
				Audiobooks kept in a Plex Music library are tracked as books instead of music. Select a music library above and choose Auto-detect, Music, or Audiobooks for it.
			</p>
		{/if}
		<label class="ct-settings-field">
			Plex usernames
			<input
				type="text"
				name="plex_usernames"
				autocomplete="off"
				spellcheck="false"
				placeholder="username 1, username 2"
				value={usernamesValue}
				oninput={(event) => (usernames = event.currentTarget.value)}
			/>
		</label>
		<div class="ct-settings-actions">
			<button type="submit" class="ct-settings-button is-primary" {disabled}>{plexPrimaryLabel(mode, plex.watchlist_sync_enabled)}</button>
			{#if watchlist && plex.watchlist_sync_enabled}
				<button type="button" class="ct-settings-button is-danger" disabled={busy} onclick={() => post(urls.plex_disable_watchlist)}>Disable Watchlist Sync</button>
			{/if}
			<button type="button" class="ct-settings-button is-danger" disabled={busy} onclick={() => post(urls.plex_disconnect)}>Disconnect</button>
		</div>
	</form>
{/if}
