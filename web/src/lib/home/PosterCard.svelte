<script lang="ts">
	import { detailLink } from '#lib/details/link.ts';
	import type { components } from '#lib/api/client.ts';
	import { fadeIn } from '#lib/media/fade.ts';
	import StatusChip from './StatusChip.svelte';

	type Card = components['schemas']['HomeRecentCard'];

	/** A Recently Watched poster card: crisp poster, title, when it was watched. */
	let { card }: { card: Card } = $props();
</script>

<article class="ct-poster-card" data-media-type={card.media_type}>
	<a {...detailLink(card.url)} class="ct-poster-link">
		<span class="ct-poster-frame">
			<img
				alt={card.title}
				class="ct-poster-img ct-fade-img"
				src={card.poster}
				srcset={card.poster_srcset || undefined}
				sizes={card.poster_srcset ? '176px' : undefined}
				width="342"
				height="513"
				loading="lazy"
				decoding="async"
				use:fadeIn
			/>
			{#if card.progress}
				<span class={['ct-progress-line', card.progress.paused && 'is-paused']} aria-hidden="true">
					<span style:width="{card.progress.percent}%"></span>
				</span>
			{/if}
		</span>
		<span class="ct-poster-title">{card.title}</span>
		<span class="ct-poster-sub">{card.subtitle}</span>
	</a>
	{#if card.status}
		<StatusChip status={card.status} />
	{/if}
</article>
