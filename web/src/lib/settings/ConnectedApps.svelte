<script lang="ts">
	import { invalidate } from '$app/navigation';
	import { djangoForm } from '#lib/csrf.ts';
	import { st } from './strings.ts';
	import { readAnswer, when, type SettingsScreen } from './types.ts';

	/**
	 * Connected apps (connected_apps.html): signed-in installs (sign one out),
	 * apps that sync the library, and CineTrack crash reports.
	 */
	let { screen }: { screen: SettingsScreen } = $props();
	const apps = $derived(screen.connected_apps!);

	const local = {
		signedIn: 'Signed-in apps',
		signedInNote:
			"One row per install. Signing one out ends only that install's session; your history is untouched and the app can sign in again.",
		lastActive: 'Last signed in or refreshed',
		signOut: 'Sign out',
		noApps: 'No app is signed in to your account.',
		tokensIn: 'App tokens, and disconnecting an app from every install at once, are in',
		integrations: 'Integrations',
		sync: 'Sync connections',
		syncNote: 'Apps that keep a copy of your library in step with Floppy, and when each last synced.',
		lastSync: 'Last sync',
		notSynced: 'Not synced yet',
		noSync: 'No app syncs with your library yet.',
		crashes: 'Crash reports',
		crashesNote:
			'Sent by CineTrack when crash reports are on in its settings. They contain the app version, device model and a stack trace, never your library or credentials.',
		exportJson: 'Export JSON',
		showing: (shown: number, total: number) => `Showing the newest ${shown} of ${total}. The export has all of them.`,
		noCrashes: 'No crash reports.'
	};

	let busy = $state('');
	let notice = $state<{ text: string; failed: boolean } | null>(null);

	async function signOut(url: string, id: string) {
		busy = id;
		notice = null;
		try {
			const answer = await readAnswer(await djangoForm(url, {}, { json: true }));
			notice = { text: answer.saved ? answer.message || st.saved : (answer.message ?? st.failed), failed: !answer.saved };
			if (answer.saved) await invalidate('floppy:settings');
		} catch {
			notice = { text: st.failed, failed: true };
		} finally {
			busy = '';
		}
	}
</script>

<section class="ct-settings-section">
	<div>
		<h2>{local.signedIn}</h2>
		<p class="ct-settings-note">{local.signedInNote}</p>
	</div>
	{#if notice}<span class={['ct-settings-status', notice.failed && 'is-error']} role="status">{notice.text}</span>{/if}
	{#if apps.sessions.length}
		<ul class="ct-settings-rows">
			{#each apps.sessions as session (session.id)}
				<li class="ct-settings-row">
					<span>
						{session.name}
						<small>{local.lastActive} {when(session.last_active)}</small>
						<small class="ct-settings-scopes">{#each session.scopes as scope (scope)}<code class="ct-settings-code">{scope}</code> {/each}</small>
					</span>
					<button type="button" class="ct-settings-button" disabled={busy !== ''} onclick={() => signOut(session.revoke_url, session.id)}
						>{local.signOut}</button
					>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="ct-settings-note">{local.noApps}</p>
	{/if}
	<p class="ct-settings-note">
		{local.tokensIn}
		<a class="ct-settings-link" href="{apps.urls.integrations}#connected-apps" data-sveltekit-reload>{local.integrations}</a>.
	</p>
</section>

<section class="ct-settings-section">
	<div>
		<h2>{local.sync}</h2>
		<p class="ct-settings-note">{local.syncNote}</p>
	</div>
	{#if apps.sync_connections.length}
		<ul class="ct-settings-rows">
			{#each apps.sync_connections as connection, index (index)}
				<li class="ct-settings-row">
					<span>{connection.label}<small>{connection.last_sync ? `${local.lastSync} ${when(connection.last_sync)}` : local.notSynced}</small></span>
					<span class="ct-settings-badge">{connection.status}</span>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="ct-settings-note">{local.noSync}</p>
	{/if}
</section>

<section class="ct-settings-section">
	<div class="ct-settings-actions is-split">
		<h2>{local.crashes}</h2>
		{#if apps.crash_report_count}<a class="ct-settings-button" href={apps.urls.export_crash_reports} download>{local.exportJson}</a>{/if}
	</div>
	<p class="ct-settings-note">{local.crashesNote}</p>
	{#if apps.crash_reports.length}
		<div class="ct-settings-rows">
			{#each apps.crash_reports as report (report.id)}
				<details class="ct-settings-more">
					<summary>
						<span>
							{report.kind} · <code class="ct-settings-code">{report.exception_class || '—'}</code>
							<small>{when(report.occurred_at)} · {report.app_version} · {report.device_model} · Android SDK {report.android_sdk}</small>
						</span>
					</summary>
					<div><pre>{report.stack_trace}</pre></div>
				</details>
			{/each}
		</div>
		{#if apps.crash_report_count > apps.crash_reports.length}
			<p class="ct-settings-note">{local.showing(apps.crash_reports.length, apps.crash_report_count)}</p>
		{/if}
	{:else}
		<p class="ct-settings-note">{local.noCrashes}</p>
	{/if}
</section>
