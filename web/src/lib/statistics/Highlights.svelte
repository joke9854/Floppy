<script lang="ts">
	import type { components } from '#lib/api/client.ts';
	import { detailLink } from '#lib/details/link.ts';
	import { st } from './strings.ts';

	type Highlights = components['schemas']['StatisticsScreenHighlights'];
	type Play = components['schemas']['StatisticsScreenPlay'];

	/**
	 * The highlight cards (highlight_set.html): First Play, Last Play and
	 * Today in (your) history, 3:2 images. Phones swipe them with dots.
	 */
	let { highlights }: { highlights: Highlights } = $props();

	const cards = $derived<{ label: string; play: Play | null }[]>([
		{ label: st.firstPlay, play: highlights.first_play ?? null },
		{ label: st.lastPlay, play: highlights.last_play ?? null },
		{ label: highlights.today_label, play: highlights.today ?? null }
	]);

	let track = $state<HTMLDivElement>();
	let current = $state(0);

	function sync() {
		if (!track?.firstElementChild) return;
		const card = (track.firstElementChild as HTMLElement).offsetWidth || 1;
		current = Math.min(2, Math.round(track.scrollLeft / card));
	}
</script>

<div class="ct-highlights">
	<div class="ct-highlights__track" bind:this={track} onscroll={sync}>
		{#each cards as card, index (index)}
			{#if card.play}
				<a {...detailLink(card.play.href)} class="ct-highlight">
					{#if card.play.image}
						<img src={card.play.image} alt={card.play.title} loading="lazy" decoding="async" />
					{:else}
						<span class="ct-highlight__blank"></span>
					{/if}
					<span class="ct-highlight__body">
						<span class="ct-highlight__label">{card.label}</span>
						<span class="ct-highlight__title">{card.play.title}</span>
						<span class="ct-highlight__caption">{card.play.caption}</span>
					</span>
				</a>
			{:else}
				<div class="ct-highlight">
					<span class="ct-highlight__blank"></span>
					<span class="ct-highlight__body">
						<span class="ct-highlight__label">{card.label}</span>
						<span class="ct-highlight__title is-empty">--</span>
					</span>
				</div>
			{/if}
		{/each}
	</div>
	<div class="ct-highlights__dots">
		{#each cards as _card, index (index)}
			<button
				type="button"
				aria-label={st.showHighlight(index + 1)}
				aria-current={current === index ? 'true' : undefined}
				onclick={() => {
					const card = track?.children[index] as HTMLElement | undefined;
					track?.scrollTo({ left: card?.offsetLeft ?? 0, behavior: 'smooth' });
				}}
			></button>
		{/each}
	</div>
</div>
