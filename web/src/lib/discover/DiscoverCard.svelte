<script lang="ts">
	import EyeOff from '@lucide/svelte/icons/eye-off';
	import Plus from '@lucide/svelte/icons/plus';
	import { detailLink } from '#lib/details/link.ts';
	import { fadeIn } from '#lib/media/fade.ts';
	import { dc } from './strings.ts';
	import type { DiscoverCard } from './types.ts';

	/**
	 * A Discover card: poster, title, "Type · Year", and the page's quick
	 * actions (Add to Planning, Hide from Discover) over the poster: on hover
	 * or focus with a mouse, always on touch screens.
	 */
	let {
		card,
		square = false,
		busy = false,
		onaction
	}: {
		card: DiscoverCard;
		square?: boolean;
		busy?: boolean;
		onaction: (action: 'planning' | 'dismiss', card: DiscoverCard) => void;
	} = $props();
</script>

<article class={['ct-poster-card ct-discover-card', square && 'is-square', busy && 'is-busy']} data-media-type={card.media_type}>
	<a {...detailLink(card.href)} class="ct-poster-link">
		<span class="ct-poster-frame">
			<img
				alt={card.title}
				class="ct-poster-img ct-fade-img"
				src={card.poster}
				srcset={card.poster_srcset || undefined}
				sizes={card.poster_srcset ? '176px' : undefined}
				width="342"
				height={square ? 342 : 513}
				loading="lazy"
				decoding="async"
				use:fadeIn
			/>
		</span>
		<span class="ct-poster-title">{card.title}</span>
		<span class="ct-poster-sub">{card.sub}</span>
	</a>
	<div class="ct-discover-card__actions">
		<button
			type="button"
			class="ct-discover-card__action"
			title={dc.addToPlanning}
			aria-label="{dc.addToPlanning}: {card.title}"
			disabled={busy}
			onclick={() => onaction('planning', card)}
		>
			<Plus class="size-4" aria-hidden="true" />
		</button>
		<button
			type="button"
			class="ct-discover-card__action"
			title={dc.hide}
			aria-label="{dc.hide}: {card.title}"
			disabled={busy}
			onclick={() => onaction('dismiss', card)}
		>
			<EyeOff class="size-4" aria-hidden="true" />
		</button>
	</div>
</article>
