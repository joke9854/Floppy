<script lang="ts">
	import { invalidate } from '$app/navigation';
	import { onMount } from 'svelte';
	import { postForm } from '../integrations/actions.ts';
	import { type SavedAnswer, type SettingsImport, when } from '../types.ts';
	import { getJson } from './plex.ts';

	/** Storyteller (import_data.html's dialog): connect, approve on the server (polled), then Sync now / Disconnect. */
	let {
		data,
		busy,
		run,
		onsaved
	}: {
		data: SettingsImport;
		busy: boolean;
		run: (send: () => Promise<SavedAnswer>) => Promise<SavedAnswer | null>;
		onsaved: () => void;
	} = $props();

	const acct = $derived(data.accounts.storyteller);
	const connected = $derived(!!acct?.connected);
	const pending = $derived(data.storyteller_pending);
	const urls = $derived(data.urls);

	let serverUrl = $state('');
	let pollStatus = $state('Waiting for approval…');

	async function refresh() {
		try {
			await invalidate('floppy:settings');
		} catch {
			// The next load refreshes the page.
		}
		onsaved();
	}

	onMount(() => {
		if (connected || !pending) return;
		let stopped = false;
		let inFlight = false;
		const timer = setInterval(
			async () => {
				if (stopped || inFlight || document.hidden) return;
				inFlight = true;
				try {
					const { body } = await getJson<{ status?: string; message?: string }>(urls.storyteller_poll);
					if (stopped) return;
					if (body.status === 'connected') {
						stopped = true;
						clearInterval(timer);
						pollStatus = 'Connected! Reloading…';
						await refresh();
					} else if (body.status === 'expired') {
						stopped = true;
						clearInterval(timer);
						pollStatus = 'Login timed out. Please try again.';
						await refresh();
					} else if (body.status === 'error') {
						stopped = true;
						clearInterval(timer);
						pollStatus = body.message || 'Login failed.';
					} else if (body.status === 'idle') {
						stopped = true;
						clearInterval(timer);
						await refresh();
					}
				} catch {
					// Keep polling.
				} finally {
					inFlight = false;
				}
			},
			Math.max(1, pending.interval || 5) * 1000
		);
		return () => {
			stopped = true;
			clearInterval(timer);
		};
	});

	async function connect(event: SubmitEvent) {
		event.preventDefault();
		if (busy || !serverUrl.trim()) return;
		const answer = await run(() => postForm(urls.storyteller_connect, { server_url: serverUrl.trim() }));
		if (answer?.saved) serverUrl = '';
	}

	const action = (url: string) => {
		if (!busy) void run(() => postForm(url));
	};
</script>

<p>
	<span class={['ct-settings-badge', connected && 'is-on']}>{connected ? 'Connected' : 'Disconnected'}</span>
</p>

{#if connected && acct}
	<p class="ct-settings-note">Sync your books from Storyteller every 2 hours.</p>
	{#if acct.name}<p class="ct-settings-note">Server: {acct.name}</p>{/if}
	{#if acct.last_sync}<p class="ct-settings-note">Last sync: {when(acct.last_sync)}</p>{/if}
	{#if acct.error}<p class="ct-settings-status is-error"><strong>Error:</strong> {acct.error}</p>{/if}
	<div class="ct-settings-actions">
		<button type="button" class="ct-settings-button is-primary" disabled={busy} onclick={() => action(urls.storyteller_sync)}>Sync now</button>
		<button type="button" class="ct-settings-button is-danger" disabled={busy} onclick={() => action(urls.storyteller_disconnect)}>Disconnect</button>
	</div>
{:else if pending}
	<p class="ct-settings-note">Approve this login on your Storyteller server to finish connecting.</p>
	{#if acct?.error}<p class="ct-settings-status is-error"><strong>Error:</strong> {acct.error}</p>{/if}
	<div class="ct-import-info">
		{#if pending.user_code}
			<p>Enter this code</p>
			<p class="ct-import-code">{pending.user_code}</p>
		{/if}
		{#if pending.verification_uri}
			<a class="ct-settings-button is-primary" href={pending.verification_uri} target="_blank" rel="noopener noreferrer">Open approval page</a>
		{/if}
		<p class="ct-settings-note" role="status">{pollStatus}</p>
	</div>
	<div class="ct-settings-actions">
		<button type="button" class="ct-settings-button" disabled={busy} onclick={() => action(urls.storyteller_cancel)}>Cancel</button>
	</div>
{:else}
	<p class="ct-settings-note">Track the books you're currently reading from Storyteller.</p>
	{#if acct?.error}<p class="ct-settings-status is-error"><strong>Error:</strong> {acct.error}</p>{/if}
	<form onsubmit={connect}>
		<label class="ct-settings-field">
			Server URL
			<input type="url" name="server_url" required spellcheck="false" placeholder="https://storyteller.example.com" bind:value={serverUrl} />
		</label>
		<div class="ct-settings-actions">
			<button type="submit" class="ct-settings-button is-primary" disabled={busy || !serverUrl.trim()}>Connect Storyteller</button>
		</div>
		{#if busy}<p class="ct-settings-note" role="status">Checking with the server…</p>{/if}
	</form>
{/if}
