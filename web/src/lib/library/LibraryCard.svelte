<script lang="ts">
	import type { components } from '#lib/api/client.ts';
	import { fadeIn } from '#lib/media/fade.ts';
	import { STATUS_LOOKS } from '#lib/media/status.ts';

	type Card = components['schemas']['LibraryCard'];

	/**
	 * A Library card (A3): the crisp poster with a status badge and an inset
	 * progress line, then the title, the subtitle ("S2 E5 next" or the
	 * status) and the value the list is sorted by.
	 */
	let { card }: { card: Card } = $props();

	const look = $derived(card.status ? STATUS_LOOKS[card.status] : undefined);
</script>

<article class="ct-library-card" data-media-type={card.media_type}>
	<a href={card.url} data-sveltekit-reload>
		<span class="ct-library-poster">
			<img
				alt={card.title}
				class="ct-fade-img"
				src={card.poster}
				srcset={card.poster_srcset || undefined}
				sizes={card.poster_srcset ? '(min-width: 30rem) 170px, 33vw' : undefined}
				width="342"
				height="513"
				loading="lazy"
				decoding="async"
				use:fadeIn
			/>
			{#if card.progress}
				<span class={['ct-library-progress', card.progress.paused && 'is-paused']} aria-hidden="true">
					<span style:width="{card.progress.percent}%"></span>
				</span>
			{/if}
		</span>
		<span class="ct-library-title">{card.title}</span>
		<span class="ct-library-sub">{card.subtitle}</span>
		{#if card.detail}<span class="ct-library-detail">{card.detail}</span>{/if}
	</a>
	{#if look}
		<span class="ct-status-badge" data-status={look.slug} title={card.status}>
			<look.icon class="size-[13px]" strokeWidth={2.5} aria-hidden="true" />
			<span class="sr-only">{card.status}</span>
		</span>
	{/if}
</article>
