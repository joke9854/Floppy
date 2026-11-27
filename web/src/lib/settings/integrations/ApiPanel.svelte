<script lang="ts">
	import { invalidate } from '$app/navigation';
	import { st } from '../strings.ts';
	import { when, type SettingsIntegrations } from '../types.ts';
	import { postForm } from './actions.ts';
	import CopyField from './CopyField.svelte';

	/** Legacy API key, app tokens and connected apps (spec 6-8). */
	let { integrations }: { integrations: SettingsIntegrations } = $props();
	const api = $derived(integrations.api);

	const local = {
		legacy: 'Legacy API key',
		legacyNote:
			'This is a legacy key. It authenticates webhook requests from your media servers and older apps, and over the API it is limited to tracking permissions (scrobbling, progress, saved items, catalog and sync reads). For apps, sign in with your Floppy account, or create a scoped app token below. Those can be limited and revoked one at a time.',
		regenerate: 'Regenerate',
		regenTitle: 'Regenerate the API key?',
		regenWarn: 'Regenerating will invalidate the previous key',
		regenUrls: 'Every webhook, RSS and Stremio URL that uses it changes.',
		cancel: 'Cancel',
		tokens: 'App tokens',
		tokensNote: 'Give each app its own token with only the permissions it needs. Revoking one leaves your other apps connected.',
		created: 'Token created:',
		copyNow: 'Copy it now. Floppy stores only a hash, so this is the only time it can be shown.',
		expired: 'Expired',
		revoke: 'Revoke',
		none: 'No app tokens yet.',
		create: 'Create an app token',
		name: 'Name',
		namePlaceholder: 'Nuvio living room',
		expires: 'Expires',
		expiresHint: 'Leave as Never for an always-on device.',
		permissions: 'Permissions',
		permissionsNote: 'Pre-selected for a tracking client: scrobbling, resume progress, and saved items.',
		createButton: 'Create token',
		apps: 'Connected apps',
		appsNote:
			'Apps you signed in to with your Floppy account. Disconnecting an app signs it out everywhere; it has to ask for your approval again to reconnect.',
		noApps: 'No connected apps yet.'
	};
	const expiries = [
		{ value: '', label: 'Never' },
		{ value: '30', label: '30 days' },
		{ value: '90', label: '90 days' },
		{ value: '365', label: '1 year' }
	];

	let busy = $state(false);
	let notice = $state<{ key: string; text: string; failed: boolean } | null>(null);
	let regenDialog = $state<HTMLDialogElement>();
	let revoking = $state<number | null>(null);
	let newToken = $state<{ name: string; secret: string } | null>(null);
	let name = $state('');
	let expiresIn = $state('');
	// svelte-ignore state_referenced_locally
	let scopes = $state<string[]>(integrations.api.scope_choices.filter((scope) => scope.default).map((scope) => scope.value));

	async function post(key: string, url: string, fields: Record<string, string | string[]> = {}, after?: () => void) {
		busy = true;
		notice = null;
		try {
			const answer = await postForm(url, fields);
			notice = { key, text: answer.saved ? answer.message || st.saved : (answer.message ?? st.failed), failed: !answer.saved };
			if (answer.saved) {
				if (answer.new_token) newToken = answer.new_token;
				after?.();
				await invalidate('floppy:settings');
			}
		} catch {
			notice = { key, text: st.failed, failed: true };
		} finally {
			busy = false;
		}
	}

	async function regenerate(event: SubmitEvent) {
		event.preventDefault();
		regenDialog?.close();
		await post('legacy', api.regenerate_url);
	}

	async function createToken(event: SubmitEvent) {
		event.preventDefault();
		await post('create', api.create_token_url, { name: name.trim(), expires_in_days: expiresIn, scopes }, () => {
			name = '';
			expiresIn = '';
			scopes = api.scope_choices.filter((scope) => scope.default).map((scope) => scope.value);
		});
	}

	function toggle(scope: string, on: boolean) {
		scopes = on ? [...scopes, scope] : scopes.filter((value) => value !== scope);
	}
</script>

