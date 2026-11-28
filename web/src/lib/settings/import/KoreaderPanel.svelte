<script lang="ts">
	import { postForm } from '../integrations/actions.ts';
	import { type SavedAnswer, type SettingsImport, when } from '../types.ts';
	import { sharedFields, standardImportsDisabled } from './sources.ts';

	/** KOReader (import_data.html's dialog): connect a sync server, then settings, Sync now and Disconnect. */
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

	const acct = $derived(data.accounts.koreader);
	const koreader = $derived(data.koreader);
	const urls = $derived(data.urls);
	const shared = $derived(sharedFields({ frequency, time, mode }));
	const off = $derived(standardImportsDisabled(mode));
	const connected = $derived(!!acct?.connected && !!koreader);

	// Connect form.
	let serverUrl = $state('');
	let username = $state('');
	let password = $state('');
	let verifySsl = $state(true);
	let createMissing = $state(false);
	let skipFinished = $state(true);
	let threshold = $state('100');
	const blank = $derived(!serverUrl.trim() || !username.trim() || !password || !threshold.trim());

	// Settings form: starts from the saved values until edited.
	let edit = $state<{ server_url?: string; username?: string; password: string; verify_ssl?: boolean; create_missing?: boolean; skip?: boolean; threshold?: string }>({ password: '' });
	const settingsBlank = $derived(!(edit.server_url ?? koreader?.server_url ?? '').trim() || !(edit.username ?? koreader?.username ?? '').trim());

	const flags = (verify: boolean, create: boolean, skip: boolean): Record<string, string> => {
		const fields: Record<string, string> = {};
		if (verify) fields.verify_ssl = 'on';
		if (create) fields.create_missing = 'on';
		if (skip) fields.skip_finished_books = 'on';
		return fields;
	};

	async function connect(event: SubmitEvent) {
		event.preventDefault();
		if (busy || off || blank) return;
		const answer = await run(() =>
			postForm(urls.koreader_connect, {
				...shared,
				server_url: serverUrl.trim(),
				username: username.trim(),
				// A password goes as typed; a space can be part of one.
				password,
				finished_threshold_percent: threshold.trim(),
				...flags(verifySsl, createMissing, skipFinished)
			})
		);
		if (answer?.saved) {
			serverUrl = '';
			username = '';
			password = '';
			verifySsl = true;
			createMissing = false;
			skipFinished = true;
			threshold = '100';
		}
	}

	async function save(event: SubmitEvent) {
		event.preventDefault();
		if (busy || settingsBlank || !koreader) return;
		const answer = await run(() =>
			postForm(urls.koreader_settings, {
				server_url: (edit.server_url ?? koreader.server_url).trim(),
				username: (edit.username ?? koreader.username).trim(),
				password: edit.password,
				finished_threshold_percent: (edit.threshold ?? String(koreader.finished_threshold_percent)).trim(),
				...flags(edit.verify_ssl ?? koreader.verify_ssl, edit.create_missing ?? koreader.create_missing, edit.skip ?? koreader.skip_finished_books)
			})
		);
		if (answer?.saved) edit = { password: '' };
	}

	const action = (url: string, fields: Record<string, string> = {}) => {
		if (!busy) void run(() => postForm(url, fields));
	};
</script>

<p>
	<span class={['ct-settings-badge', connected && 'is-on']}>{connected ? 'Connected' : 'Disconnected'}</span>
</p>

