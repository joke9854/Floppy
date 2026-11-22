<script lang="ts">
	import Plus from '@lucide/svelte/icons/plus';
	import { detailLink } from '#lib/details/link.ts';
	import { dc } from './strings.ts';
	import type { DiscoverSlide } from './types.ts';

	/**
	 * The Discover hero (ct/discover_hero.html): a scroll-snap carousel of one
	 * pick per row with its backdrop (or logo), "Type · Genre · Year", Add to
	 * Planning and Details. The dots follow the scroll; it advances every 7 s
	 * unless hovered, focused or the user prefers reduced motion.
	 */
	let {
		slides,
		busy = '',
		onplan
	}: { slides: DiscoverSlide[]; busy?: string; onplan: (slide: DiscoverSlide) => void } = $props();

	let track: HTMLDivElement;
	let current = $state(0);
	let paused = $state(false);

	function go(index: number) {
		track?.scrollTo({ left: index * track.clientWidth, behavior: 'smooth' });
	}

	function sync() {
		if (track) current = Math.round(track.scrollLeft / Math.max(track.clientWidth, 1));
	}

	$effect(() => {
		if (slides.length < 2 || paused) return;
		if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
		const timer = setInterval(() => go((current + 1) % slides.length), 7000);
		return () => clearInterval(timer);
	});
</script>

<section
	class="ct-discover-hero"
	aria-roledescription="carousel"
	aria-label={dc.featured}
	onpointerenter={() => (paused = true)}
	onpointerleave={() => (paused = false)}
	onfocusin={() => (paused = true)}
	onfocusout={() => (paused = false)}
>
	<div class="ct-discover-hero__track" bind:this={track} onscroll={sync}>
		{#each slides as slide, index (index)}
			<article
				class="ct-discover-hero__slide"
				aria-roledescription="slide"
				aria-label={dc.slideOf(index + 1, slides.length)}
			>
				<img
					alt=""
					class="ct-discover-hero__art"
					src={slide.backdrop}
					srcset={slide.backdrop_srcset || undefined}
					sizes={slide.backdrop_srcset ? '(min-width: 768px) 80vw, 100vw' : undefined}
					width="1280"
					height="720"
					decoding="async"
					fetchpriority={index === 0 ? 'high' : undefined}
					loading={index === 0 ? undefined : 'lazy'}
				/>
				<div class="ct-discover-hero__fade" aria-hidden="true"></div>
				<div class="ct-discover-hero__body">
					<a {...detailLink(slide.href)} class={['ct-discover-hero__title', slide.logo && 'has-logo']}>
						{#if slide.logo}
							<img alt={slide.title} src={slide.logo} width="800" height="310" decoding="async" />
						{:else}
							{slide.title}
						{/if}
					</a>
					<p class="ct-discover-hero__meta">{slide.meta}</p>
					<div class="ct-discover-hero__actions">
						<button
							type="button"
							class="ct-discover-hero__primary"
							disabled={busy === slide.key}
							onclick={() => onplan(slide)}
						>
							<Plus class="size-4" aria-hidden="true" />
							{dc.addToPlanning}
						</button>
						<a {...detailLink(slide.href)} class="ct-discover-hero__secondary">{dc.details}</a>
					</div>
				</div>
			</article>
		{/each}
	</div>
	{#if slides.length > 1}
		<div class="ct-discover-hero__dots">
			{#each slides as slide, index (index)}
				<button
					type="button"
					aria-label={dc.goToSlide(index + 1)}
					aria-current={index === current ? 'true' : undefined}
					onclick={() => go(index)}
				></button>
			{/each}
		</div>
	{/if}
</section>
