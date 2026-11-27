<script lang="ts">
	import { invalidate } from '$app/navigation';
	import { st } from '../strings.ts';
	import { when, type SettingsIntegrations } from '../types.ts';
	import { postFile, postForm } from './actions.ts';
	import CopyField from './CopyField.svelte';

	/** Jellyfin: the official and unofficial webhook setups and the Floppy to Jellyfin connection. */
	let { integrations }: { integrations: SettingsIntegrations } = $props();
	const jellyfin = $derived(integrations.jellyfin);
	const account = $derived(jellyfin.account);

	const template = `{
  "Event": "{{#if_equals NotificationType 'PlaybackStart'}}Play{{/if_equals}}{{#if_equals NotificationType 'PlaybackStop'}}Stop{{/if_equals}}{{#if_equals NotificationType 'PlaybackProgress'}}{{#if IsPaused}}Pause{{else}}Play{{/if}}{{/if_equals}}{{#if_equals NotificationType 'UserDataSaved'}}UserDataSaved{{/if_equals}}{{#if_equals NotificationType 'ItemAdded'}}ItemAdded{{/if_equals}}{{#if_equals NotificationType 'ItemDeleted'}}ItemDeleted{{/if_equals}}",
  "PlaybackPositionTicks": "{{PlaybackPositionTicks}}",
  "Item": {
    "Id": "{{ItemId}}",
    "Type": "{{ItemType}}",
    "Name": "{{Name}}",
    "ProductionYear": "{{Year}}",
    "ProviderIds": {
      "Tmdb": "{{Provider_tmdb}}",
      "Imdb": "{{Provider_imdb}}",
      "Tvdb": "{{Provider_tvdb}}"
    },
    "UserData": {
      "Played": {{#if_equals PlayedToCompletion 'True'}}true{{else}}false{{/if_equals}},
      "LastPlayedDate": "{{LastPlayedDate}}"{{#if_equals NotificationType 'UserDataSaved'}}{{#if Rating}},
      "Rating": {{Rating}}{{/if}}{{/if_equals}}
    }{{#if_equals ItemType 'Episode'}},
    "SeriesName": "{{SeriesName}}",
    "ParentIndexNumber": {{SeasonNumber}},
    "IndexNumber": {{EpisodeNumber}}
    {{/if_equals}}
  }
}`;
	const repoUrl = 'https://raw.githubusercontent.com/shemanaev/jellyfin-plugin-repo/master/manifest.json';

	const local = {
		officialTitle: 'Jellyfin Integration (Official Repo)',
		officialNote:
			'Connect Jellyfin to automatically track your watching progress. Use this method if your server has access to the official Jellyfin plugin repository.',
		unofficialTitle: 'Jellyfin Integration (Unofficial Repo)',
		unofficialNote:
			'An alternative setup using an unofficial webhook plugin from a community repository. Use this method if the official Jellyfin plugin repository is not accessible from your server.',
		setup: 'Setup Instructions',
		webhookUrl: 'Jellyfin webhook URL',
		template: 'Jellyfin JSON template',
		events: 'Webhook Events',
		eventsNote: 'Play and Stop events are always processed. Enable these to sync manual watched changes from the unofficial Webhooks plugin.',
		played: 'Process MarkPlayed events',
		playedHelp: 'Mark media as watched when it is manually marked played in Jellyfin.',
		unplayed: 'Process MarkUnplayed events',
		unplayedHelp: 'Remove watched progress when it is manually marked unplayed in Jellyfin. This event can delete media from Floppy.',
		saveChanges: 'Save Changes',
		title: 'Floppy → Jellyfin',
		connected: 'Connected',
		disconnected: 'Disconnected',
		note: 'Push your Floppy watched status onto a Jellyfin server, e.g. after re-adding media or setting up a fresh Jellyfin instance.',
		lastSync: 'Last sync:',
		error: 'Error:',
		pullTitle: 'Jellyfin → Floppy: auto-import history',
		pullNote:
			"No manual export needed. Floppy pulls your watch history straight from your Jellyfin server: full per-play history via the Playback Reporting plugin's API when it's reachable with an admin key, otherwise a one-event-per-item backfill from Jellyfin's current watched state.",
		prOn: "Using Playback Reporting's API (full per-play history).",
		prOff: "Playback Reporting's API isn't reachable with this key — using the current-watched-state backfill instead (one event per item).",
		prNone: 'Not yet run.',
		lastRun: 'Last run:',
		importNow: 'Import history now',
		manual: 'Or upload a Playback Reporting TSV manually',
		manualNote:
			"Only needed if your key can't reach the Playback Reporting API (e.g. a non-admin key) and you'd rather not use the current-watched-state backfill above.",
		importFile: 'Playback Reporting TSV file',
		importUpload: 'Import / reimport history',
		pushWatched: 'Push watched status to Jellyfin',
		pushUnwatched: 'Push unwatched status to Jellyfin',
		scheduled: 'Sync on a schedule (hourly)',
		instant: 'Instant push after playback events',
		saveSettings: 'Save Settings',
		syncNow: 'Sync Now',
		edit: 'Edit connection',
		disconnect: 'Disconnect',
		sure: 'Disconnect Jellyfin? Floppy stops syncing with it.',
		cancel: 'Cancel',
		editNote:
			"Update the server URL, API key, or user. If the key doesn't resolve a user automatically, also provide the exact Jellyfin username.",
		update: 'Update Jellyfin connection',
		connectNote:
			"Connect Jellyfin using your server URL and API key. If the key doesn't resolve a user automatically, also provide the exact Jellyfin username.",
		connect: 'Connect Jellyfin',
		serverUrl: 'Server URL',
		apiKeyUpdate: 'Jellyfin API key (re-enter to update)',
		apiKey: 'Jellyfin API key',
		usernamePh: 'Jellyfin username (only needed for server-admin keys)',
		username: 'Jellyfin username'
	};

	let busy = $state('');
	let notice = $state<{ key: string; text: string; failed: boolean } | null>(null);
	// svelte-ignore state_referenced_locally
	let markPlayed = $state(integrations.jellyfin.mark_played_enabled);
	// svelte-ignore state_referenced_locally
	let markUnplayed = $state(integrations.jellyfin.mark_unplayed_enabled);
	// svelte-ignore state_referenced_locally
	let pullOn = $state(integrations.jellyfin.account?.pull_history_enabled ?? false);
	// svelte-ignore state_referenced_locally
	let pushPlayed = $state(integrations.jellyfin.account?.push_watched_enabled ?? false);
	// svelte-ignore state_referenced_locally
	let pushUnplayed = $state(integrations.jellyfin.account?.push_unwatched_enabled ?? false);
	// svelte-ignore state_referenced_locally
	let scheduled = $state(integrations.jellyfin.account?.scheduled_push_enabled ?? false);
	// svelte-ignore state_referenced_locally
	let instant = $state(integrations.jellyfin.account?.instant_push_enabled ?? false);
	let editing = $state(false);
	let confirming = $state(false);
	// svelte-ignore state_referenced_locally
	let baseUrl = $state(integrations.jellyfin.account?.base_url ?? '');
	let apiKey = $state('');
	// svelte-ignore state_referenced_locally
	let username = $state(integrations.jellyfin.account?.username ?? '');
	let file = $state<File | null>(null);

	async function run(key: string, send: () => ReturnType<typeof postForm>, after?: () => void) {
		busy = key;
		notice = null;
		try {
			const answer = await send();
			notice = { key, text: answer.saved ? answer.message || st.saved : (answer.message ?? st.failed), failed: !answer.saved };
			if (answer.saved) {
				after?.();
				await invalidate('floppy:settings');
			}
		} catch {
			notice = { key, text: st.failed, failed: true };
		} finally {
			busy = '';
		}
	}

	const post = (key: string, url: string, fields: Record<string, string | string[]> = {}, after?: () => void) =>
		run(key, () => postForm(url, fields), after);

	function saveEvents(event: SubmitEvent) {
		event.preventDefault();
		return post('events', jellyfin.urls.events, {
			...(markPlayed ? { jellyfin_mark_played_enabled: 'on' } : {}),
			...(markUnplayed ? { jellyfin_mark_unplayed_enabled: 'on' } : {})
		});
	}

	function saveSettings(event: SubmitEvent) {
		event.preventDefault();
		const fields: Record<string, string> = {};
		if (pullOn) fields.pull_history_enabled = 'on';
		if (pushPlayed) fields.push_watched_enabled = 'on';
		if (pushUnplayed) fields.push_unwatched_enabled = 'on';
		if (scheduled) fields.scheduled_push_enabled = 'on';
		if (instant) fields.instant_push_enabled = 'on';
		return post('settings', jellyfin.urls.settings, fields);
	}

	function connect(event: SubmitEvent) {
		event.preventDefault();
		return post('connect', jellyfin.urls.connect, { base_url: baseUrl.trim(), api_key: apiKey, username: username.trim() }, () => {
			apiKey = '';
			editing = false;
		});
	}

	function upload(event: SubmitEvent) {
		event.preventDefault();
		const chosen = file;
		if (!chosen) return;
		return run('upload', () => postFile(jellyfin.urls.upload, 'playback_reporting_file', chosen), () => (file = null));
	}

	function disconnect() {
		confirming = false;
		return post('disconnect', jellyfin.urls.disconnect);
	}
