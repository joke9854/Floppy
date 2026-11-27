<script lang="ts">
	import { invalidate } from '$app/navigation';
	import { st } from '../strings.ts';
	import { when, type SettingsIntegrations } from '../types.ts';
	import { postForm } from './actions.ts';
	import CopyField from './CopyField.svelte';

	/** Stremio: the scrobbler addon install, install credentials and catalog status. */
	let { integrations }: { integrations: SettingsIntegrations } = $props();
	const stremio = $derived(integrations.stremio);

	let busy = $state('');
	let notice = $state<{ key: string; text: string; failed: boolean } | null>(null);
	let confirming = $state<number | null>(null);
	let name = $state('');
	let playback = $state(true);

	async function post(key: string, url: string, fields: Record<string, string> = {}, after?: () => void) {
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

	function create(event: SubmitEvent) {
		event.preventDefault();
		return post('create', stremio.create_grant_url, { name: name.trim(), ...(playback ? { allow_playback_start: 'on' } : {}) }, () => {
			name = '';
			playback = true;
		});
	}

	function revoke(grant: { id: number; revoke_url: string }) {
		confirming = null;
		return post(`grant-${grant.id}`, grant.revoke_url);
	}
</script>

{#snippet status(key: string)}
	{#if notice?.key === key}<span class={['ct-settings-status', notice.failed && 'is-error']} role="status">{notice.text}</span>{/if}
{/snippet}

<section class="ct-settings-section">
	<div>
		<h2>Stremio Integration</h2>
		<p class="ct-settings-note">
			Install the Floppy Scrobbler addon in Stremio to mark movies and episodes as in progress the moment playback starts. Pair it with the Stremio import on
			the <a href={stremio.import_url} data-sveltekit-reload>Import page</a>, which syncs watched state from your Stremio library every 2 hours.
		</p>
	</div>
	<h3>Setup Instructions</h3>
	<ol class="ct-settings-steps">
		<li>
			Copy your personal addon URL:
			<CopyField value={stremio.addon_url} label="Stremio addon URL" />
		</li>
		<li>
			Optional:
			<a href={stremio.configure_url} target="_blank" rel="noopener noreferrer">choose which catalogs<span class="sr-only"> {st.newTab}</span></a>
			the addon publishes, then use the URL it gives you in place of the one above.
		</li>
		<li>In Stremio, open <strong>Addons</strong>, paste the URL into the search box at the top, and click <strong>Install</strong>.</li>
		<li>Floppy must be reachable from your Stremio device over <strong>HTTPS</strong> (plain HTTP only works for localhost).</li>
		<li>Playback start marks the item in progress; the recurring library import marks items watched.</li>
	</ol>

	<h3>Install credentials</h3>
	<p class="ct-settings-note">
		The install URL carries its credential in the path, so it ends up in logs and browser history. Create one per device: revoking it breaks only that install,
		where regenerating your account token breaks every integration at once.
	</p>
	{#if stremio.grants.length}
		<ul class="ct-settings-rows">
			{#each stremio.grants as grant (grant.id)}
				<li class="ct-settings-row">
					<span
						>{grant.name}<small
							>Created {when(grant.created_at)}{grant.last_used_at ? ` · Last used ${when(grant.last_used_at)}` : ' · Never used'}{grant.allow_playback_start
								? ''
								: ' · Catalogs only'}</small
						></span
					>
					{#if confirming === grant.id}
						<span class="ct-settings-actions">
							<button type="button" class="ct-settings-button" onclick={() => (confirming = null)}>Cancel</button>
							<button type="button" class="ct-settings-button is-danger" disabled={busy !== ''} onclick={() => revoke(grant)}>Revoke</button>
						</span>
					{:else}
						<button
							type="button"
							class="ct-settings-button is-danger"
							aria-label="Revoke {grant.name}"
							disabled={busy !== ''}
							onclick={() => (confirming = grant.id)}>Revoke</button
						>
					{/if}
				</li>
			{/each}
		</ul>
	{:else}
		<p class="ct-settings-note">No install credentials yet, so the URL above uses your account token.</p>
	{/if}
	<div class="ct-settings-actions">
		{#each stremio.grants as grant (grant.id)}{@render status(`grant-${grant.id}`)}{/each}
	</div>
	<form onsubmit={create}>
		<label class="ct-settings-field">
			Install name
			<input type="text" required maxlength="255" placeholder="Living room TV" autocomplete="off" bind:value={name} />
		</label>
		<label class="ct-settings-check"><input type="checkbox" bind:checked={playback} /><span>Mark items in progress on playback</span></label>
		<div class="ct-settings-actions">
			{@render status('create')}
			<button type="submit" class="ct-settings-button is-primary" disabled={busy !== '' || integrations.is_demo || !name.trim()}>Create install</button>
		</div>
	</form>

	{#if stremio.readiness.length}
		<h3>Catalog Status</h3>
		<ul class="ct-settings-rows">
			{#each stremio.readiness as item (item.noun + item.list_name)}
				<li class="ct-settings-row">
					<span>
						{#if item.unresolved > 0}
							<strong>{item.publishable} of {item.total}</strong>
							{item.noun} in <strong>{item.list_name}</strong> can be published. Stremio identifies titles by IMDb ID, and the other {item.unresolved}
							{item.unresolved === 1 ? 'has' : 'have'} none yet. Floppy resolves these in the background, but a title with no IMDb ID at its provider stays
							unpublishable.
						{:else}
							All <strong>{item.total}</strong>
							{item.noun} in <strong>{item.list_name}</strong> can be published.
						{/if}
					</span>
				</li>
			{/each}
		</ul>
	{/if}
</section>
