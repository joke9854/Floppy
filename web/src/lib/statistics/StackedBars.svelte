<script lang="ts">
	import type { Bars } from './types.ts';

	/**
	 * A stacked bar chart in plain SVG (the page draws these with Chart.js,
	 * which the web budget cannot carry): one bar per label, a segment per
	 * series in its colour, a y axis in `unit`, and the values on hover.
	 */
	let {
		bars,
		unit,
		label,
		width = 720
	}: { bars: Bars; unit: string; label: string; width?: number } = $props();

	const HEIGHT = 220;
	const AXIS = 40;
	const BOTTOM = 28;

	// `width` is the drawing width; the SVG scales to its card (no resize
	// observer), so narrow cards pass a smaller one to keep the text legible.
	const totals = $derived(bars.labels.map((_, index) => bars.series.reduce((sum, series) => sum + (series.values[index] || 0), 0)));
	const max = $derived(niceMax(Math.max(0, ...totals)));
	const plot = $derived(Math.max(1, width - AXIS));
	const slot = $derived(plot / Math.max(1, bars.labels.length));
	const barWidth = $derived(Math.max(2, Math.min(36, slot * 0.7)));
	// At most ~8 labels along the bottom, as Chart.js thins its ticks.
	const step = $derived(Math.max(1, Math.ceil(bars.labels.length / Math.max(1, Math.floor(plot / 72)))));
	const ticks = $derived([0, 0.25, 0.5, 0.75, 1].map((part) => +(max * part).toFixed(1)));

	function niceMax(value: number): number {
		if (value <= 0) return 1;
		const power = 10 ** Math.floor(Math.log10(value));
		const scaled = value / power;
		return (scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10) * power;
	}

	const y = (value: number) => (HEIGHT - BOTTOM) * (1 - value / max);

	function describe(index: number): string {
		const parts = bars.series
			.filter((series) => series.values[index])
			.map((series) => `${series.label}: ${format(series.values[index])} ${unit}`);
		return [bars.labels[index], ...parts].join('\n');
	}

	const format = (value: number) => value.toLocaleString('en-US', { maximumFractionDigits: 1 });
</script>

<div class="ct-stats-bars">
	<svg viewBox="0 0 {width} {HEIGHT}" width="100%" role="img" aria-label={label}>
		{#each ticks as tick, position (position)}
			<line x1={AXIS} x2={width} y1={y(tick)} y2={y(tick)} class="ct-stats-grid" />
			<text x={AXIS - 6} y={y(tick) + 4} text-anchor="end" class="ct-stats-tick">{format(tick)}</text>
		{/each}
		{#each bars.labels as barLabel, index (index)}
			{@const x = AXIS + slot * index + (slot - barWidth) / 2}
			<g class="ct-stats-bar">
				<title>{describe(index)}</title>
				<rect x={AXIS + slot * index} y="0" width={slot} height={HEIGHT - BOTTOM} fill="transparent" />
				{#each bars.series as series, which (which)}
					{@const below = bars.series.slice(0, which).reduce((sum, other) => sum + (other.values[index] || 0), 0)}
					{@const value = series.values[index] || 0}
					{#if value > 0}
						<rect
							{x}
							y={y(below + value)}
							width={barWidth}
							height={Math.max(1, y(below) - y(below + value))}
							fill={series.color || 'var(--color-accent)'}
							rx="2"
						/>
					{/if}
				{/each}
				{#if index % step === 0}
					<text x={x + barWidth / 2} y={HEIGHT - 8} text-anchor="middle" class="ct-stats-tick">{barLabel}</text>
				{/if}
			</g>
		{/each}
	</svg>
	{#if bars.series.length > 1}
		<ul class="ct-stats-legend">
			{#each bars.series as series (series.media_type || series.label)}
				<li><span style:background-color={series.color}></span>{series.label}</li>
			{/each}
		</ul>
	{/if}
</div>