</script>

{#snippet status(key: string)}
	{#if notice?.key === key}<span class={['ct-settings-status', notice.failed && 'is-error']} role="status">{notice.text}</span>{/if}
{/snippet}

<section class="ct-settings-section">
	<div>
		<h2>{local.officialTitle}</h2>
		<p class="ct-settings-note">{local.officialNote}</p>
	</div>
	<h3>{local.setup}</h3>
	<ol class="ct-settings-steps">
		<li>You will need to have TMDB and TVDB as metadata providers in Jellyfin.</li>
		<li>Install the Webhook plugin from the Jellyfin Stable repo via your server's Plugin Catalog.</li>
		<li>Restart your server, then open the Webhook plugin and click <strong>Add Generic Destination</strong>.</li>
		<li>
			Configure the webhook with the following settings:
			<ul>
				<li>Name: <strong>Floppy</strong></li>
				<li>
					Notification Type: <strong>Playback Start</strong>, <strong>Playback Stop</strong>, <strong>Playback Progress</strong>,
					<strong>User Data Saved</strong>, <strong>Item Added</strong>, and <strong>Item Deleted</strong>
				</li>
				<li>User Filter: your Jellyfin user</li>
			</ul>
		</li>
		<li>
			Set the webhook URL to:
			<CopyField value={jellyfin.webhook_url} label={local.webhookUrl} />
		</li>
		<li>
			Under the <strong>Template</strong> section, paste the following JSON:
			<CopyField value={template} label={local.template} multiline rows={14} />
		</li>
	</ol>
</section>

<section class="ct-settings-section">
	<div>
		<h2>{local.unofficialTitle}</h2>
		<p class="ct-settings-note">{local.unofficialNote}</p>
	</div>
	<h3>{local.setup}</h3>
	<ol class="ct-settings-steps">
		<li>You will need to have TMDB and TVDB as metadata providers in Jellyfin.</li>
		<li>
			In Jellyfin, go to <strong>Dashboard &gt; Plugins &gt; Repositories</strong> and add the following repository URL:
			<a href={repoUrl} target="_blank" rel="noopener noreferrer">{repoUrl}<span class="sr-only"> {st.newTab}</span></a>
		</li>
		<li>
			From the Plugin Catalog, install the
			<a href="https://github.com/shemanaev/jellyfin-plugin-webhooks" target="_blank" rel="noopener noreferrer"
				>Unofficial Webhooks plugin<span class="sr-only"> {st.newTab}</span></a
			>.
		</li>
		<li>
			Restart your server, then open the Unofficial Webhooks plugin and configure it:
			<ul>
				<li>Payload format: <strong>Default</strong></li>
				<li>Listen to events only for: your Jellyfin user</li>
				<li>
					Events: <strong>Play</strong>, <strong>Stop</strong>, <strong>MarkPlayed</strong>, <strong>MarkUnplayed</strong>,
					<strong>ItemAdded</strong>, and <strong>ItemDeleted</strong>
				</li>
			</ul>
		</li>
		<li>
			Set the webhook URL to:
			<CopyField value={jellyfin.webhook_url} label={local.webhookUrl} />
		</li>
	</ol>
	<h3>{local.events}</h3>
	<p class="ct-settings-note">{local.eventsNote}</p>
	<form onsubmit={saveEvents}>
		<label class="ct-settings-check">
			<input type="checkbox" bind:checked={markPlayed} />
			<span>{local.played}<small>{local.playedHelp}</small></span>
		</label>
		<label class="ct-settings-check">
			<input type="checkbox" bind:checked={markUnplayed} />
			<span>{local.unplayed}<small>{local.unplayedHelp}</small></span>
		</label>
		<div class="ct-settings-actions">
			{@render status('events')}
			<button type="submit" class="ct-settings-button is-primary" disabled={busy !== ''}>{local.saveChanges}</button>
		</div>
	</form>
</section>

<section class="ct-settings-section">
	<div class="ct-settings-actions is-split">
		<h2>{local.title}</h2>
		<span class={['ct-settings-badge', account?.connected && 'is-on']}>{account?.connected ? local.connected : local.disconnected}</span>
	</div>
	<p class="ct-settings-note">{local.note}</p>

	{#if account}
		<p class="ct-settings-note">
			{account.base_url}{#if account.username} • {account.username}{/if}{#if account.last_sync_at}
				• {local.lastSync} {when(account.last_sync_at)}{/if}
		</p>
		{#if account.last_error_message}<p class="ct-settings-status is-error"><strong>{local.error}</strong> {account.last_error_message}</p>{/if}

		<h3>{local.pullTitle}</h3>
		<p class="ct-settings-note">{local.pullNote}</p>
		<p class="ct-settings-note">
			{account.playback_reporting_available === true ? local.prOn : account.playback_reporting_available === false ? local.prOff : local.prNone}
			{#if account.last_pull_at}{local.lastRun} {when(account.last_pull_at)}.{/if}
		</p>
		{#if account.last_pull_error_message}
			<p class="ct-settings-status is-error"><strong>{local.error}</strong> {account.last_pull_error_message}</p>
		{/if}
		<div class="ct-settings-actions">
			{@render status('pull')}
			<button type="button" class="ct-settings-button" disabled={busy !== ''} onclick={() => post('pull', jellyfin.urls.pull)}
				>{local.importNow}</button
			>
		</div>

		<details class="ct-settings-more">
			<summary>{local.manual}</summary>
			<div>
				<p class="ct-settings-note">{local.manualNote}</p>
				{#if jellyfin.last_import}
					<p class="ct-settings-note">
						Last import: {jellyfin.last_import.status} ({when(jellyfin.last_import.started_at)}), {jellyfin.last_import.created} created, {jellyfin
							.last_import.skipped} skipped.
					</p>
				{/if}
				<form onsubmit={upload}>
					<label class="ct-settings-field">
						{local.importFile}
						<input
							type="file"
							accept=".tsv,.txt,text/tab-separated-values,text/plain"
							required
							onchange={(event) => (file = event.currentTarget.files?.[0] ?? null)}
						/>
					</label>
					<div class="ct-settings-actions">
						{@render status('upload')}
						<button type="submit" class="ct-settings-button" disabled={busy !== '' || !file}>{local.importUpload}</button>
					</div>
				</form>
			</div>
		</details>

		<form onsubmit={saveSettings}>
			<label class="ct-settings-check"
				><input type="checkbox" bind:checked={pullOn} /><span>Automatically import new Jellyfin history (every {jellyfin.pull_interval_minutes} minutes)</span></label
			>
			<label class="ct-settings-check"><input type="checkbox" bind:checked={pushPlayed} /><span>{local.pushWatched}</span></label>
			<label class="ct-settings-check"><input type="checkbox" bind:checked={pushUnplayed} /><span>{local.pushUnwatched}</span></label>
			<label class="ct-settings-check"><input type="checkbox" bind:checked={scheduled} /><span>{local.scheduled}</span></label>
			<label class="ct-settings-check"><input type="checkbox" bind:checked={instant} /><span>{local.instant}</span></label>
			<div class="ct-settings-actions">
				{@render status('settings')}
				<button type="submit" class="ct-settings-button is-primary" disabled={busy !== ''}>{local.saveSettings}</button>
			</div>
		</form>

		<div class="ct-settings-actions">
			{@render status('push')}
			{@render status('disconnect')}
			<button type="button" class="ct-settings-button" disabled={busy !== ''} onclick={() => post('push', jellyfin.urls.push)}>{local.syncNow}</button>
			<button type="button" class="ct-settings-button" aria-expanded={editing} onclick={() => (editing = !editing)}>{local.edit}</button>
			{#if confirming}
				<span class="ct-settings-note">{local.sure}</span>
				<button type="button" class="ct-settings-button" onclick={() => (confirming = false)}>{local.cancel}</button>
				<button type="button" class="ct-settings-button is-danger" disabled={busy !== ''} onclick={disconnect}>{local.disconnect}</button>
			{:else}
				<button type="button" class="ct-settings-button is-danger" disabled={busy !== ''} onclick={() => (confirming = true)}>{local.disconnect}</button>
			{/if}
		</div>

		{#if editing}
			<form onsubmit={connect}>
				<p class="ct-settings-note">{local.editNote}</p>
				<label class="ct-settings-field">
					{local.serverUrl}
					<input type="url" required placeholder="https://jellyfin.local:8096" bind:value={baseUrl} />
				</label>
				<label class="ct-settings-field">
					{local.apiKey}
					<input type="password" required autocomplete="off" placeholder={local.apiKeyUpdate} bind:value={apiKey} />
				</label>
				<label class="ct-settings-field">
					{local.username}
					<input type="text" autocomplete="off" placeholder={local.usernamePh} bind:value={username} />
				</label>
				<div class="ct-settings-actions">
					{@render status('connect')}
					<button type="button" class="ct-settings-button" onclick={() => (editing = false)}>{local.cancel}</button>
					<button type="submit" class="ct-settings-button is-primary" disabled={busy !== '' || integrations.is_demo}>{local.update}</button>
				</div>
			</form>
		{/if}
	{:else}
		<form onsubmit={connect}>
			<p class="ct-settings-note">{local.connectNote}</p>
			<label class="ct-settings-field">
				{local.serverUrl}
				<input type="url" required placeholder="https://jellyfin.local:8096" bind:value={baseUrl} />
			</label>
			<label class="ct-settings-field">
				{local.apiKey}
				<input type="password" required autocomplete="off" placeholder={local.apiKey} bind:value={apiKey} />
			</label>
			<label class="ct-settings-field">
				{local.username}
				<input type="text" autocomplete="off" placeholder={local.usernamePh} bind:value={username} />
			</label>
			<div class="ct-settings-actions">
				{@render status('connect')}
				<button type="submit" class="ct-settings-button is-primary" disabled={busy !== '' || integrations.is_demo}>{local.connect}</button>
			</div>
		</form>
	{/if}
</section>
