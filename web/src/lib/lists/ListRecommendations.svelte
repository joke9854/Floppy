<script lang="ts">
	import './list-extras.css';
	import './lists.css';
	import { djangoForm } from '#lib/csrf.ts';
	import { detailLink } from '#lib/details/link.ts';
	import Dialog from '#lib/ui/Dialog.svelte';
	import { ld } from './strings.ts';

	/**
	 * A list's recommendations (list_recommendations.html) as a dialog on the
	 * list page: each with who sent it and their note, Approve and add, Deny.
	 * `ondone` reloads the list after a change.
	 */
	let { open = $bindable(false), url, ondone }: { open?: boolean; url: string; ondone: (message: string) => void } = $props();

	type Recommendation = {
		id: number;
		title: string;
		media_type: string;
		href: string;
		image: string;
		recommender: string;
		note: string;
		approve_url: string;
		deny_url: string;
	};
	let rows = $state<Recommendation[] | null>(null);
	let busy = $state<number | null>(null);
	let failed = $state(false);

	async function load() {
		failed = false;
		const response = await fetch(url, { credentials: 'same-origin', headers: { accept: 'application/json' } });
		if (!response.ok) {
			failed = true;
			return;
		}
		rows = ((await response.json()) as { recommendations: Recommendation[] }).recommendations;
	}

	$effect(() => {
		if (open) void load();
	});

	async function act(row: Recommendation, action: string) {
		busy = row.id;
		try {
			const response = await djangoForm(action, {}, { json: true });
			const body = (await response.json().catch(() => ({}))) as { message?: string };
			if (!response.ok) throw new Error(body.message);
			rows = (rows ?? []).filter((entry) => entry.id !== row.id);
			ondone(body.message ?? '');
		} catch {
			failed = true;
		} finally {
			busy = null;
		}
	}
</script>

<Dialog bind:open title={ld.recommendationsTitle} sheet>
	{#if rows === null}
		<p class="ct-list-dialog__note">{failed ? ld.failed : ld.loading}</p>
	{:else if rows.length === 0}
		<div class="ct-list-dialog__empty">
			<h3>{ld.noRecommendations}</h3>
			<p>{ld.noRecommendationsHint}</p>
		</div>
	{:else}
		{#if failed}<p class="ct-list-form__error">{ld.failed}</p>{/if}
		<ul class="ct-list-dialog__rows">
			{#each rows as row (row.id)}
				<li class={[busy === row.id && 'is-busy']}>
					<a {...detailLink(row.href)} class="ct-list-dialog__poster"><img src={row.image} alt="" loading="lazy" /></a>
					<div class="ct-list-dialog__body">
						<a {...detailLink(row.href)} class="ct-list-dialog__title">{row.title}</a>
						<span class="ct-list-dialog__meta">{row.media_type} · {ld.recommendedBy} {row.recommender}</span>
						{#if row.note}<p class="ct-list-dialog__quote">{row.note}</p>{/if}
						<div class="ct-list-form__actions is-start">
							<button type="button" class="ct-lists-button is-primary" disabled={busy !== null} onclick={() => act(row, row.approve_url)}>{ld.approve}</button>
							<button type="button" class="ct-lists-button" disabled={busy !== null} onclick={() => act(row, row.deny_url)}>{ld.deny}</button>
						</div>
					</div>
				</li>
			{/each}
		</ul>
	{/if}
</Dialog>
