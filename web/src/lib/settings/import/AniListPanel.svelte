<script lang="ts">
	import { postForm } from '../integrations/actions.ts';
	import type { SavedAnswer, SettingsImport } from '../types.ts';
	import OAuthForm from './OAuthForm.svelte';
	import { sharedFields, standardImportsDisabled } from './sources.ts';

	/** AniList (import_data.html's AniList dialog): a public username, or OAuth for a private profile. */
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

	let priv = $state(false);
	let user = $state('');
	const standardOff = $derived(standardImportsDisabled(mode));

	async function importPublic(event: SubmitEvent) {
		event.preventDefault();
		if (busy) return;
		const answer = await run(() => postForm(data.urls.anilist_public, { ...sharedFields({ frequency, time, mode }), user: user.trim() }));
		if (answer?.saved) user = '';
	}
</script>

<label class="ct-settings-check">
	<input type="checkbox" bind:checked={priv} />
	<span>Import private profile (requires authentication)</span>
</label>
{#if priv}
	<OAuthForm action={data.urls.anilist_oauth} button="Connect with AniList & Import" disabled={standardOff} {frequency} {time} {mode} />
{:else}
	<form onsubmit={importPublic}>
		<label class="ct-settings-field">
			Public AniList username
			<input type="text" name="user" autocomplete="off" spellcheck="false" placeholder="Public AniList username" bind:value={user} />
		</label>
		<div class="ct-settings-actions">
			<button type="submit" class="ct-settings-button is-primary" disabled={busy || standardOff || !user.trim()}>Import</button>
		</div>
	</form>
{/if}
