<script lang="ts">
	import Repeat from '@lucide/svelte/icons/repeat';
	import Star from '@lucide/svelte/icons/star';
	import { detailLink } from '#lib/details/link.ts';
	import { t } from '#lib/strings.ts';
	import type { LibraryCard, LibraryScreen } from './query.ts';

	/**
	 * The Library's table layout (B3), as the Django table draws it: the
	 * user's columns in their order, a small poster, the title with its
	 * repeat count, then each cell's value and its small note (Latest,
	 * Total, Earliest, Remaining). Genres filter the list, as their links do
	 * on the page.
	 */
	let {
		columns,
		cards,
		ongenre,
		selecting = false,
		selected = [],
		ontoggle
	}: {
		columns: LibraryScreen['columns'];
		cards: LibraryCard[];
		ongenre: (genre: string) => void;
		selecting?: boolean;
		selected?: number[];
		ontoggle?: (key: number) => void;
	} = $props();
</script>

<div class="ct-library-table-wrap">
	<table class="ct-library-table">
		<thead>
			<tr>
				{#if selecting}<th class="is-select"><span class="sr-only">{t.selected}</span></th>{/if}
				{#each columns as column (column.key)}
					<th scope="col" class={[`is-${column.key}`, column.align === 'center' && 'is-center']}
						>{column.label}</th
					>
				{/each}
			</tr>
		</thead>
		<tbody>
			{#each cards as card (card.key)}
				{@const cells = new Map(card.cells.map((cell) => [cell.key, cell]))}
				<tr class={[selected.includes(card.key) && 'is-selected']}>
					{#if selecting}
						<td class="is-select">
							<input
								type="checkbox"
								aria-label={card.title}
								checked={selected.includes(card.key)}
								onchange={() => ontoggle?.(card.key)}
							/>
						</td>
					{/if}
					{#each columns as column (column.key)}
						{@const cell = cells.get(column.key)}
						<td class={[`is-${column.key}`, column.align === 'center' && 'is-center']}>
							{#if column.role === 'image'}
								<img alt="" src={card.poster} width="40" height="60" loading="lazy" decoding="async" />
							{:else if column.role === 'title'}
								<span class="ct-table-title">
									<a {...detailLink(card.url)}>{card.title}</a>
									{#if card.repeats}
										<span class="ct-table-repeats" title="{card.repeats}×">
											<Repeat class="size-3.5" aria-hidden="true" />{card.repeats}
										</span>
									{/if}
								</span>
							{:else if cell && column.key === 'genres'}
								{#if cell.items.length}
									<span class="ct-table-genres">
										{#each cell.items as genre (genre)}
											<button type="button" onclick={() => ongenre(genre)}>{genre}</button>
										{/each}
									</span>
								{:else}<span class="ct-table-empty">-</span>{/if}
							{:else if cell && column.key === 'tags'}
								{#if cell.items.length}
									<span class="ct-table-clip" title={cell.items.join(', ')}>{cell.items.join(', ')}</span>
								{:else}<span class="ct-table-empty">-</span>{/if}
							{:else if cell && column.role === 'score'}
								<span class={['ct-table-score', !cell.text && 'is-empty']}>
									<Star class="size-4" aria-hidden="true" />{cell.text ?? ''}
								</span>
								{#if cell.note}<span class="ct-table-note">{cell.note}</span>{/if}
							{:else if cell?.text}
								<span class="ct-table-clip" title={cell.text}>{cell.text}</span>
								{#if cell.note}<span class="ct-table-note">{cell.note}</span>{/if}
							{:else}
								<span class="ct-table-empty">-</span>
							{/if}
						</td>
					{/each}
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<style>
	.ct-library-table-wrap {
		overflow-x: auto;
		border-radius: var(--radius-ct-md, 16px);
		background-color: var(--color-surface);
	}

	.ct-library-table {
		width: 100%;
		border-collapse: collapse;
		font-size: 14px;
	}

	th {
		padding: 12px 10px;
		color: var(--color-muted);
		font-size: 12px;
		font-weight: 600;
		text-align: left;
		white-space: nowrap;
	}

	td {
		padding: 8px 10px;
		border-top: 1px solid rgb(255 255 255 / 6%);
		color: var(--color-text-secondary);
		vertical-align: middle;
	}

	tbody tr:hover td {
		background-color: rgb(255 255 255 / 3%);
	}

	.is-select {
		width: 40px;
		text-align: center;
	}

	.is-select input {
		accent-color: var(--color-accent);
	}

	tr.is-selected td {
		background-color: rgb(255 255 255 / 5%);
	}

	.is-center {
		text-align: center;
	}

	td.is-image {
		width: 56px;
		padding-block: 6px;
	}

	td.is-image img {
		width: 40px;
		min-width: 40px;
		max-width: none;
		height: 60px;
		border-radius: 6px;
		object-fit: cover;
	}

	td.is-title {
		min-width: 200px;
		color: var(--color-text);
		font-weight: 600;
	}

	.ct-table-title {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
	}

	.ct-table-title a {
		display: -webkit-box;
		overflow: hidden;
		-webkit-box-orient: vertical;
		-webkit-line-clamp: 1;
		line-clamp: 1;
	}

	.ct-table-title a:hover {
		color: var(--color-accent);
	}

	.ct-table-repeats {
		display: inline-flex;
		flex: none;
		align-items: center;
		gap: 4px;
		color: var(--color-text-secondary);
		font-size: 13px;
		font-weight: 500;
	}

	.ct-table-clip {
		display: block;
		max-width: 20rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.is-center .ct-table-clip {
		margin-inline: auto;
	}

	.ct-table-note {
		display: block;
		margin-top: 2px;
		color: var(--color-accent);
		font-size: 12px;
	}

	.ct-table-empty {
		color: var(--color-muted);
	}

	.ct-table-score {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		color: var(--color-text);
	}

	.ct-table-score :global(svg) {
		color: rgb(250 204 21);
		fill: currentColor;
	}

	.ct-table-score.is-empty :global(svg) {
		color: var(--color-muted);
	}

	.ct-table-genres {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		min-width: 160px;
	}

	.ct-table-genres button {
		padding: 2px 8px;
		border: 1px solid rgb(255 255 255 / 10%);
		border-radius: 999px;
		background-color: rgb(255 255 255 / 4%);
		color: var(--color-text-secondary);
		font-size: 12px;
		font-weight: 500;
		white-space: nowrap;
		cursor: pointer;
	}

	.ct-table-genres button:hover {
		background-color: rgb(255 255 255 / 10%);
		color: var(--color-text);
	}

	td.is-synopsis .ct-table-clip,
	td.is-notes .ct-table-clip {
		max-width: 18rem;
	}
</style>
