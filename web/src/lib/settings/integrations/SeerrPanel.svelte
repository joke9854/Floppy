<script lang="ts">
	import { invalidate } from '$app/navigation';
	import { st } from '../strings.ts';
	import type { SettingsIntegrations } from '../types.ts';
	import { postForm } from './actions.ts';
	import CopyField from './CopyField.svelte';

	/** Seerr: auto-add settings, the per-user webhook and the optional global webhook. */
	let { integrations }: { integrations: SettingsIntegrations } = $props();
	const seerr = $derived(integrations.seerr);

	const payload = `{
  "media_type": "{{media_type}}",
  "media_tmdbid": "{{media_tmdbid}}",
  "media_status": "{{media_status}}",
  "requestedBy_username": "{{requestedBy_username}}"
}`;
	const globalPayload = `{
  "media_type": "{{media_type}}",
  "media_tmdbid": "{{media_tmdbid}}",
  "media_status": "{{media_status}}",
  "requestedBy_username": "{{requestedBy_username}}",
  "secret": "REPLACE_WITH_SHARED_SECRET"
}`;

	let busy = $state(false);
	let notice = $state<{ text: string; failed: boolean } | null>(null);
	// svelte-ignore state_referenced_locally
	let enabled = $state(integrations.seerr.enabled ? '1' : '0');
	// svelte-ignore state_referenced_locally
	let triggers = $state(integrations.seerr.trigger_statuses);
	// svelte-ignore state_referenced_locally
	let usernames = $state(integrations.seerr.allowed_usernames);
	// svelte-ignore state_referenced_locally
	let defaultStatus = $state(integrations.seerr.default_added_status);

	async function save(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		notice = null;
		try {
			const answer = await postForm(seerr.save_url, {
				jellyseerr_enabled: enabled,
				jellyseerr_trigger_statuses: triggers,
				jellyseerr_allowed_usernames: usernames,
				jellyseerr_default_added_status: defaultStatus
			});
			notice = { text: answer.saved ? answer.message || st.saved : (answer.message ?? st.failed), failed: !answer.saved };
			if (answer.saved) await invalidate('floppy:settings');
		} catch {
			notice = { text: st.failed, failed: true };
		} finally {
			busy = false;
		}
	}
</script>

<section class="ct-settings-section">
	<div>
		<h2>Seerr Integration</h2>
		<p class="ct-settings-note">Use a Seerr webhook to automatically add requested/approved media into Floppy.</p>
	</div>

	<h3>Seerr Settings</h3>
	<form onsubmit={save}>
		<label class="ct-settings-field">
			Auto-add requested media
			<select class="ct-settings-select" bind:value={enabled}>
				<option value="1">Enabled - Allow Seerr to automatically add media</option>
				<option value="0">Disabled - Do not allow Seerr to add media</option>
			</select>
			<small>Controls whether Seerr webhooks are allowed to add items to your Floppy list.</small>
		</label>
		<label class="ct-settings-field">
			Trigger statuses (comma-separated)
			<input type="text" autocomplete="off" placeholder="PENDING,PROCESSING,PARTIALLY_AVAILABLE,AVAILABLE" bind:value={triggers} />
			<small>Examples: PENDING,PROCESSING,PARTIALLY_AVAILABLE,AVAILABLE. Leave blank for default behaviour (UNKNOWN is ignored).</small>
		</label>
		<label class="ct-settings-field">
			Allowed Seerr usernames (comma-separated)
			<input type="text" autocomplete="off" placeholder="john, someoneelse" bind:value={usernames} />
			<small>Leave blank to allow any requester. If set, only those usernames can trigger adds.</small>
		</label>
		<label class="ct-settings-field">
			Default Floppy status for added items
			<select class="ct-settings-select" bind:value={defaultStatus}>
				{#each seerr.default_status_choices as choice (choice)}<option value={choice}>{choice}</option>{/each}
			</select>
		</label>
		<div class="ct-settings-actions">
			{#if notice}<span class={['ct-settings-status', notice.failed && 'is-error']} role="status">{notice.text}</span>{/if}
			<button type="submit" class="ct-settings-button is-primary" disabled={busy || integrations.is_demo}>Save Changes</button>
		</div>
	</form>

	<h3>Setup Instructions</h3>
	<ol class="ct-settings-steps">
		<li>In Seerr, go to <strong>Settings &gt; Notifications &gt; Webhook</strong>.</li>
		<li>Create a webhook with method <strong>POST</strong> and content type <strong>application/json</strong>.</li>
		<li>
			Set the webhook URL to:
			<CopyField value={seerr.webhook_url} label="Seerr webhook URL" />
		</li>
		<li>
			Paste this <strong>JSON Payload</strong> template into Seerr:
			<CopyField value={payload} label="JSON template" multiline rows={6} />
			<p class="ct-settings-note">
				Important: Seerr's default payload will not work with Floppy. You must use the template above. If you see logs like
				<code class="ct-settings-code">unsupported media_type='{'{media_type}'}'</code>, Seerr is sending the literal template (it was pasted/escaped
				incorrectly).
			</p>
		</li>
		<li>Select the notification types you want (commonly request/approval events).</li>
	</ol>
</section>

{#if seerr.global_enabled}
	<section class="ct-settings-section">
		<div>
			<h2>Global Webhook (multi-user households)</h2>
			<p class="ct-settings-note">
				Seerr only supports one webhook per instance. If multiple Floppy users share the same Seerr/Overseerr instance, point Seerr at this single global URL
				instead of a per-user one. Floppy matches each incoming request's requester username against every user's <strong>Allowed Seerr usernames</strong>
				above, so each user must still enable "Auto-add requested media" and list their own Seerr username there.
			</p>
		</div>
		<ol class="ct-settings-steps">
			<li>In Seerr, go to <strong>Settings &gt; Notifications &gt; Webhook</strong>.</li>
			<li>Create a webhook with method <strong>POST</strong> and content type <strong>application/json</strong>.</li>
			<li>
				Set the webhook URL to:
				<CopyField value={seerr.global_webhook_url} label="Seerr global webhook URL" />
			</li>
			<li>
				Paste this <strong>JSON Payload</strong> template into Seerr, replacing <code class="ct-settings-code">REPLACE_WITH_SHARED_SECRET</code> with the
				value your administrator configured in <code class="ct-settings-code">SEERR_GLOBAL_WEBHOOK_SECRET</code>:
				<CopyField value={globalPayload} label="Global JSON template" multiline rows={7} />
			</li>
		</ol>
	</section>
{/if}
