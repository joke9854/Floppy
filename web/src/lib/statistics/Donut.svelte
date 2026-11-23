<script lang="ts">
	import type { Slice } from './charts.ts';

	/**
	 * A doughnut in plain SVG with a centre total and a legend sorted by
	 * size (the page's Hours by Media Type and Status Composition).
	 */
	let {
		slices,
		total,
		caption,
		format,
		label
	}: { slices: Slice[]; total: string; caption: string; format: (value: number) => string; label: string } = $props();

	const RADIUS = 60;
	const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
	const sum = $derived(slices.reduce((a, slice) => a + slice.value, 0) || 1);
	const arcs = $derived.by(() => {
		let offset = 0;
		return slices.map((slice) => {
			const length = (slice.value / sum) * CIRCUMFERENCE;
			const arc = { ...slice, length, offset };
			offset += length;
			return arc;
		});
	});
	const legend = $derived([...slices].sort((a, b) => b.value - a.value));
	const percent = (value: number) => `${Math.round((value / sum) * 100)}%`;
</script>

<div class="ct-donut">
	<div class="ct-donut__chart">
		<svg viewBox="0 0 150 150" role="img" aria-label={label}>
			<circle cx="75" cy="75" r={RADIUS} class="ct-donut__track" />
			{#each arcs as arc, index (index)}
				<circle
					cx="75"
					cy="75"
					r={RADIUS}
					fill="none"
					stroke={arc.color}
					stroke-width="20"
					stroke-dasharray="{Math.max(0, arc.length - 1)} {CIRCUMFERENCE}"
					stroke-dashoffset={-arc.offset}
					transform="rotate(-90 75 75)"
				>
					<title>{arc.label}: {format(arc.value)} ({percent(arc.value)})</title>
				</circle>
			{/each}
		</svg>
		<span class="ct-donut__center"><strong>{total}</strong><small>{caption}</small></span>
	</div>
	<ul class="ct-donut__legend">
		{#each legend as slice, index (index)}
			<li>
				<span class="ct-donut__dot" style:background-color={slice.color}></span>
				<span class="ct-donut__name">{slice.label}</span>
				<span class="ct-donut__value">{format(slice.value)}</span>
				<span class="ct-donut__pct">{percent(slice.value)}</span>
			</li>
		{/each}
	</ul>
</div>
