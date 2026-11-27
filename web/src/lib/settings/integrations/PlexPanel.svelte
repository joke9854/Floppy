<script lang="ts">
	import { invalidate } from '$app/navigation';
	import { st } from '../strings.ts';
	import { when, type SettingsIntegrations } from '../types.ts';
	import { postForm } from './actions.ts';
	import CopyField from './CopyField.svelte';
	import LibraryPicker from './LibraryPicker.svelte';

	/** Plex: usernames, webhook libraries, sharing the webhook, received shares, status and setup. */
	let { integrations }: { integrations: SettingsIntegrations } = $props();
	const plex = $derived(integrations.plex);
	const allValues = $derived(plex.libraries.map((library) => library.value));

	const local = {
		title: 'Plex Integration',
		note: 'Connect Plex to automatically track your watching progress.',
		usernames: 'Plex Usernames',
		usernamesNote: 'This username (or several, comma-separated) will be used to filter which events are sent to your webhook.',
		usernamesPh: 'username1, username2, username3',
		save: 'Save Changes',
		libraries: 'Plex Webhook Libraries',
		librariesNote: 'Choose which Plex libraries are accepted by your webhook. All libraries are selected by default.',
		noneNote: 'With none selected, every library is accepted.',
		connectFirst: 'Connect Plex from the Import page to load your available libraries.',
		share: 'Share Plex Webhook',
		shareNote:
			"Share this server's webhook with another Floppy user without sharing your Plex token. The recipient must enable the share before events are recorded.",
		shareConnect: 'Connect Plex from the Import page before sharing its webhook.',
		recipient: 'Floppy user',
		select: 'Select a user',
		plexUsername: 'Plex username',
		shareButton: 'Share',
		current: 'Current shares',
		enabled: 'Enabled by recipient',
		waiting: 'Waiting for recipient opt-in',
		revoke: 'Revoke Access',
		cancel: 'Cancel',
		received: 'Shared Plex Webhooks',
		webhookStatus: 'Webhook Status'
	};

	let busy = $state('');
	let notice = $state<{ key: string; text: string; failed: boolean } | null>(null);

	// svelte-ignore state_referenced_locally
	let usernames = $state(integrations.plex.usernames);
	// svelte-ignore state_referenced_locally
	let webhookLibs = $state<string[]>([...integrations.plex.selected_libraries]);
	let recipient = $state('');
	let shareUsername = $state('');
	// svelte-ignore state_referenced_locally
	let shareLibs = $state<string[]>(integrations.plex.libraries.map((library) => library.value));
	let edits = $state<Record<number, { username?: string; libs?: string[] }>>({});
	let confirming = $state<number | null>(null);

	async function post(key: string, url: string, fields: Record<string, string | string[]>, after?: () => void) {
		busy = key;
		notice = null;
		try {
			const answer = await postForm(url, fields);
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

	function libraryFields(libs: string[]): Record<string, string | string[]> {
		const all = allValues.length > 0 && allValues.every((value) => libs.includes(value));
		return all ? { plex_webhook_share_all_libraries: '1' } : { plex_webhook_share_libraries: libs };
	}

	function saveUsernames(event: SubmitEvent) {
		event.preventDefault();
		return post('usernames', plex.urls.usernames, { plex_usernames: usernames });
	}

	function saveLibraries(event: SubmitEvent) {
		event.preventDefault();
		return post('libraries', plex.urls.libraries, { plex_webhook_libraries: webhookLibs });
	}

	function createShare(event: SubmitEvent) {
		event.preventDefault();
		return post(
			'share',
			plex.urls.share,
			{ plex_webhook_share_recipient: recipient, plex_webhook_share_username: shareUsername.trim(), ...libraryFields(shareLibs) },
			() => {
				recipient = '';
				shareUsername = '';
				shareLibs = [...allValues];
			}
		);
	}

	function saveShare(event: SubmitEvent, share: { id: number; plex_username: string; all_libraries: boolean; libraries: string[] }) {
		event.preventDefault();
		const edit = edits[share.id];
		const libs = edit?.libs ?? (share.all_libraries ? allValues : share.libraries);
		return post(`share-${share.id}`, plex.urls.share, {
			plex_webhook_share_id: String(share.id),
			plex_webhook_share_username: (edit?.username ?? share.plex_username).trim(),
			...libraryFields(libs)
		});
	}

	function deleteShare(id: number) {
		confirming = null;
		return post(`share-${id}`, plex.urls.delete_share, { plex_webhook_share_id: String(id) });
	}

	const receivedScope = { all: 'All libraries', selected: 'Selected libraries only', none: 'No libraries' } as const;
</script>

{#snippet status(key: string)}
	{#if notice?.key === key}<span class={['ct-settings-status', notice.failed && 'is-error']} role="status">{notice.text}</span>{/if}
{/snippet}

<section class="ct-settings-section">
	<div>
		<h2>{local.title}</h2>
		<p class="ct-settings-note">{local.note}</p>
	</div>

	<h3>{local.usernames}</h3>
	<form onsubmit={saveUsernames}>
		<p class="ct-settings-note">{local.usernamesNote}</p>
		<label class="ct-settings-field">
			{local.usernames}
			<input type="text" autocomplete="off" placeholder={local.usernamesPh} bind:value={usernames} />
		</label>
		<div class="ct-settings-actions">
			{@render status('usernames')}
			<button type="submit" class="ct-settings-button is-primary" disabled={busy !== ''}>{local.save}</button>
		</div>
	</form>

	<h3>{local.libraries}</h3>
	<p class="ct-settings-note">{local.librariesNote}</p>
	{#if plex.libraries.length}
		<form onsubmit={saveLibraries}>
			<LibraryPicker libraries={plex.libraries} selected={webhookLibs} onchange={(next) => (webhookLibs = next)} disabled={busy !== ''} />
			<p class="ct-settings-note">{local.noneNote}</p>
			<div class="ct-settings-actions">
				{@render status('libraries')}
				<button type="submit" class="ct-settings-button is-primary" disabled={busy !== ''}>{local.save}</button>
			</div>
		</form>
	{:else}
		<p class="ct-settings-note">{local.connectFirst}</p>
	{/if}

	<h3>{local.share}</h3>
	<p class="ct-settings-note">{local.shareNote}</p>
	{#if plex.connected}
		<form onsubmit={createShare}>
			<label class="ct-settings-field">
				{local.recipient}
				<select class="ct-settings-select" required bind:value={recipient}>
					<option value="">{local.select}</option>
					{#each plex.recipients as user (user.id)}<option value={String(user.id)}>{user.username}</option>{/each}
				</select>
			</label>
			<label class="ct-settings-field">
				{local.plexUsername}
				<input type="text" required maxlength="255" autocomplete="off" placeholder={local.usernamesPh} bind:value={shareUsername} />
				<small>{local.usernamesNote}</small>
			</label>
			<LibraryPicker libraries={plex.libraries} selected={shareLibs} onchange={(next) => (shareLibs = next)} disabled={busy !== ''} />
			<div class="ct-settings-actions">
				{@render status('share')}
				<button type="submit" class="ct-settings-button is-primary" disabled={busy !== '' || integrations.is_demo}>{local.shareButton}</button>
			</div>
		</form>
	{:else}
		<p class="ct-settings-note">{local.shareConnect}</p>
	{/if}

	{#if plex.shares.length}
		<h4>{local.current}</h4>
		{#each plex.shares as share (share.id)}
			<form onsubmit={(event) => saveShare(event, share)}>
				<p class="ct-settings-note">{local.recipient}: <strong>{share.recipient}</strong></p>
				<label class="ct-settings-field">
					{local.plexUsername}
					<input
						type="text"
						required
						maxlength="255"
						autocomplete="off"
						value={edits[share.id]?.username ?? share.plex_username}
						oninput={(event) => (edits[share.id] = { ...edits[share.id], username: event.currentTarget.value })}
					/>
				</label>
				<LibraryPicker
					libraries={plex.libraries}
					selected={edits[share.id]?.libs ?? (share.all_libraries ? allValues : share.libraries)}
					onchange={(next) => (edits[share.id] = { ...edits[share.id], libs: next })}
					disabled={busy !== ''}
				/>
				<p class="ct-settings-note">{share.recipient_enabled ? local.enabled : local.waiting}</p>
				<div class="ct-settings-actions">
					{@render status(`share-${share.id}`)}
					{#if confirming === share.id}
						<button type="button" class="ct-settings-button" onclick={() => (confirming = null)}>{local.cancel}</button>
						<button type="button" class="ct-settings-button is-danger" disabled={busy !== ''} onclick={() => deleteShare(share.id)}>{local.revoke}</button>
					{:else}
						<button type="button" class="ct-settings-button is-danger" disabled={busy !== ''} onclick={() => (confirming = share.id)}>{local.revoke}</button>
					{/if}
					<button type="submit" class="ct-settings-button is-primary" disabled={busy !== '' || integrations.is_demo}>{local.save}</button>
				</div>
			</form>
		{/each}
	{/if}

	{#if plex.received.length}
		<h3>{local.received}</h3>
		<ul class="ct-settings-rows">
			{#each plex.received as share (share.id)}
				<li class="ct-settings-row">
					<span>
						Shared by <strong>{share.owner}</strong> for Plex username <strong>{share.plex_username}</strong>
						<small>{receivedScope[share.libraries]}</small>
						{@render status(`received-${share.id}`)}
					</span>
					<button
						type="button"
						class="ct-settings-button"
						disabled={busy !== ''}
						onclick={() => post(`received-${share.id}`, plex.urls.toggle_share, { plex_webhook_share_id: String(share.id), enabled: share.enabled ? '0' : '1' })}
						>{share.enabled ? 'Turn Off' : 'Turn On'}</button
					>
				</li>
			{/each}
		</ul>
	{/if}

	<h3>{local.webhookStatus}</h3>
	<div class="ct-settings-note" role="status">
		{#if plex.webhook.status === 'needs_update'}
			<strong>Webhook URL needs updating</strong>
			<p>
				You regenerated your API token on {when(plex.webhook.rotated_at)}. Plex webhooks using the old token will be rejected with a 401. Update the Plex webhook URL
				to the one shown below.
			</p>
		{:else if plex.webhook.status === 'error'}
			<strong>Last webhook error</strong>
			<p>{plex.webhook.error} ({when(plex.webhook.error_at)})</p>
		{:else if plex.webhook.status === 'received'}
			<p>Last webhook received {when(plex.webhook.last_received_at)}.</p>
		{:else}
			<strong>No Plex webhooks received yet</strong>
			<p>If you expect automatic logging, confirm webhooks are enabled in Plex and that the URL includes your current API token.</p>
		{/if}
	</div>

	<h3>Setup Instructions</h3>
	<ol class="ct-settings-steps">
		<li>You will need a Plex Pass subscription to use webhooks.</li>
		<li>In Plex, go to <strong>Settings &gt; Server &gt; Network</strong> and enable Webhooks.</li>
		<li>
			Go to
			<a href="https://app.plex.tv/desktop/#!/settings/webhooks" target="_blank" rel="noopener noreferrer"
				>Settings &gt; Webhooks<span class="sr-only"> {st.newTab}</span></a
			>
			and click <strong>Add Webhook</strong>, then enter the following URL:
			<CopyField value={plex.webhook_url} label="Plex webhook URL" />
		</li>
	</ol>
</section>
