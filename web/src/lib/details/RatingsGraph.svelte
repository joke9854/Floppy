<script lang="ts">
	import type { components } from '#lib/api/client.ts';
	import Dialog from '#lib/ui/Dialog.svelte';
	import { ls } from './lazyStrings.ts';

	type Graphs = components['schemas']['DetailGraphs'];

	/**
	 * A ratings graph (P4-L3b), as the score chip's Series Graph: the heatmap
	 * of a show's episode ratings, a row per episode and a column per season,
	 * each cell coloured by its score, the votes in its tooltip. Fetched when
	 * opened; the table scrolls sideways on phones.
	 */
	let {
		kind,
		url,
		open = $bindable(true)
	}: {
		kind: 'provider' | 'trakt' | 'imdb';
		/** The page's `details/<type>/<source>/<id>/graphs/` read. */
		url: string;
		open?: boolean;
	} = $props();

	let graph = $state.raw<Graphs[typeof kind] | undefined>(undefined);
	let failed = $state(false);

	$effect(() => {
		let live = true;
		fetch(url, { credentials: 'same-origin' })
			.then(async (response) => {
				if (!response.ok) throw new Error(String(response.status));
				const body = (await response.json()) as Graphs;
				if (live) graph = body[kind];
			})
			.catch(() => {
				if (live) failed = true;
			});
		return () => {
			live = false;
		};
	});

	/** Dark text on the amber cells, as the Django tooltip. */
	const ink = (score: number) => (score >= 6 && score < 8 ? 'rgb(0 0 0 / 80%)' : '#fff');
</script>

<Dialog bind:open title={graph?.title ?? ls.graphKind(kind)}>
	{#if failed}
		<p role="alert">{ls.graphLoadFailed}</p>
	{:else if graph === undefined}
		<p aria-busy="true">{ls.loading}</p>
	{:else if !graph?.rows.length}
		<p>{ls.graphEmpty}</p>
	{:else if graph}
		<div class="ct-graph" tabindex="-1">
			<table>
				<thead>
					<tr>
						<td></td>
						{#each graph.seasons as season (season.label)}<th scope="col">{season.label}</th>{/each}
					</tr>
				</thead>
				<tbody>
					{#each graph.rows as row, index (index)}
						<tr>
							<th scope="row">{row.episode ? `${graph.row_label}${row.episode}` : ''}</th>
							{#each row.cells as cell, c (c)}
								{#if cell.color && cell.score !== null}
									<td
										class="ct-graph__cell"
										title={ls.graphCell(cell.score, cell.votes)}
										style:background-color={cell.color}
										style:color={ink(cell.score)}>{cell.score}</td
									>
								{:else}
									<td class="ct-graph__cell is-empty">—</td>
								{/if}
							{/each}
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		<ul class="ct-graph__legend">
			{#each graph.legend as item (item.label)}
				<li><span style:background-color={item.color}></span>{item.label}</li>
			{/each}
		</ul>
	{/if}
</Dialog>

<style>
	.ct-graph {
		max-height: 55dvh;
		overflow: auto;
	}
	.ct-graph table {
		border-collapse: separate;
		border-spacing: 6px;
	}
	.ct-graph th {
		color: var(--color-muted);
		font-size: 11px;
		font-weight: 600;
		text-align: center;
	}
	.ct-graph tbody th {
		padding-right: 4px;
		text-align: right;
		font-weight: 400;
	}
	.ct-graph__cell {
		min-width: 3rem;
		padding: 10px 0;
		border-radius: 8px;
		font-size: 13px;
		font-weight: 700;
		line-height: 1;
		text-align: center;
	}
	.ct-graph__cell.is-empty {
		background-color: rgb(255 255 255 / 5%);
		color: rgb(255 255 255 / 15%);
		font-size: 12px;
		font-weight: 400;
	}
	.ct-graph__legend {
		display: flex;
		flex-wrap: wrap;
		gap: 4px 12px;
		margin: 0;
		padding: 0;
		color: var(--color-muted);
		font-size: 12px;
		list-style: none;
	}
	.ct-graph__legend span {
		display: inline-block;
		width: 10px;
		height: 10px;
		margin-right: 5px;
		border-radius: 3px;
	}
</style>
