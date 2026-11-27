<script lang="ts">
	import FileUp from '@lucide/svelte/icons/file-up';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import { postForm } from '../integrations/actions.ts';
	import { st } from '../strings.ts';
	import { when, type SettingsImportActivity } from '../types.ts';

	/**
	 * The Import page's activity panel: periodic imports, the last 7 days of
	 * import tasks, tracked runs (cancel / undo) and the media imported per
	 * source. It polls while the tab is visible and keeps the last good data.
	 */
	let { initial, url }: { initial: SettingsImportActivity | null; url: string } = $props();

	// svelte-ignore state_referenced_locally
	// Null when the server could not read the activity yet; the poll fills it.
	let activity = $state<SettingsImportActivity>(
		initial ?? { schedules: [], results: [], runs: [], source_media: [], delete_schedule_url: '' }
	);
	let busy = $state(false);
	let notice = $state<{ section: string; text: string; failed: boolean } | null>(null);
	let open = $state<Record<string, boolean>>({});
	let copied = $state('');
	let pending = $state<{ title: string; lines: string[]; action: string; section: string; run: () => Promise<{ saved: boolean; message?: string }> } | null>(null);
	let dialog = $state<HTMLDialogElement>();
	let loading = false;
	let copyTimer: ReturnType<typeof setTimeout> | undefined;

	export async function refresh() {
		if (loading) return;
		loading = true;
		try {
			const response = await fetch(url, { headers: { accept: 'application/json' }, credentials: 'same-origin' });
			if (response.ok) activity = (await response.json()) as SettingsImportActivity;
		} catch {
			// keep the last good data
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		const timer = setInterval(() => {
			if (document.visibilityState === 'visible') void refresh();
		}, 5000);
		const visible = () => {
			if (document.visibilityState === 'visible') void refresh();
		};
		document.addEventListener('visibilitychange', visible);
		return () => {
			clearInterval(timer);
			document.removeEventListener('visibilitychange', visible);
			clearTimeout(copyTimer);
		};
	});

	async function act(section: string, send: () => Promise<{ saved: boolean; message?: string }>) {
		busy = true;
		notice = null;
		try {
			const answer = await send();
			notice = { section, text: answer.saved ? answer.message || st.saved : (answer.message ?? st.failed), failed: !answer.saved };
			if (answer.saved) await refresh();
		} catch {
			notice = { section, text: st.failed, failed: true };
		} finally {
			busy = false;
		}
	}

	function ask(next: NonNullable<typeof pending>) {
		pending = next;
		dialog?.showModal();
	}

	async function confirmed(event: SubmitEvent) {
		event.preventDefault();
		const action = pending;
		dialog?.close();
		if (action) await act(action.section, action.run);
	}

	function toggle(key: string) {
		open[key] = !open[key];
	}

	async function copy(key: string, text: string) {
		try {
			await navigator.clipboard.writeText(text);
			copied = key;
			clearTimeout(copyTimer);
			copyTimer = setTimeout(() => (copied = ''), 2000);
		} catch {
			// clipboard not available
		}
	}

	function badge(status: string, errors: string): string {
		if (status === 'SUCCESS') return errors ? 'Finished' : 'Success';
		if (status === 'STARTED') return 'Started';
		if (status === 'FAILURE') return 'Failed';
		if (status === 'REVOKED') return 'Cancelled';
		return 'Pending';
	}

	function runBadge(status: string): string {
		if (status === 'completed') return 'Completed';
		if (status === 'running') return 'Running';
		if (status === 'failed') return 'Failed';
		return 'Cancelled';
	}

	function resultKey(result: SettingsImportActivity['results'][number]): string {
		return `result:${result.source.key}:${result.date}:${result.summary}`;
	}

	function scheduleStamp(label: string, iso: string | null): string {
		return `${label}: ${when(iso) || '—'}`;
	}
</script>

