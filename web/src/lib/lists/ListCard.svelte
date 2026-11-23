<script lang="ts">
	import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal';
	import { ls } from './strings.ts';
	import type { ListCard } from './types.ts';

	/**
	 * A list card (ct_list_card.html): a strip of the first four posters, the
	 * name (the list's page), "N items · Shared · N% completed", and Edit for
	 * lists the user can edit. The list's page is still Django's (P4-I2).
	 */
	let { card, onedit }: { card: ListCard; onedit: (card: ListCard) => void } = $props();
</script>

<article class="ct-list-card">
	<a href={card.href} class="ct-list-card__cover" tabindex="-1" aria-hidden="true" data-sveltekit-reload>
		{#each card.covers as poster, index (index)}
			<img src={poster} alt="" loading="lazy" decoding="async" />
		{:else}
			<span class="ct-list-card__blank"></span>
		{/each}
	</a>
	{#if card.can_edit}
		<button type="button" class="ct-list-card__edit" title={ls.editList} aria-label={ls.editNamed(card.name)} onclick={() => onedit(card)}>
			<SlidersHorizontal class="size-4" aria-hidden="true" />
		</button>
	{/if}
	<a href={card.href} class="ct-list-card__title" data-sveltekit-reload>
		{card.name}
	</a>
	<p class="ct-list-card__meta">{card.meta}</p>
	{#if card.watched}<p class="ct-list-card__meta">{card.watched}</p>{/if}
</article>
