<script lang="ts">
	import './lists.css';
	import { csrfToken, djangoWrite } from '#lib/csrf.ts';
	import Dialog from '#lib/ui/Dialog.svelte';
	import { im, lf, ls } from './strings.ts';
	import { readDevicePoll, type ListsScreen } from './types.ts';

	/**
	 * The Lists page's import dialogs: CSV, MDBList and Trakt, on the list
	 * imports API (the same endpoints the CineTrack app uses). Trakt connects
	 * with the device code flow. Secrets are posted, never read back.
	 */
	let {
		kind = $bindable(null),
		screen
	}: { kind?: 'csv' | 'mdblist' | 'trakt' | null; screen: ListsScreen } = $props();

	interface Status {
		trakt: { has_credentials: boolean; authorization_pending: boolean };
		mdblist: { connected: boolean; sync_frequency: string | null; connection_broken: boolean; last_error_message: string };
	}

	let open = $derived(kind !== null);
	let status = $state<Status | null>(null);
	let busy = $state(false);
	let message = $state('');
	let failed = $state('');
	let file = $state<File | null>(null);
	let apiKey = $state('');
	let frequency = $state('24h');
	let reference = $state('');
	let clientId = $state('');
	let clientSecret = $state('');
	let traktStep = $state<'setup' | 'credentials' | 'login' | 'device'>('setup');
	let device = $state<{ user_code: string; verification_url: string } | null>(null);
	let copied = $state(false);
	let pollGeneration = 0;

	async function loadStatus() {
		const response = await fetch('/api/v1/lists/imports/', { credentials: 'same-origin' });
		if (response.ok) status = await response.json();
	}

	$effect(() => {
		if (!kind) {
			pollGeneration++;
			return;
		}
		message = '';
		failed = '';
		device = null;
		apiKey = '';
		clientId = '';
		clientSecret = '';
		if (kind !== 'csv') {
			loadStatus().then(() => {
				if (kind === 'trakt') traktStep = status?.trakt.has_credentials ? 'login' : 'setup';
			});
		}
	});

	async function run(task: () => Promise<Response>, done: string) {
		busy = true;
		failed = '';
		message = '';
		try {
			const response = await task();
			if (!response.ok) {
				const body = await response.json().catch(() => ({}));
				throw new Error(body.detail || ls.failed);
			}
			message = done;
			await loadStatus();
		} catch (error) {
			failed = error instanceof Error ? error.message : ls.failed;
		}
		busy = false;
	}

	async function uploadCsv() {
		if (!file) return;
		const body = new FormData();
		body.append('file', file);
		await run(
			async () =>
				fetch('/api/v1/lists/import/', {
					method: 'POST',
					credentials: 'same-origin',
					headers: { 'x-csrftoken': await csrfToken() },
					body
				}),
			im.csvQueued
		);
	}

	async function startDevice() {
		busy = true;
		failed = '';
		try {
			const response = await djangoWrite('/api/v1/lists/imports/trakt/device/', 'POST');
			const body = await response.json().catch(() => ({}));
			if (!response.ok) throw new Error(body.detail || ls.failed);
			device = { user_code: body.user_code, verification_url: body.verification_url };
			traktStep = 'device';
			poll(Number(body.interval) || 5, ++pollGeneration);
		} catch (error) {
			failed = error instanceof Error ? error.message : ls.failed;
		}
		busy = false;
	}

	async function poll(interval: number, generation: number) {
		await new Promise((resolve) => setTimeout(resolve, interval * 1000));
		if (generation !== pollGeneration) return;
		try {
			const response = await djangoWrite('/api/v1/lists/imports/trakt/device/poll/', 'POST');
			const state = readDevicePoll(response.status, await response.json().catch(() => ({})));
			if (generation !== pollGeneration) return;
			if (state.kind === 'pending') poll(state.interval, generation);
			else if (state.kind === 'importing') message = im.importing;
			else if (state.kind === 'expired') failed = im.expired;
			else failed = state.message;
		} catch {
			failed = ls.failed;
		}
	}

	async function copyUri() {
		await navigator.clipboard?.writeText(screen.trakt_redirect_uri).catch(() => {});
		copied = true;
		setTimeout(() => (copied = false), 1500);
	}

	const title = $derived(kind === 'csv' ? im.csvTitle : kind === 'mdblist' ? im.mdbTitle : im.traktTitle);
</script>

<Dialog
	bind:open={() => open, (value) => {
		if (!value) kind = null;
	}}
	{title}
	sheet
