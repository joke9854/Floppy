<script lang="ts">
	import ExternalLink from '@lucide/svelte/icons/external-link';
	import { postForm } from '../integrations/actions.ts';
	import { st } from '../strings.ts';
	import { type SavedAnswer, type SettingsImport, when } from '../types.ts';
	import { type ImportAccount, sharedFields } from './sources.ts';

	/**
	 * A connect-once account source (Last.fm, Koito, Xbox, PSN, Pocket Casts,
	 * GPodder): connect, then Sync now / full history / Disconnect. The views
	 * call the provider before answering, and none is mode- or demo-gated.
	 */
	let {
		account,
		data,
		frequency,
		time,
		mode,
		busy,
		run
	}: {
		account: ImportAccount;
		data: SettingsImport;
		frequency: string;
		time: string;
		mode: string;
		busy: boolean;
		run: (send: () => Promise<SavedAnswer>) => Promise<SavedAnswer | null>;
	} = $props();

	const acct = $derived(data.accounts[account.key]);
	const ctx = $derived({ frequency, pollInterval: data.lastfm_poll_interval, absPollInterval: data.audiobookshelf_poll_interval });
	const urls = $derived(data.urls as unknown as Record<string, string>);
	const shared = $derived(sharedFields({ frequency, time, mode }));
	const history = $derived(acct?.history ?? null);
	const historyError = $derived(account.key === 'lastfm' ? 'History import error: ' : 'Import error: ');
	const historyTone = $derived(
		history?.status === 'completed' ? 'is-done' : history?.status === 'failed' ? 'is-error' : history?.status === 'running' || history?.status === 'queued' ? 'is-active' : ''
	);

	let values = $state<Record<string, string>>({});
	const value = (name: string, fallback?: string) => values[name] ?? fallback ?? '';
	const blank = $derived(
		account.connectReady
			? !account.connectReady(Object.fromEntries(account.connectFields.map((field) => [field.name, value(field.name, field.value)])))
			: account.connectFields.some((field) => field.required && !value(field.name, field.value).trim())
	);

	async function connect(event: SubmitEvent) {
		event.preventDefault();
		if (busy || blank) return;
		const fields: Record<string, string> = account.connectPostsShared ? { ...shared } : {};
		// Passwords go as typed; a space can be part of one.
		for (const field of account.connectFields) {
			const typed = value(field.name, field.value);
			fields[field.name] = field.type === 'password' ? typed : typed.trim();
		}
		const answer = await run(() => postForm(urls[`${account.key}_connect`], fields));
		if (answer?.saved) values = {};
	}

	const action = (name: 'sync' | 'history' | 'disconnect', fields: Record<string, string> = {}) => {
		if (busy) return;
		void run(() => postForm(urls[`${account.key}_${name}`], fields));
	};
</script>

{#snippet links()}
	{#each account.links ?? [] as link (link.href)}
		<a class="ct-settings-link" href={link.href} target="_blank" rel="noopener noreferrer"
			>{link.label} <ExternalLink class="inline size-4" aria-hidden="true" /><span class="sr-only">{st.newTab}</span></a
		>{' '}
	{/each}
{/snippet}

<p>
	<span class={['ct-settings-badge', acct?.connected && 'is-on']}>{acct?.connected ? 'Connected' : 'Disconnected'}</span>
</p>

{#if !acct}
	<p class="ct-settings-note">{account.disconnected(ctx)}</p>
	{#if account.links?.length}<p class="ct-settings-note">{@render links()}</p>{/if}
	<form onsubmit={connect}>
		{#each account.connectFields as field (field.name)}
			<label class="ct-settings-field">
				{field.label}
				<input
					type={field.type}
					name={field.name}
					placeholder={field.placeholder}
					required={field.required}
					autocomplete={field.type === 'password' ? 'off' : undefined}
					spellcheck="false"
					value={value(field.name, field.value)}
					oninput={(event) => (values[field.name] = event.currentTarget.value)}
				/>
			</label>
		{/each}
		<div class="ct-settings-actions">
			<button type="submit" class="ct-settings-button is-primary" disabled={busy || blank}>{account.connectButton}</button>
		</div>
		{#if busy}<p class="ct-settings-note" role="status">Checking with the provider…</p>{/if}
	</form>
	{#if account.footnote}<p class="ct-settings-note">{account.footnote}</p>{/if}
{:else}
	<p class="ct-settings-note">{account.connected(ctx)}</p>
	{#if account.key === 'lastfm' && data.lastfm_recurring_every}
		<p class="ct-settings-note">Recurring import: {data.lastfm_recurring_every} minutes</p>
	{/if}
	{#if account.nameLabel && acct.name}<p class="ct-settings-note">{account.nameLabel}: {acct.name}</p>{/if}
	{#if acct.last_sync}<p class="ct-settings-note">Last sync: {when(acct.last_sync)}</p>{/if}
	{#if acct.error}<p class="ct-settings-status is-error">Error: {acct.error}</p>{/if}
	{#if history}
		<p class={['ct-settings-note', 'ct-import-history', historyTone]}>Full history import: {history.label}</p>
		{#if history.current_page && history.total_pages}
			<p class="ct-settings-note">Page {history.current_page} of {history.total_pages}</p>
		{/if}
		{#if history.completed_at}<p class="ct-settings-note">Completed: {when(history.completed_at)}</p>{/if}
		{#if history.error}<p class="ct-settings-status is-error">{historyError}{history.error}</p>{/if}
	{/if}
	<div class="ct-settings-actions">
		<button type="button" class="ct-settings-button is-primary" disabled={busy} onclick={() => action('sync', account.syncPostsShared ? shared : {})}
			>{account.syncLabel(ctx)}</button
		>
		{#if history?.can_start}
			<button type="button" class="ct-settings-button" disabled={busy} onclick={() => action('history')}>{history.button}</button>
		{/if}
		<button type="button" class="ct-settings-button is-danger" disabled={busy} onclick={() => action('disconnect')}>Disconnect</button>
	</div>
	{#if account.footnote && account.footnoteAlways}<p class="ct-settings-note">{account.footnote}</p>{/if}
{/if}
