<script lang="ts">
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import { dc } from './strings.ts';
	import type { DiscoverScreen } from './types.ts';

	/**
	 * Hidden from Discover (the page's P3b view): what the user hid, with
	 * Unhide (discover_toggle_hidden), and a way back to Discover.
	 */
	let {
		screen,
		busy = null,
		onback,
		onunhide
	}: {
		screen: DiscoverScreen;
		busy?: number | null;
		onback: () => void;
		onunhide: (itemId: number) => void;
	} = $props();
</script>

<div class="ct-hidden-view">
	<button type="button" class="ct-hidden-back" onclick={onback}>
		<ChevronLeft class="size-5" aria-hidden="true" />
		{dc.back}
	</button>
	<h1 class="ct-page-title">{dc.hiddenTitle}</h1>
	<p class="ct-page-sub">{screen.hidden_summary}</p>
	{#if screen.hidden.length}
		<ul class="ct-hidden-list">
			{#each screen.hidden as entry (entry.item_id)}
				<li class="ct-hidden-row">
					{#if entry.poster}
						<img src={entry.poster} alt="" class="ct-hidden-poster" loading="lazy" />
					{:else}
						<span class="ct-hidden-poster" aria-hidden="true"></span>
					{/if}
					<div class="ct-hidden-text">
						<div class="ct-hidden-title">{entry.title}</div>
						<div class="ct-hidden-meta">{entry.meta}</div>
					</div>
					<button
						type="button"
						class="ct-hidden-unhide"
						disabled={busy === entry.item_id}
						onclick={() => onunhide(entry.item_id)}
					>
						{dc.unhide}
					</button>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="ct-hidden-empty">{dc.hiddenEmpty}</p>
	{/if}
</div>