>
	<div class="ct-import">
		{#if kind === 'csv'}
			<form
				onsubmit={(event) => {
					event.preventDefault();
					uploadCsv();
				}}
			>
				<label>
					<span>{im.csvFile}</span>
					<input type="file" accept=".csv,text/csv" required onchange={(event) => (file = event.currentTarget.files?.[0] ?? null)} />
				</label>
				<div class="ct-list-form__actions">
					<button type="submit" class="ct-lists-button is-primary" disabled={busy || !file}>{im.import}</button>
				</div>
			</form>
		{:else if kind === 'mdblist' && status}
			{#if !status.mdblist.connected}
				<form
					onsubmit={(event) => {
						event.preventDefault();
						run(() => djangoWrite('/api/v1/lists/imports/mdblist/', 'PUT', { api_key: apiKey, sync_frequency: frequency }), im.queued);
					}}
				>
					<label><span>{im.apiKey}</span><input type="password" bind:value={apiKey} required autocomplete="off" /></label>
					<label>
						<span>{im.syncFrequency}</span>
						<select bind:value={frequency}>
							{#each Object.entries(im.frequencies) as [value, label] (value)}<option {value}>{label}</option>{/each}
						</select>
					</label>
					<div class="ct-list-form__actions">
						<button type="submit" class="ct-lists-button is-primary" disabled={busy}>{im.connect}</button>
					</div>
				</form>
			{:else}
				{#if status.mdblist.connection_broken}
					<p class="ct-list-form__error">{im.problem} {status.mdblist.last_error_message}</p>
				{/if}
				<form
					onsubmit={(event) => {
						event.preventDefault();
						run(() => djangoWrite('/api/v1/lists/imports/mdblist/import/', 'POST', { list_reference: reference }), im.queued);
					}}
				>
					<label><span>{im.importByRef}</span><input bind:value={reference} required placeholder={im.listReference} /></label>
					<div class="ct-list-form__actions">
						<button type="submit" class="ct-lists-button is-primary" disabled={busy}>{im.import}</button>
					</div>
				</form>
				<div class="ct-list-form__actions">
					<button type="button" class="ct-lists-button" disabled={busy} onclick={() => run(() => djangoWrite('/api/v1/lists/imports/mdblist/sync/', 'POST'), im.queued)}>
						{im.syncNow}
					</button>
					<button type="button" class="ct-lists-button is-danger" disabled={busy} onclick={() => run(() => djangoWrite('/api/v1/lists/imports/mdblist/', 'DELETE'), '')}>
						{im.disconnect}
					</button>
				</div>
			{/if}
		{:else if kind === 'trakt' && status}
			{#if traktStep === 'setup'}
				<h3>{im.traktSetup}</h3>
				<p>{im.traktSetupBody}</p>
				<p class="ct-import__label">{im.redirectUri}</p>
				<div class="ct-import__copy">
					<code>{screen.trakt_redirect_uri}</code>
					<button type="button" class="ct-lists-button" onclick={copyUri}>{copied ? im.copied : im.copy}</button>
				</div>
				<div class="ct-list-form__actions">
					<a class="ct-lists-link" href="https://trakt.tv/oauth/applications/new" target="_blank" rel="noopener noreferrer">{im.createApp}</a>
					<button type="button" class="ct-lists-button is-primary" onclick={() => (traktStep = 'credentials')}>{im.next}</button>
				</div>
			{:else if traktStep === 'credentials'}
				<form
					onsubmit={async (event) => {
						event.preventDefault();
						await run(() => djangoWrite('/api/v1/lists/imports/trakt/credentials/', 'PUT', { client_id: clientId, client_secret: clientSecret }), '');
						if (!failed) traktStep = 'login';
					}}
				>
					<label><span>{im.clientId}</span><input bind:value={clientId} required autocomplete="off" /></label>
					<label><span>{im.clientSecret}</span><input type="password" bind:value={clientSecret} required autocomplete="off" /></label>
					<div class="ct-list-form__actions">
						<button type="button" class="ct-lists-button" onclick={() => (traktStep = 'setup')}>{im.back}</button>
						<button type="submit" class="ct-lists-button is-primary" disabled={busy}>{im.saveCredentials}</button>
					</div>
				</form>
			{:else if traktStep === 'login'}
				<div class="ct-list-form__actions is-start">
					<button type="button" class="ct-lists-button is-primary" disabled={busy} onclick={startDevice}>{im.login}</button>
					<button type="button" class="ct-lists-button" onclick={() => (traktStep = 'credentials')}>{im.updateCredentials}</button>
				</div>
			{:else if device}
				<p>{im.deviceStep(device.verification_url)}</p>
				<p class="ct-import__code">{device.user_code}</p>
				<a class="ct-lists-link" href={device.verification_url} target="_blank" rel="noopener noreferrer">{device.verification_url}</a>
				{#if !message && !failed}<p class="ct-list-form__note">{im.waiting}</p>{/if}
			{/if}
		{:else if kind}
			<p class="ct-list-form__note">{lf.loading}</p>
		{/if}
		{#if message}<p class="ct-import__done" role="status">{message}</p>{/if}
		{#if failed}<p class="ct-list-form__error" role="alert">{failed}</p>{/if}
	</div>
</Dialog>
