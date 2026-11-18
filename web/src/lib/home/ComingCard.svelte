<script lang="ts">
	import { detailLink } from '#lib/details/link.ts';
	import type { components } from '#lib/api/client.ts';
	import { t } from '#lib/strings.ts';
	import { fadeIn } from '#lib/media/fade.ts';
	import { comingDay } from './dates.ts';

	type Release = components['schemas']['HomeRelease'];

	/**
	 * A Coming Soon release: the poster stays crisp, with glass date and
	 * Premiere/Finale pills over it, then the title and "S3 E1".
	 */
	let { release }: { release: Release } = $props();
</script>

<article class="ct-poster-card">
	<a {...detailLink(release.url)} class="ct-poster-link">
		<span class="ct-poster-frame">
			<img
				alt={release.title}
				class="ct-poster-img ct-fade-img"
				src={release.poster}
				srcset={release.poster_srcset || undefined}
				sizes={release.poster_srcset ? '176px' : undefined}
				width="342"
				height="513"
				loading="lazy"
				decoding="async"
				use:fadeIn
			/>
			<span class={['ct-coming-date', release.is_today && 'is-today']}>
				{release.is_today ? t.today : comingDay(release.day)}
			</span>
			{#if release.tag === 'finale'}
				<span class="ct-coming-tag">{t.finale}</span>
			{:else if release.tag === 'premiere'}
				<span class="ct-coming-tag is-premiere">{t.premiere}</span>
			{/if}
		</span>
		<span class="ct-poster-title">{release.title}</span>
		<span class="ct-poster-sub">{release.label}</span>
	</a>
</article>
