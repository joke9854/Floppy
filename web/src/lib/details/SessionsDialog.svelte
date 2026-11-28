<script lang="ts">
	import Pencil from '@lucide/svelte/icons/pencil';
	import Star from '@lucide/svelte/icons/star';
	import type { components } from '#lib/api/client.ts';
	import type { TrackTarget } from '#lib/track/open.svelte.ts';
	import Dialog from '#lib/ui/Dialog.svelte';
	import { ls } from './lazyStrings.ts';

	type Sessions = components['schemas']['SessionsScreen'];
	type Entry = Sessions['days'][number]['entries'][number];

	/**
	 * The activity sessions dialog (P4-L3b), as the Django page's activity
	 * history for one title: the At a glance numbers, then the days newest
	 * first, each row's time, title, what happened and Edit tracking (the web
	 * track dialog for that play). `query` is the `sessions_query` the page's
	 * activity line carries.
	 */
	let {
		query,
		open = $bindable(true),
		onedit
	}: {
		query: string;
		open?: boolean;
		onedit: (target: TrackTarget) => void;
	} = $props();

	let sessions = $state.raw<Sessions | null>(null);
	let failed = $state(false);

	$effect(() => {
		let live = true;
		fetch(`/api/v1/history/sessions/?${query}`, { credentials: 'same-origin' })
			.then(async (response) => {
				if (!response.ok) throw new Error(String(response.status));
				const body = (await response.json()) as Sessions;
				if (live) sessions = body;
			})
			.catch(() => {
				if (live) failed = true;
			});
		return () => {
			live = false;
		};
	});

	function edit(entry: Entry) {
		const target = entry.track;
		if (!target) return;
		onedit({
			mediaType: target.media_type,
			source: target.source,
			mediaId: target.media_id,
			season: target.season_number,
			episode: target.episode_number,
			instanceId: target.instance_id
		});
	}
</script>

<Dialog bind:open title={ls.activityHistory}>
	<div class="ct-sessions">
		{#if failed}
			<p role="alert">{ls.sessionsLoadFailed}</p>
		{:else if !sessions}
			<p aria-busy="true">{ls.loading}</p>
		{:else}
			{#if sessions.stats.length}
				<dl class="ct-sessions__stats" aria-label={ls.atAGlance}>
					{#each sessions.stats as stat (stat.label)}
						<div><dt>{stat.label}</dt><dd>{stat.value}</dd></div>
					{/each}
				</dl>
			{/if}
			{#each sessions.days as day (day.key)}
				<section class="ct-sessions__day">
					<h3>
						<span>{day.weekday} {day.date}</span>
						<small>{day.meta}</small>
					</h3>
					<ul>
						{#each day.entries as entry (entry.key)}
							<li>
								<span class="ct-sessions__time" title={entry.time_title}>{entry.time}</span>
								<span class="ct-sessions__text">
									<span class="ct-sessions__title">{entry.title}</span>
									<span class="ct-sessions__sub">
										{#if entry.code}<b>{entry.code}</b>{/if}
										{entry.subtitle}
										{#if entry.runtime}· {entry.runtime}{/if}
										{#if entry.score}· <Star class="inline size-3" aria-hidden="true" />{entry.score}{/if}
									</span>
								</span>
								{#if entry.track}
									<button
										type="button"
										class="ct-sessions__edit"
										title={ls.editTracking}
										aria-label={ls.editTracking}
										onclick={() => edit(entry)}
									>
										<Pencil class="size-4" aria-hidden="true" />
									</button>
								{/if}
							</li>
						{/each}
					</ul>
				</section>
			{:else}
				<p>{ls.sessionsEmpty}</p>
			{/each}
			{#if sessions.capped}<p class="ct-sessions__cap">{ls.sessionsCapped(sessions.max_days)}</p>{/if}
		{/if}
	</div>
</Dialog>

<style>
	.ct-sessions {
		display: flex;
		flex-direction: column;
		gap: 16px;
		font-size: 14px;
	}
	.ct-sessions__stats {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 8px 12px;
		margin: 0;
	}
	.ct-sessions__stats dt {
		color: var(--color-muted);
		font-size: 11px;
		letter-spacing: 0.04em;
		text-transform: uppercase;
	}
	.ct-sessions__stats dd {
		margin: 0;
		font-weight: 600;
	}
	.ct-sessions__day h3 {
		display: flex;
		justify-content: space-between;
		gap: 8px;
		padding-bottom: 6px;
		border-bottom: 1px solid rgb(255 255 255 / 10%);
		font-weight: 600;
	}
	.ct-sessions__day small {
		color: var(--color-muted);
		font-weight: 400;
	}
	.ct-sessions__day ul {
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.ct-sessions__day li {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 8px 0;
	}
	.ct-sessions__time {
		flex: none;
		width: 64px;
		color: var(--color-muted);
		font-variant-numeric: tabular-nums;
	}
	.ct-sessions__text {
		display: flex;
		flex: 1;
		flex-direction: column;
		min-width: 0;
	}
	.ct-sessions__title {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.ct-sessions__sub {
		color: var(--color-muted);
		font-size: 12px;
	}
	.ct-sessions__edit {
		display: inline-grid;
		flex: none;
		width: 34px;
		height: 34px;
		place-items: center;
		border-radius: 999px;
		color: var(--color-muted);
		cursor: pointer;
	}
	.ct-sessions__edit:hover {
		background-color: rgb(255 255 255 / 8%);
		color: var(--color-text);
	}
	.ct-sessions__cap {
		color: var(--color-muted);
		font-size: 12px;
		text-align: center;
	}
</style>
