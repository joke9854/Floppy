<script lang="ts">
	import type { components } from '#lib/api/client.ts';
	import { dt } from '#lib/details/strings.ts';
	import PeopleRail from './PeopleRail.svelte';

	type Info = components['schemas']['DetailSeasonInfo'];

	/** A season's info (the season fragment's #ct-season-info), in the season dialog. */
	let { info }: { info: Info } = $props();
</script>

<div class="ct-season-info">
	<div class="ct-season-info__head">
		{#if info.poster}
			<img alt="" class="ct-season-info__poster" src={info.poster} width="185" height="278" decoding="async" />
		{/if}
		<div>
			<p class="ct-detail-meta">
				{#if info.year}<span>{info.year}</span>{/if}
				{#if info.episodes}<span>{dt.episodeCount(info.episodes)}</span>{/if}
				{#if info.runtime}<span>{info.runtime}</span>{/if}
			</p>
			{#if info.score}
				<p class="ct-season-info__score">
					<span aria-hidden="true">★</span>
					{info.score}
					<span class="ct-season-info__source">TMDB</span>
				</p>
			{/if}
		</div>
	</div>
	{#if info.synopsis}<p class="ct-season-info__synopsis">{info.synopsis}</p>{/if}
	{#if info.cast.length}
		<PeopleRail cast={info.cast} crew={[]} />
	{/if}
</div>
