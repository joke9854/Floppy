<script lang="ts">
	import { st } from '../strings.ts';
	import type { SettingsIntegrations } from '../types.ts';
	import CopyField from './CopyField.svelte';

	/** Kodi (integrations.html): HTTP Scrobbler setup instructions, no forms. */
	let { integrations }: { integrations: SettingsIntegrations } = $props();
</script>

<section class="ct-settings-section">
	<div>
		<h2>Kodi Integration</h2>
		<p class="ct-settings-note">Connect Kodi to automatically track your watching progress.</p>
	</div>
	<h3>Setup Instructions</h3>
	<ol class="ct-settings-steps">
		<li>You will need TMDB and/or TVDB metadata sources enabled in Kodi so that external IDs are included in webhook payloads.</li>
		<li>
			Download and install the
			<a href="https://github.com/sboddy/KodiAddon-HttpScrobbler" target="_blank" rel="noopener noreferrer"
				>HTTP Scrobbler add-on<span class="sr-only"> {st.newTab}</span></a
			>.
		</li>
		<li>In Kodi, go to <strong>Settings &gt; Services &gt; Control</strong> and enable <strong>Allow remote control via HTTP</strong>.</li>
		<li>
			In the HTTP Scrobbler add-on settings, set the webhook URL to:
			<p class="ct-settings-note">Tip: open the Kodi web interface at <code class="ct-settings-code">http://&lt;kodi-ip&gt;:8080</code> to configure the add-on — easier than using the remote.</p>
			<CopyField value={integrations.kodi_webhook_url} label="Kodi webhook URL" />
		</li>
		<li>Leave the username and password fields blank.</li>
		<li>
			In the add-on's "Scrobble at specific events" settings, make sure <strong>Start playback</strong>,
			<strong>Playback stopped (not finished)</strong>, and <strong>Playback finished (not stopped before reaching the end)</strong> are all enabled (they're
			on by default).
		</li>
		<li>
			If you use the add-on's <strong>Skip all events after sending stop/end</strong> option, turn it off — it can suppress the events Floppy needs to mark an
			episode watched.
		</li>
		<li>An item is marked watched when playback reaches 80% or Kodi reports <em>Playback finished</em>.</li>
	</ol>
</section>