{#snippet status(key: string)}
	{#if notice?.key === key}<span class={['ct-settings-status', notice.failed && 'is-error']} role="status">{notice.text}</span>{/if}
{/snippet}

<section class="ct-settings-section">
	<h2>{local.legacy}</h2>
	<p class="ct-settings-note">{local.legacyNote}</p>
	<CopyField value={api.legacy_token} label={local.legacy} />
	<p class="ct-settings-note">{local.regenWarn}</p>
	<div class="ct-settings-actions">
		{@render status('legacy')}
		<button type="button" class="ct-settings-button is-danger" disabled={busy || integrations.is_demo} onclick={() => regenDialog?.showModal()}
			>{local.regenerate}</button
		>
	</div>
</section>

<section class="ct-settings-section" id="app-tokens">
	<div>
		<h2>{local.tokens}</h2>
		<p class="ct-settings-note">{local.tokensNote}</p>
	</div>
	{#if newToken}
		<div class="ct-settings-section" role="status">
			<h3>{local.created} {newToken.name}</h3>
			<p class="ct-settings-note">{local.copyNow}</p>
			<CopyField value={newToken.secret} label="New token secret" />
		</div>
	{/if}
	{#if api.tokens.length}
		<ul class="ct-settings-rows">
			{#each api.tokens as token (token.id)}
				<li class="ct-settings-row">
					<span>
						{token.name}
						{#if token.expired}<span class="ct-settings-badge">{local.expired}</span>{/if}
						<small>
							<span class="ct-settings-code">{token.prefix}…</span>
							Created {when(token.created_at)}
							{token.last_used_at ? ` · Last used ${when(token.last_used_at)}` : ' · Never used'}
							{token.expires_at ? ` · Expires ${when(token.expires_at)}` : ''}
						</small>
						<span class="ct-settings-scopes">
							{#each token.scopes as scope (scope)}<span class="ct-settings-code">{scope}</span>{/each}
						</span>
					</span>
					{#if revoking === token.id}
						<span class="ct-settings-note">{token.name} stops working immediately. Your other apps are unaffected.</span>
						<button type="button" class="ct-settings-button" disabled={busy} onclick={() => (revoking = null)}>{local.cancel}</button>
						<button
							type="button"
							class="ct-settings-button is-danger"
							disabled={busy}
							onclick={() => post('tokens', token.revoke_url, {}, () => (revoking = null))}>{local.revoke}</button
						>
					{:else}
						<button type="button" class="ct-settings-button" disabled={busy} onclick={() => (revoking = token.id)}>{local.revoke}</button>
					{/if}
				</li>
			{/each}
		</ul>
	{:else}
		<p class="ct-settings-note">{local.none}</p>
	{/if}
	<div class="ct-settings-actions">{@render status('tokens')}</div>

	<details class="ct-settings-more">
		<summary>{local.create}</summary>
		<div>
			<form class="contents" onsubmit={createToken}>
				<label class="ct-settings-field">
					{local.name}
					<input type="text" required maxlength="255" placeholder={local.namePlaceholder} bind:value={name} />
				</label>
				<label class="ct-settings-field">
					{local.expires}
					<select bind:value={expiresIn}>
						{#each expiries as expiry (expiry.value)}<option value={expiry.value}>{expiry.label}</option>{/each}
					</select>
					<small class="ct-settings-note">{local.expiresHint}</small>
				</label>
				<fieldset class="ct-settings-field">
					<legend>{local.permissions}</legend>
					<p class="ct-settings-note">{local.permissionsNote}</p>
					{#each api.scope_choices as scope (scope.value)}
						<label class="ct-settings-check">
							<input type="checkbox" checked={scopes.includes(scope.value)} onchange={(event) => toggle(scope.value, event.currentTarget.checked)} />
							<span><span class="ct-settings-code">{scope.value}</span><small>{scope.description}</small></span>
						</label>
					{/each}
				</fieldset>
				<div class="ct-settings-actions">
					{@render status('create')}
					<button type="submit" class="ct-settings-button is-primary" disabled={busy || integrations.is_demo || !name.trim()}>{local.createButton}</button>
				</div>
			</form>
		</div>
	</details>
</section>

<section class="ct-settings-section" id="connected-apps">
	<div>
		<h2>{local.apps}</h2>
		<p class="ct-settings-note">{local.appsNote}</p>
	</div>
	{#if api.connected_apps.length}
		<ul class="ct-settings-rows">
			{#each api.connected_apps as app (app.client_id)}
				<li class="ct-settings-row">
					<span>
						{app.name}
						<small>Connected {when(app.connected_at)}</small>
						<span class="ct-settings-scopes">
							{#each app.scopes as scope (scope)}<span class="ct-settings-code">{scope}</span>{/each}
						</span>
					</span>
					<button type="button" class="ct-settings-button" disabled={busy} onclick={() => post('apps', app.revoke_url)}>{local.revoke}</button>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="ct-settings-note">{local.noApps}</p>
	{/if}
	<div class="ct-settings-actions">{@render status('apps')}</div>
</section>

<dialog class="ct-settings-dialog" bind:this={regenDialog} aria-labelledby="ct-regen-title">
	<form onsubmit={regenerate}>
		<h2 id="ct-regen-title">{local.regenTitle}</h2>
		<p class="ct-settings-note">{local.regenWarn}</p>
		<p class="ct-settings-note">{local.regenUrls}</p>
		<div class="ct-settings-actions">
			<button type="button" class="ct-settings-button" onclick={() => regenDialog?.close()}>{local.cancel}</button>
			<button type="submit" class="ct-settings-button is-danger">{local.regenerate}</button>
		</div>
	</form>
</dialog>
