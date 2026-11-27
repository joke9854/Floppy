<script lang="ts">
	import { invalidate } from '$app/navigation';
	import { st } from '../strings.ts';
	import { when, type SettingsIntegrations } from '../types.ts';
	import { postForm } from './actions.ts';

	/** Watched-state sync: conflicts and one card per connection (spec 5). */
	let { integrations }: { integrations: SettingsIntegrations } = $props();
	const sync = $derived(integrations.sync);

	const local = {
		title: 'Watched-state sync',
		note: 'Keep completion state in step with your media servers. History imports are configured separately, per connection.',
		conflictNote: 'Both sides changed while they were out of contact. Sync is paused for these items only — everything else keeps flowing.',
		watched: 'Watched',
		unwatched: 'Unwatched',
		empty: 'No connections yet. Connect a media server above and it will appear here.',
		pause: 'Pause',
		resume: 'Resume',
		direction: 'Direction',
		save: 'Save'
	};
	const stateLabel = (value: string) => (value === 'on' ? 'On' : value === 'off' ? 'Off' : value === 'unavailable' ? 'Unavailable' : 'Not supported');

	let busy = $state(false);
	let notice = $state<{ key: string; text: string; failed: boolean } | null>(null);
	let directions = $state<Record<number, string>>({});

	const directionOf = (id: number, current: string) => directions[id] ?? current;

	async function post(key: string, url: string, fields: Record<string, string>) {
		busy = true;
		notice = null;
		try {
			const answer = await postForm(url, fields);
			notice = { key, text: answer.saved ? answer.message || st.saved : (answer.message ?? st.failed), failed: !answer.saved };
			if (answer.saved) await invalidate('floppy:settings');
		} catch {
			notice = { key, text: st.failed, failed: true };
		} finally {
			busy = false;
		}
	}
</script>

{#snippet status(key: string)}
	{#if notice?.key === key}<span class={['ct-settings-status', notice.failed && 'is-error']} role="status">{notice.text}</span>{/if}
{/snippet}

<section class="ct-settings-section">
	<div>
		<h2>{local.title}</h2>
		<p class="ct-settings-note">{local.note}</p>
	</div>

	{#if sync.conflicts.length}
		<div class="ct-settings-section">
			<h3>{sync.conflicts.length} item{sync.conflicts.length === 1 ? ' needs' : 's need'} your decision</h3>
			<p class="ct-settings-note">{local.conflictNote}</p>
			<ul class="ct-settings-rows">
				{#each sync.conflicts as conflict (conflict.id)}
					<li class="ct-settings-row">
						<span>
							{conflict.item}
							<small>{conflict.kind} says {conflict.remote_watched ? 'watched' : 'unwatched'}; Floppy says {conflict.local_watched ? 'watched' : 'unwatched'}.</small>
						</span>
						<button
							type="button"
							class="ct-settings-button"
							disabled={busy}
							onclick={() => post('conflicts', sync.urls.resolve, { conflict_id: String(conflict.id), watched: 'true' })}>{local.watched}</button
						>
						<button
							type="button"
							class="ct-settings-button"
							disabled={busy}
							onclick={() => post('conflicts', sync.urls.resolve, { conflict_id: String(conflict.id), watched: 'false' })}>{local.unwatched}</button
						>
					</li>
				{/each}
			</ul>
			<div class="ct-settings-actions">{@render status('conflicts')}</div>
		</div>
	{/if}

	{#if sync.bindings.length}
		{#each sync.bindings as binding (binding.id)}
			<div class="ct-settings-section">
				<div class="ct-settings-actions is-split">
					<h3>{binding.label}</h3>
					<span class={['ct-settings-badge', binding.active && !binding.kill_switch && 'is-on']}>{binding.badge}</span>
				</div>
				<p class="ct-settings-note">
					{binding.last_reconciled_at ? `Last checked ${when(binding.last_reconciled_at)}` : 'Not checked yet'}{binding.pending_deliveries
						? ` · ${binding.pending_deliveries} pending`
						: ''}{binding.failed_deliveries ? ` · ${binding.failed_deliveries} failed` : ''}{binding.open_conflicts
						? ` · ${binding.open_conflicts} to decide`
						: ''}
				</p>
				{#if binding.last_error_message}<p class="ct-settings-status is-error">{binding.last_error_message}</p>{/if}
				<div class="ct-settings-actions">
					<label class="ct-settings-weeks">
						{local.direction}
						<select
							class="ct-settings-select"
							value={directionOf(binding.id, binding.direction)}
							onchange={(event) => (directions[binding.id] = event.currentTarget.value)}
						>
							{#each sync.direction_choices as choice (choice.value)}<option value={choice.value}>{choice.label}</option>{/each}
						</select>
					</label>
					<button
						type="button"
						class="ct-settings-button is-primary"
						disabled={busy}
						onclick={() => post(`direction-${binding.id}`, sync.urls.direction, { binding_id: String(binding.id), direction: directionOf(binding.id, binding.direction) })}
						>{local.save}</button
					>
					<button
						type="button"
						class="ct-settings-button"
						disabled={busy}
						onclick={() => post(`direction-${binding.id}`, sync.urls.pause, { binding_id: String(binding.id), kill_switch: binding.kill_switch ? 'off' : 'on' })}
						>{binding.kill_switch ? local.resume : local.pause}</button
					>
				</div>
				{@render status(`direction-${binding.id}`)}
				<ul class="ct-settings-rows">
					{#each binding.capabilities as capability (capability.code)}
						<li class={['ct-settings-row', capability.state !== 'on' && 'is-off']}>
							<span class={['ct-settings-badge', capability.state === 'on' && 'is-on']}>{stateLabel(capability.state)}</span>
							<span>{capability.label}{capability.state === 'unavailable' ? ' — not verified for this provider yet' : ''}</span>
						</li>
					{/each}
				</ul>
			</div>
		{/each}
	{:else}
		<p class="ct-settings-note">{local.empty}</p>
	{/if}
</section>
