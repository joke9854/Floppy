<script lang="ts">
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import type { components } from '#lib/api/client.ts';
	import { t } from '#lib/strings.ts';
	import { weekday, dayOfMonth } from './dates.ts';

	type Release = components['schemas']['HomeRelease'];

	/** One release in Airing This Week: day, poster, title, "S2 E5 · 21:00", tag. */
	let { release }: { release: Release } = $props();
</script>

<li>
	<a href={release.url} class="ct-airing-row">
		<span class={['ct-airing-day', release.is_today && 'is-today']}>
			<span>{weekday(release.day)}</span>
			<strong>{dayOfMonth(release.day)}</strong>
		</span>
		<img
			alt=""
			class="ct-airing-poster"
			src={release.poster}
			width="40"
			height="60"
			loading="lazy"
			decoding="async"
		/>
		<span class="ct-airing-text">
			<span class="ct-airing-title">{release.title}</span>
			<span class="ct-airing-sub">
				{release.label}{#if release.time}&nbsp;· {release.time}{/if}
			</span>
		</span>
		{#if release.tag === 'finale'}
			<span class="ct-airing-tag">{t.finale}</span>
		{:else if release.tag === 'premiere'}
			<span class="ct-airing-tag is-premiere">{t.premiere}</span>
		{/if}
		<ChevronRight class="ct-airing-chevron size-4" aria-hidden="true" />
	</a>
</li>
