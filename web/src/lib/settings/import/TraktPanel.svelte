<script lang="ts">
	import ExternalLink from '@lucide/svelte/icons/external-link';
	import { postForm } from '../integrations/actions.ts';
	import CopyField from '../integrations/CopyField.svelte';
	import { st } from '../strings.ts';
	import type { SavedAnswer, SettingsImport } from '../types.ts';
	import OAuthForm from './OAuthForm.svelte';
	import { PERIODIC_UPLOAD_NOTE, sharedFields, standardImportsDisabled } from './sources.ts';
	import { postUpload } from './upload.ts';

	/** Trakt (import_data.html's Trakt dialog): public username, private (OAuth) or a data export. */
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

	let profile = $state('public');
	let user = $state('');
	let picked = $state<File[]>([]);
	let nonce = $state(0);

	const configured = $derived(data.trakt.configured);
	const choice = $derived(configured ? profile : 'csv');
	const standardOff = $derived(standardImportsDisabled(mode));
	const exportOff = $derived(frequency !== 'once');

	async function importPublic(event: SubmitEvent) {
		event.preventDefault();
		if (busy) return;
		const answer = await run(() => postForm(data.urls.trakt_public, { ...sharedFields({ frequency, time, mode }), user: user.trim() }));
		if (answer?.saved) user = '';
	}

	async function importExport(event: SubmitEvent) {
		event.preventDefault();
		if (busy || exportOff || !picked.length) return;
		const answer = await run(() => postUpload(data.urls.trakt_export, { mode }, { trakt_export: picked }));
		if (answer?.saved) {
			picked = [];
			nonce += 1;
		}
	}
</script>

{#if !configured}
	<p class="ct-settings-note">
		Trakt now requires VIP to register new API applications, so username-based import is unavailable unless <code>TRAKT_API</code> and
		<code>TRAKT_API_SECRET</code> are already set. Use a Trakt data export instead.
	</p>
{:else}
	<label class="ct-settings-field">
		Profile
		<select bind:value={profile}>
			<option value="public">Public profile</option>
			<option value="private">Private profile (OAuth)</option>
			<option value="csv">Data export file</option>
		</select>
	</label>
{/if}

{#if choice === 'public'}
	<form onsubmit={importPublic}>
		<label class="ct-settings-field">
			Public Trakt username
			<input type="text" name="user" autocomplete="off" spellcheck="false" placeholder="Public Trakt username" bind:value={user} />
		</label>
		<div class="ct-settings-actions">
			<button type="submit" class="ct-settings-button is-primary" disabled={busy || standardOff || !user.trim()}>Import</button>
		</div>
	</form>
{:else if choice === 'private'}
	<div class="ct-import-info">
		<p><strong>Private Profile Import (OAuth)</strong></p>
		<ol>
			<li>
				Create a Trakt application at
				<a class="ct-settings-link" href="https://trakt.tv/oauth/applications" target="_blank" rel="noopener noreferrer"
					>Trakt API Apps <ExternalLink class="inline size-4" aria-hidden="true" /><span class="sr-only">{st.newTab}</span></a
				>.
			</li>
			<li>Set the Redirect URI to the value below.</li>
			<li>Set <code>TRAKT_API</code> and <code>TRAKT_API_SECRET</code> in your environment.</li>
		</ol>
		<CopyField value={data.trakt.redirect_uri} label="Redirect URI" />
		{#if data.trakt.redirect_capable}
			<p>Behind reverse proxies, also set <code>URLS=https://your_domain.com</code> so Floppy builds the correct callback URL.</p>
		{:else}
			<p>
				This instance is not served over HTTPS, and Trakt only accepts HTTPS redirects, so Floppy will show you a code to enter at
				<code>trakt.tv/activate</code> instead. Set <code>URLS=https://your_domain.com</code> if you would rather use the one-click browser flow.
			</p>
		{/if}
	</div>
	<OAuthForm action={data.urls.trakt_oauth} button="Connect with Trakt & Import" disabled={standardOff} {frequency} {time} {mode} />
{:else}
	<div class="ct-import-info">
		<p>
			No Trakt account anymore? Upload the <code>.zip</code> from a Trakt data export to import your history, ratings, watchlist, collection and
			lists. Individual <code>.json</code> files and the older <code>.csv</code> export also work.
		</p>
		<p>Importing lists replaces any lists previously imported from Trakt.</p>
	</div>
	{#if exportOff}<p class="ct-settings-note">{PERIODIC_UPLOAD_NOTE}</p>{/if}
	{#key nonce}
		<form onsubmit={importExport}>
			<label class="ct-settings-field">
				Select Export File
				<input
					type="file"
					name="trakt_export"
					accept=".zip,.json,.csv"
					multiple
					disabled={exportOff || busy}
					onchange={(event) => (picked = Array.from((event.currentTarget as HTMLInputElement).files ?? []))}
				/>
			</label>
			<div class="ct-settings-actions">
				<button type="submit" class="ct-settings-button is-primary" disabled={exportOff || busy || !picked.length}>Import</button>
			</div>
		</form>
	{/key}
{/if}
