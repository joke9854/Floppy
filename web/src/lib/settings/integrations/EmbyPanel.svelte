<script lang="ts">
	import type { SettingsIntegrations } from '../types.ts';
	import CopyField from './CopyField.svelte';

	/** Emby (integrations.html): webhook setup instructions, no forms. */
	let { integrations }: { integrations: SettingsIntegrations } = $props();
</script>

<section class="ct-settings-section">
	<div>
		<h2>Emby Integration</h2>
		<p class="ct-settings-note">Connect Emby to automatically track your watching progress.</p>
	</div>
	<h3>Setup Instructions</h3>
	<ol class="ct-settings-steps">
		<li>In Emby, go to <strong>Settings &gt; Notifications</strong>.</li>
		<li>Click <strong>Add Notification</strong>.</li>
		<li>
			Configure the notification with the following settings:
			<ul>
				<li>Request content type: <strong>multipart/form-data</strong></li>
				<li>Events: <strong>Play</strong> and <strong>Stop</strong></li>
				<li>Limit user events to: your Emby user</li>
				<li><strong>Limit library events to</strong> and <strong>Limit devices events to</strong> are optional.</li>
			</ul>
		</li>
		<li>
			Set the webhook URL to:
			<CopyField value={integrations.emby_webhook_url} label="Emby webhook URL" />
		</li>
	</ol>
</section>
