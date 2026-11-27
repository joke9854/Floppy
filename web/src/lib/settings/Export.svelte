<script lang="ts">
	import Trash from '@lucide/svelte/icons/trash-2';
	import { invalidate } from '$app/navigation';
	import { djangoForm } from '#lib/csrf.ts';
	import { st } from './strings.ts';
	import { downloadName, readAnswer, when, type SettingsScreen } from './types.ts';

	/**
	 * Export (export_data.html): the CSV export, once or on a schedule (the
	 * form answers with the file), where scheduled exports and database
	 * snapshots land, the Letterboxd export, schedules and recent runs.
	 */
	let { screen }: { screen: SettingsScreen } = $props();
	const exportPage = $derived(screen.export!);

	const local = {
		title: 'Export Data',
		intro:
			'Export your media, ratings, and lists as CSV, or create a recurring export schedule and download the initial CSV immediately. This is a data export, not a database backup — it does not restore your account, integrations, or preferences.',
		savesTo: 'Scheduled exports save to:',
		files: (count: number) => `${count} ${count === 1 ? 'file' : 'files'} there now.`,
		notMounted: 'Not mounted to the host — add ./backups:/floppy/backups to your compose file or they are lost with the container.',
		snapshotTo: 'For disaster recovery, Floppy separately writes a verified database snapshot to:',
		snapshots: (count: number) =>
			`${count} ${count === 1 ? 'snapshot' : 'snapshots'} there now. This is the file to restore from if the database itself is damaged.`,
		snapshotOff: 'Disabled — set DB_SNAPSHOT_ENABLED=true to turn database snapshots on.',
		frequency: 'Export Frequency',
		time: 'Export Time (server time)',
		content: 'Export Content',
		contentNote:
			'Keep at least one media type, Custom Lists, or Collection enabled. Keep every media type and both additional content options enabled for a full export.',
		lists: 'Custom Lists',
		collection: 'Collection',
		exportOnce: 'Export as CSV',
		exportSchedule: 'Export as CSV and Save Schedule',
		needOne: 'Select at least one media type, Custom Lists, or Collection to export.',
		downloaded: 'Export downloaded.',
		scheduled: 'Export downloaded and the schedule saved.',
		others: 'Export for Other Websites',
		othersNote: 'Unlike the export above, these exports are trimmed and reshaped to match what a specific external site expects.',
		letterboxd: "Watched movies with ratings and diary dates, ready for Letterboxd's CSV import.",
		schedules: 'Active Scheduled Exports',
		noSchedules: 'No scheduled exports configured',
		noSchedulesNote: 'Set up a schedule above to automatically export your data',
		allTypes: 'Media Types: All',
		noneTypes: 'Media Types: None (Lists/Collection only)',
		included: 'Included',
		excluded: 'Excluded',
		lastBackup: 'Last Backup:',
		nextBackup: 'Next Backup:',
		never: 'Never',
		deleteSchedule: 'Delete schedule',
		history: 'Export History',
		historyNote: 'Showing export activity from the last 7 days.',
		noHistory: 'No exports in the last 7 days',
		csvExport: 'CSV Export'
	};
	const frequencies = [
		{ value: 'once', label: 'Export Once' },
		{ value: 'daily', label: 'Every Day' },
		{ value: '2days', label: 'Every 2 Days' },
		{ value: 'weekly', label: 'Weekly' }
	];
	const statusLabel: Record<string, string> = { SUCCESS: 'Success', STARTED: 'Started', FAILURE: 'Failed', PENDING: 'Pending' };

	let frequency = $state('once');
	let time = $state('03:00');
	// svelte-ignore state_referenced_locally
	let types = $state<string[]>(screen.export!.media_types.map((type) => type.value));
	let includeLists = $state(true);
	let includeCollection = $state(true);
	let busy = $state('');
	let notice = $state<{ key: string; text: string; failed: boolean } | null>(null);

	const empty = $derived(!types.length && !includeLists && !includeCollection);
	const labelOf = (value: string) => exportPage.media_types.find((type) => type.value === value)?.label ?? value;

	async function runExport(event: SubmitEvent) {
		event.preventDefault();
		if (empty) {
			notice = { key: 'export', text: local.needOne, failed: true };
			return;
		}
		busy = 'export';
		notice = null;
		try {
			const fields: Record<string, string | string[]> = { frequency, time, media_types: types };
			if (includeLists) fields.include_lists = 'on';
			if (includeCollection) fields.include_collection = 'on';
			const response = await djangoForm(exportPage.urls.export, fields, { json: true });
			if (!response.ok || !(response.headers.get('content-type') ?? '').includes('text/csv')) {
				const answer = await readAnswer(response);
				notice = { key: 'export', text: answer.message || st.failed, failed: true };
				return;
			}
			const url = URL.createObjectURL(await response.blob());
			const link = Object.assign(document.createElement('a'), { href: url, download: downloadName(response, 'floppy.csv') });
			link.click();
			setTimeout(() => URL.revokeObjectURL(url), 1000);
			notice = { key: 'export', text: frequency === 'once' ? local.downloaded : local.scheduled, failed: false };
			if (frequency !== 'once') await invalidate('floppy:settings');
		} catch {
			notice = { key: 'export', text: st.failed, failed: true };
		} finally {
			busy = '';
		}
	}

	async function deleteSchedule(taskName: string) {
		busy = taskName;
		notice = null;
		try {
			const answer = await readAnswer(await djangoForm(exportPage.urls.delete_schedule, { task_name: taskName }, { json: true }));
			notice = { key: 'schedules', text: answer.saved ? answer.message || st.saved : (answer.message ?? st.failed), failed: !answer.saved };
			if (answer.saved) await invalidate('floppy:settings');
		} catch {
			notice = { key: 'schedules', text: st.failed, failed: true };
		} finally {
			busy = '';
		}
	}
