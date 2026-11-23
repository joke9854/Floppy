<script lang="ts">
	import { rhythmTiers } from './charts.ts';

	/**
	 * Activity Rhythm (drawRhythmChart): weekdays down, hours across, a dot
	 * per hour sized and lit by its quantile tier, with a Low-High legend.
	 */
	let { matrix }: { matrix: number[][] } = $props();

	const CELL = 12;
	const GAP = 4;
	const AREA = CELL + GAP;
	const MAX_R = CELL / 2;
	const LABEL_W = 30;
	const LABEL_H = 14;
	const TIERS = 6;
	const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
	const HOURS = [
		[0, '12 AM'],
		[6, '6 AM'],
		[12, '12 PM'],
		[18, '6 PM']
	] as const;

	const tiers = $derived(rhythmTiers(matrix, TIERS));
	const radius = (tier: number) => (tier === 0 ? 1.5 : 2 + (tier / TIERS) * (MAX_R - 2));
	const fill = (tier: number) => (tier === 0 ? 'rgba(255,255,255,0.05)' : `rgba(99,102,241,${(0.2 + 0.8 * (tier / TIERS)).toFixed(2)})`);
	const hour = (h: number) => `${h % 12 === 0 ? 12 : h % 12} ${h < 12 ? 'AM' : 'PM'}`;
</script>

<svg width="100%" viewBox="0 0 {LABEL_W + 24 * AREA} {LABEL_H + 7 * AREA}" class="ct-rhythm" role="img" aria-label="Activity Rhythm">
	{#each HOURS as [h, text] (h)}
		<text x={LABEL_W + h * AREA + CELL / 2} y={LABEL_H - 2} text-anchor="middle">{text}</text>
	{/each}
	{#each tiers as row, r (r)}
		<text x={LABEL_W - 4} y={LABEL_H + r * AREA + CELL / 2 + 3.5} text-anchor="end">{DAYS[r]}</text>
		{#each row as tier, c (c)}
			<circle cx={LABEL_W + c * AREA + CELL / 2} cy={LABEL_H + r * AREA + CELL / 2} r={radius(tier).toFixed(1)} fill={fill(tier)}>
				{#if matrix[r][c] > 0}<title>{DAYS[r]} {hour(c)} — {matrix[r][c]} session{matrix[r][c] === 1 ? '' : 's'}</title>{/if}
			</circle>
		{/each}
	{/each}
</svg>
<div class="ct-rhythm__legend" aria-hidden="true">
	<span>Low</span>
	{#each [1, 2, 3, 4, 5, 6] as tier (tier)}
		<i style:width="{radius(tier) * 2}px" style:height="{radius(tier) * 2}px" style:background={fill(tier)}></i>
	{/each}
	<span>High</span>
</div>
