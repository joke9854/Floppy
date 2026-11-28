<script lang="ts">
	import { postForm } from '../integrations/actions.ts';
	import { type SavedAnswer, type SettingsImport, when } from '../types.ts';

	/** Radarr and Sonarr (import_data.html's dialogs): one row per instance, and a form to add another. */
	let {
		sourceKey,
		data,
		busy,
		run
	}: {
		sourceKey: 'radarr' | 'sonarr';
		data: SettingsImport;
		busy: boolean;
		run: (send: () => Promise<SavedAnswer>) => Promise<SavedAnswer | null>;
	} = $props();

	const name = $derived(sourceKey === 'radarr' ? 'Radarr' : 'Sonarr');
	const list = $derived(data[sourceKey]);
	const urls = $derived(data.urls as unknown as Record<string, string>);
	const placeholder = $derived(sourceKey === 'radarr' ? 'https://radarr.local:7878' : 'https://sonarr.local:8989');

	let label = $state('');
	let baseUrl = $state('');
	let apiKey = $state('');
	const blank = $derived(!baseUrl.trim() || !apiKey.trim());

	async function connect(event: SubmitEvent) {
		event.preventDefault();
		if (busy || blank) return;
		const answer = await run(() => postForm(urls[`${sourceKey}_connect`], { name: label.trim(), base_url: baseUrl.trim(), api_key: apiKey.trim() }));
		if (answer?.saved) {
			label = '';
			baseUrl = '';
			apiKey = '';
		}
	}

	const act = (action: 'sync' | 'disconnect', id: number) => {
		if (busy) return;
		void run(() => postForm(urls[`${sourceKey}_${action}`], { instance_id: String(id) }));
	};
</script>

{#each list as instance (instance.id)}
	<div class="ct-import-instance">
		<p>
			<strong>{instance.name}</strong>
			<span class={['ct-settings-badge', instance.connected && 'is-on']}>{instance.connected ? 'Connected' : 'Disconnected'}</span>
		</p>
		<p class="ct-settings-note">{instance.base_url}</p>
		{#if instance.last_sync}<p class="ct-settings-note">Last sync: {when(instance.last_sync)}</p>{/if}
		{#if instance.error}<p class="ct-settings-status is-error">{instance.error}</p>{/if}
		<div class="ct-settings-actions">
			<button type="button" class="ct-settings-button" disabled={busy} aria-label={`Sync ${instance.name} now`} onclick={() => act('sync', instance.id)}>Sync Now</button>
			<button type="button" class="ct-settings-button is-danger" disabled={busy} aria-label={`Disconnect ${instance.name}`} onclick={() => act('disconnect', instance.id)}
				>Disconnect</button
			>
		</div>
	</div>
{/each}

<p class="ct-settings-note">{list.length ? `Connect another ${name} instance.` : `Connect ${name} using your server URL and API key.`}</p>
<form onsubmit={connect}>
	<label class="ct-settings-field">
		Label
		<input type="text" name="name" autocomplete="off" placeholder="Label (optional, e.g. '4K')" bind:value={label} />
	</label>
	<label class="ct-settings-field">
		Server URL
		<input type="url" name="base_url" required spellcheck="false" {placeholder} bind:value={baseUrl} />
	</label>
	<label class="ct-settings-field">
		API key
		<input type="password" name="api_key" required autocomplete="off" placeholder={`${name} API key`} bind:value={apiKey} />
	</label>
	<div class="ct-settings-actions">
		<button type="submit" class="ct-settings-button is-primary" disabled={busy || blank}>{list.length ? 'Add Instance' : `Connect ${name}`}</button>
	</div>
	{#if busy}<p class="ct-settings-note" role="status">Checking with the server…</p>{/if}
</form>