{#snippet status(section: string)}
	{#if notice?.section === section}<p class={['ct-settings-status', notice.failed && 'is-error']} role="status">{notice.text}</p>{/if}
{/snippet}

{#snippet logo(source: { name: string; logo: string })}
	{#if source.logo}<img src={source.logo} alt="" class="ct-import-row-logo" />{:else}<FileUp class="size-5" aria-hidden="true" />{/if}
{/snippet}

<section class="ct-settings-section">
	<div>
		<h2>Active Periodic Imports</h2>
		<p class="ct-settings-note">Automated imports that run on a schedule. These will continue to sync your media until disabled.</p>
	</div>
	{#if activity.schedules.length}
		<ul class="ct-settings-rows">
			{#each activity.schedules as schedule (schedule.task_name)}
				<li class="ct-settings-row ct-import-activity-row">
					{@render logo(schedule.source)}
					<span>
						{schedule.source.name}
						<small>{schedule.schedule}</small>
						{#if schedule.username}<small>Username: {schedule.username}</small>{/if}
						<small>Mode: {schedule.mode}</small>
						<small>{scheduleStamp('Last Import', schedule.last_run)}</small>
						<small>{scheduleStamp('Next Import', schedule.next_run)}</small>
					</span>
					<button
						type="button"
						class="is-icon"
						aria-label="Delete schedule"
						disabled={busy}
						onclick={() => act('schedules', () => postForm(activity.delete_schedule_url, { task_name: schedule.task_name }))}
						><Trash2 class="size-4" aria-hidden="true" /></button
					>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="ct-settings-note"><strong>No periodic imports configured</strong><br />Enable a recurring import or Plex watchlist sync to see it here</p>
	{/if}
	{@render status('schedules')}
</section>

<section class="ct-settings-section">
	<div>
		<h2>Import History</h2>
		<p class="ct-settings-note">Showing import activity from the last 7 days.</p>
	</div>
	{#if activity.results.length}
		<ul class="ct-settings-rows">
			{#each activity.results as result (resultKey(result))}
				{@const key = resultKey(result)}
				<li class="ct-settings-row ct-import-activity-row">
					{@render logo(result.source)}
					<span>
						<span class="ct-import-line">
							<span class="ct-settings-badge">{badge(result.status, result.errors)}</span>
							{result.source.name}
						</span>
						<small>{when(result.date)}</small>
						{#if result.summary}<small>{result.summary}</small>{/if}
						{#if result.status === 'STARTED' && result.progress_current}
							{#if result.progress_total}
								<small>{result.progress_label || 'Importing'} {result.progress_current} / {result.progress_total}</small>
								<span
									class="ct-import-bar"
									role="progressbar"
									aria-label={result.progress_label || 'Importing'}
									aria-valuemin="0"
									aria-valuemax="100"
									aria-valuenow={Math.round(result.progress_percent)}
									><span style:width="{Math.max(0, Math.min(100, result.progress_percent))}%"></span></span
								>
							{:else}
								<small>{result.progress_label || 'Gathering items…'} ({result.progress_current} found)</small>
							{/if}
						{/if}
						{#if result.errors && (result.status === 'SUCCESS' || result.status === 'FAILURE')}
							<span class="ct-import-line">
								<button type="button" class="ct-settings-link" aria-expanded={!!open[key]} onclick={() => toggle(key)}>
									{#if result.status === 'SUCCESS'}{open[key] ? 'Hide failed items' : 'Show failed items'}{:else}{open[key] ? 'Hide traceback' : 'Show traceback'}{/if}
								</button>
								{#if result.status === 'FAILURE' && open[key]}
									<button type="button" class="ct-settings-button" onclick={() => copy(key, result.errors)}>{copied === key ? 'Copied!' : 'Copy'}</button>
								{/if}
							</span>
							{#if open[key]}
								{#if result.status === 'SUCCESS'}
									<ul class="ct-import-errors">
										{#each result.errors.split('\n').filter((line) => line.trim()) as line, index (index)}<li>{line}</li>{/each}
									</ul>
								{:else}
									<pre class="ct-import-trace">{result.errors}</pre>
								{/if}
							{/if}
						{/if}
					</span>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="ct-settings-note"><strong>No imports in the last 7 days</strong><br />Import your media from any source to see the history here</p>
	{/if}
</section>

{#if activity.runs.length}
	<section class="ct-settings-section">
		<h2>Recent Import Runs</h2>
		<ul class="ct-settings-rows">
			{#each activity.runs as run (run.id)}
				<li class="ct-settings-row ct-import-activity-row">
					{@render logo(run.source)}
					<span>
						<span class="ct-import-line"><span class="ct-settings-badge">{runBadge(run.status)}</span>{run.source.name}</span>
						<small>{when(run.started_at)}</small>
						<small
							>Created: {run.created} · Updated: {run.updated} · Skipped: {run.skipped} · Failed: {run.failed}{run.remaining !== null
								? ` · Remaining: ${run.remaining}`
								: ''}</small
						>
					</span>
					{#if run.status === 'running'}
						<button
							type="button"
							class="ct-settings-button"
							disabled={busy}
							onclick={() => ask({ title: 'Cancel this import?', lines: [], action: 'Cancel import', section: 'runs', run: () => postForm(run.cancel_url) })}
							>Cancel import</button
						>
					{:else}
						<button
							type="button"
							class="ct-settings-button"
							disabled={busy}
							onclick={() =>
								ask({
									title: 'Undo this import?',
									lines: ['Remove the items this import created? This cannot be undone.'],
									action: 'Undo this import',
									section: 'runs',
									run: () => postForm(run.rollback_url)
								})}>Undo this import</button
						>
					{/if}
				</li>
			{/each}
		</ul>
		{@render status('runs')}
	</section>
{/if}

{#if activity.source_media.length}
	<section class="ct-settings-section">
		<div>
			<h2>Imported Media by Source</h2>
			<p class="ct-settings-note">Permanently delete everything of a media type imported from one source, e.g. before re-importing from a different source.</p>
		</div>
		<ul class="ct-settings-rows">
			{#each activity.source_media as entry (`${entry.source.key}:${entry.media_type}`)}
				<li class="ct-settings-row ct-import-activity-row">
					{@render logo(entry.source)}
					<span>
						{entry.source.name}
						<small>{entry.media_type} · {entry.count} {entry.count === 1 ? 'item' : 'items'}</small>
					</span>
					<button
						type="button"
						class="ct-settings-button is-danger"
						disabled={busy}
						onclick={() =>
							ask({
								title: 'Delete all?',
								lines: [
									`Permanently delete all ${entry.media_type} items imported from this source?${entry.media_type === 'music' ? ' Artists and albums left with no tracks are removed from your library too.' : ''} This cannot be undone.`
								],
								action: 'Delete all',
								section: 'media',
								run: () => postForm(entry.delete_url)
							})}>Delete all</button
					>
				</li>
			{/each}
		</ul>
		{@render status('media')}
	</section>
{/if}

<dialog class="ct-settings-dialog" bind:this={dialog} aria-labelledby="ct-import-confirm-title" onclose={() => (pending = null)}>
	{#if pending}
		<form onsubmit={confirmed}>
			<h2 id="ct-import-confirm-title">{pending.title}</h2>
			{#each pending.lines as line (line)}<p class="ct-settings-note">{line}</p>{/each}
			<div class="ct-settings-actions">
				<button type="button" class="ct-settings-button" onclick={() => dialog?.close()}>Keep</button>
				<button type="submit" class="ct-settings-button is-danger">{pending.action}</button>
			</div>
		</form>
	{/if}
</dialog>