{#snippet thresholdHelp()}
	<small class="ct-settings-note">Synced progress at or above this percentage is marked completed.</small>
{/snippet}

{#if connected && koreader}
	<p class="ct-settings-note">
		Sync reading progress using your import schedule above.
		{#if koreader.link_count}
			{koreader.link_count === 1 ? '1 linked document.' : `${koreader.link_count} linked documents.`}
		{:else}
			Link document IDs on each book's track modal to sync from official servers.
		{/if}
	</p>
	<p class="ct-settings-note">Server: {koreader.server_url}</p>
	{#if acct?.last_sync}<p class="ct-settings-note">Last sync: {when(acct.last_sync)}</p>{/if}
	{#if acct?.error}<p class="ct-settings-status is-error"><strong>Error:</strong> {acct.error}</p>{/if}

	<form onsubmit={save}>
		<p><strong>Settings</strong></p>
		<label class="ct-settings-field">
			Server URL
			<input type="url" name="server_url" required spellcheck="false" value={edit.server_url ?? koreader.server_url} oninput={(event) => (edit.server_url = event.currentTarget.value)} />
		</label>
		<label class="ct-settings-field">
			Username
			<input type="text" name="username" required autocomplete="username" value={edit.username ?? koreader.username} oninput={(event) => (edit.username = event.currentTarget.value)} />
		</label>
		<label class="ct-settings-field">
			Password
			<input type="password" name="password" autocomplete="current-password" placeholder="Leave blank to keep current password" bind:value={edit.password} />
		</label>
		<label class="ct-import-check-row">
			<input type="checkbox" checked={edit.verify_ssl ?? koreader.verify_ssl} onchange={(event) => (edit.verify_ssl = event.currentTarget.checked)} />
			Verify TLS certificate
		</label>
		<label class="ct-import-check-row">
			<input type="checkbox" checked={edit.create_missing ?? koreader.create_missing} onchange={(event) => (edit.create_missing = event.currentTarget.checked)} />
			Add matched books that are not already in my library
		</label>
		<label class="ct-import-check-row">
			<input type="checkbox" checked={edit.skip ?? koreader.skip_finished_books} onchange={(event) => (edit.skip = event.currentTarget.checked)} />
			Skip books already marked completed (fewer server requests)
		</label>
		<label class="ct-settings-field">
			Mark completed at (%)
			<input
				type="number"
				name="finished_threshold_percent"
				min="1"
				max="100"
				step="1"
				required
				value={edit.threshold ?? String(koreader.finished_threshold_percent)}
				oninput={(event) => (edit.threshold = event.currentTarget.value)}
			/>
			{@render thresholdHelp()}
		</label>
		<div class="ct-settings-actions">
			<button type="submit" class="ct-settings-button is-primary" disabled={busy || settingsBlank}>Save settings</button>
		</div>
	</form>
	<div class="ct-settings-actions">
		<button type="button" class="ct-settings-button is-primary" disabled={busy || off} onclick={() => action(urls.koreader_sync, shared)}>Sync now</button>
		<button type="button" class="ct-settings-button is-danger" disabled={busy} onclick={() => action(urls.koreader_disconnect)}>Disconnect</button>
	</div>
{:else}
	<p class="ct-settings-note">
		Connect your self-hosted KOReader sync server. Enable <strong>Send document metadata</strong> in KOReader for automatic matching on supported servers.
	</p>
	{#if acct?.error}<p class="ct-settings-status is-error"><strong>Error:</strong> {acct.error}</p>{/if}
	<form onsubmit={connect}>
		<label class="ct-settings-field">
			Server URL
			<input type="url" name="server_url" required spellcheck="false" placeholder="https://kosync.example.com:7200" bind:value={serverUrl} />
		</label>
		<label class="ct-settings-field">
			Username
			<input type="text" name="username" required autocomplete="username" bind:value={username} />
		</label>
		<label class="ct-settings-field">
			Password
			<input type="password" name="password" required autocomplete="current-password" bind:value={password} />
		</label>
		<label class="ct-import-check-row"><input type="checkbox" bind:checked={verifySsl} /> Verify TLS certificate</label>
		<label class="ct-import-check-row"><input type="checkbox" bind:checked={createMissing} /> Add matched books that are not already in my library</label>
		<label class="ct-import-check-row"><input type="checkbox" bind:checked={skipFinished} /> Skip books already marked completed (fewer server requests)</label>
		<label class="ct-settings-field">
			Mark completed at (%)
			<input type="number" name="finished_threshold_percent" min="1" max="100" step="1" required bind:value={threshold} />
			{@render thresholdHelp()}
		</label>
		<div class="ct-settings-actions">
			<button type="submit" class="ct-settings-button is-primary" disabled={busy || off || blank}>Connect &amp; Import</button>
		</div>
		{#if busy}<p class="ct-settings-note" role="status">Checking with the server…</p>{/if}
	</form>
{/if}