</script>

{#snippet status(key: string)}
	{#if notice?.key === key}<span class={['ct-settings-status', notice.failed && 'is-error']} role="status">{notice.text}</span>{/if}
{/snippet}

<form class="ct-settings-section" onsubmit={runExport}>
	<div>
		<h2>{local.title}</h2>
		<p class="ct-settings-note">{local.intro}</p>
	</div>
	<p class="ct-settings-note">
		{local.savesTo} <code class="ct-settings-code">{exportPage.backup.path}</code>
		{exportPage.backup.host_reachable ? local.files(exportPage.backup.file_count) : local.notMounted}
	</p>
	<p class="ct-settings-note">
		{#if exportPage.snapshot.enabled}
			{local.snapshotTo} <code class="ct-settings-code">{exportPage.snapshot.path}</code>
			{exportPage.snapshot.host_reachable ? local.snapshots(exportPage.snapshot.file_count) : local.notMounted}
		{:else}
			{local.snapshotOff}
		{/if}
	</p>
	<div class="ct-settings-actions" style="justify-content: flex-start">
		<label class="ct-settings-field">
			{local.frequency}
			<select bind:value={frequency}>
				{#each frequencies as option (option.value)}<option value={option.value}>{option.label}</option>{/each}
			</select>
		</label>
		{#if frequency !== 'once'}
			<label class="ct-settings-field">{local.time}<input type="time" bind:value={time} required /></label>
		{/if}
	</div>
	<h3>{local.content}</h3>
	<p class="ct-settings-note">{local.contentNote}</p>
	<div class="ct-settings-options">
		{#each exportPage.media_types as type (type.value)}
			<label class="ct-settings-check"><input type="checkbox" value={type.value} bind:group={types} /><span>{type.label}</span></label>
		{/each}
		<label class="ct-settings-check"><input type="checkbox" bind:checked={includeLists} /><span>{local.lists}</span></label>
		<label class="ct-settings-check"><input type="checkbox" bind:checked={includeCollection} /><span>{local.collection}</span></label>
	</div>
	<div class="ct-settings-actions">
		{@render status('export')}
		<button type="submit" class="ct-settings-button is-primary" disabled={busy !== '' || exportPage.is_demo || empty}
			>{frequency === 'once' ? local.exportOnce : local.exportSchedule}</button
		>
	</div>
</form>

<section class="ct-settings-section">
	<div>
		<h2>{local.others}</h2>
		<p class="ct-settings-note">{local.othersNote}</p>
	</div>
	<div class="ct-settings-row">
		<span>Letterboxd<small>{local.letterboxd}</small></span>
		<a class="ct-settings-button" href={exportPage.urls.letterboxd} download>{st.download}</a>
	</div>
</section>

<section class="ct-settings-section">
	<h2>{local.schedules}</h2>
	{@render status('schedules')}
	{#if exportPage.schedules.length}
		<ul class="ct-settings-rows">
			{#each exportPage.schedules as schedule (schedule.task_name)}
				<li class="ct-settings-row">
					<span>
						{local.csvExport} · {schedule.schedule}
						<small>
							{schedule.media_types === null
								? local.allTypes
								: schedule.media_types.length
									? `Media Types: ${schedule.media_types.map(labelOf).join(', ')}`
									: local.noneTypes}
						</small>
						<small
							>{local.lists}: {schedule.include_lists ? local.included : local.excluded} · {local.collection}: {schedule.include_collection
								? local.included
								: local.excluded}</small
						>
						<small>{local.lastBackup} {when(schedule.last_run) || local.never} · {local.nextBackup} {when(schedule.next_run)}</small>
					</span>
					<button
						type="button"
						class="is-icon"
						aria-label={local.deleteSchedule}
						disabled={busy !== ''}
						onclick={() => deleteSchedule(schedule.task_name)}><Trash class="size-4" aria-hidden="true" /></button
					>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="ct-settings-note">{local.noSchedules}. {local.noSchedulesNote}.</p>
	{/if}
</section>

<section class="ct-settings-section">
	<div>
		<h2>{local.history}</h2>
		<p class="ct-settings-note">{local.historyNote}</p>
	</div>
	{#if exportPage.results.length}
		<div class="ct-settings-rows">
			{#each exportPage.results as result, index (index)}
				<details class="ct-settings-more">
					<summary>
						<span>{local.csvExport}<small>{when(result.date)}</small></span>
						<span class={['ct-settings-badge', result.status === 'SUCCESS' && 'is-on']}>{statusLabel[result.status] ?? result.status}</span>
					</summary>
					<div>
						{#if result.summary}<p class="ct-settings-note">{result.summary}</p>{/if}
						{#if result.errors}<pre>{result.errors}</pre>{/if}
					</div>
				</details>
			{/each}
		</div>
	{:else}
		<p class="ct-settings-note">{local.noHistory}</p>
	{/if}
</section>
