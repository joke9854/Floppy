<script lang="ts">
	import type { SettingsIntegrations } from '../types.ts';
	import CopyField from './CopyField.svelte';

	/** Nuvio setup (spec 17): the server URL and how to connect and disconnect. */
	let { integrations }: { integrations: SettingsIntegrations } = $props();
</script>

<section class="ct-settings-section">
	<div>
		<h2>Nuvio Integration</h2>
		<p class="ct-settings-note">
			Connect Nuvio TV or Nuvio Mobile for two-way scrobbling, resume progress, and watched-state sync. Nuvio talks to Floppy's API directly, so there's no
			webhook to configure.
		</p>
	</div>
	<h3>Setup Instructions</h3>
	<ol class="ct-settings-steps">
		<li>
			Create an <a class="ct-settings-link" href="?open=api#app-tokens">app token</a> above, named after the device. The default permissions already cover
			everything Nuvio needs.
		</li>
		<li>Copy the token secret when it's shown — Floppy only displays it once.</li>
		<li>
			In Nuvio, enter this Server URL and the token secret you copied:
			<CopyField value={integrations.nuvio_server_url} label="Nuvio server URL" />
		</li>
		<li>
			Revoke the token in <a class="ct-settings-link" href="?open=api#app-tokens">App tokens</a> above to disconnect the device. This never deletes your tracking
			data.
		</li>
	</ol>
</section>
