<script lang="ts">
	import './list-extras.css';
	import './lists.css';
	import { detailLink } from '#lib/details/link.ts';
	import Dialog from '#lib/ui/Dialog.svelte';
	import { ld } from './strings.ts';

	/** A list's Activity History (list_activity.html, the latest 100) as a dialog on the list page. */
	let { open = $bindable(false), url }: { open?: boolean; url: string } = $props();

	type Activity = {
		id: number;
		type: string;
		description: string;
		timestamp: string;
		item: { title: string; href: string; image: string } | null;
	};
	let rows = $state<Activity[] | null>(null);
	let failed = $state(false);

	$effect(() => {
		if (!open) return;
		failed = false;
		fetch(url, { credentials: 'same-origin', headers: { accept: 'application/json' } })
			.then(async (response) => {
				if (!response.ok) throw new Error(String(response.status));
				rows = ((await response.json()) as { activities: Activity[] }).activities;
			})
			.catch(() => (failed = true));
	});
</script>

<Dialog bind:open title={ld.activityTitle} sheet>
	{#if rows === null}
		<p class="ct-list-dialog__note">{failed ? ld.failed : ld.loading}</p>
	{:else if rows.length === 0}
		<div class="ct-list-dialog__empty">
			<h3>{ld.noActivity}</h3>
			<p>{ld.noActivityHint}</p>
		</div>
	{:else}
		<ul class="ct-list-dialog__rows">
			{#each rows as row (row.id)}
				<li>
					{#if row.item}
						<a {...detailLink(row.item.href)} class="ct-list-dialog__poster is-small"><img src={row.item.image} alt="" loading="lazy" /></a>
					{/if}
					<div class="ct-list-dialog__body">
						<span class="ct-list-dialog__text">{row.description}</span>
						<span class="ct-list-dialog__meta">{row.timestamp}</span>
					</div>
				</li>
			{/each}
		</ul>
	{/if}
</Dialog>
