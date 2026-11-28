<script lang="ts">
	import EpisodePage from '../../../../../../../tv/[id]/[title]/season/[season]/episode/[episode]/+page.svelte';
	import type { PageProps } from './$types';

	/** An anime filed as a series: the show episode page, read with `?parent=anime`. */
	let { data, params, form }: PageProps = $props();
</script>

<EpisodePage {data} {params} {form} />
