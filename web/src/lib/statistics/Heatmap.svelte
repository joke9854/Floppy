<script lang="ts">
	import type { components } from '#lib/api/client.ts';
	import { st } from './strings.ts';

	/**
	 * Activity History (statistics.html): one column per week, one cell per
	 * day in five levels, months along the top, every other weekday down the
	 * side. It shows every type, as on the page.
	 */
	let { heatmap }: { heatmap: components['schemas']['StatisticsScreenHeatmap'] } = $props();
</script>

<section class="ct-stats-card">
	<div class="ct-stats-card__head">
		<div>
			<h2 class="ct-stats-card__title">{st.activityHistory}</h2>
			<p class="ct-stats-card__sub">{st.activityHistorySub}</p>
		</div>
		<div class="ct-heat-legend" aria-hidden="true">
			<span>{st.less}</span>
			{#each [0, 1, 2, 3, 4] as level (level)}<i class="ct-heat-cell is-{level}"></i>{/each}
			<span>{st.more}</span>
		</div>
	</div>
	<div class="ct-heat-scroll">
		<div class="ct-heat">
			<div class="ct-heat-months">
				{#each heatmap.months as month, index (index)}
					<span style:flex="{month.weeks} {month.weeks} 0" style:min-width="calc({month.weeks} * 1rem)">{month.label}</span>
				{/each}
			</div>
			<div class="ct-heat-body">
				<div class="ct-heat-weekdays" aria-hidden="true">
					{#each heatmap.weekdays as weekday, index (index)}
						<span>{index % 2 === 0 ? weekday : ''}</span>
					{/each}
				</div>
				<div class="ct-heat-weeks">
					{#each heatmap.weeks as week, column (column)}
						<div class="ct-heat-week">
							{#each week as day, row (row)}
								<i
									class={['ct-heat-cell', day.future ? 'is-future' : `is-${day.level}`]}
									title={day.future ? day.date : st.activities(day.date, day.count)}
								></i>
							{/each}
						</div>
					{/each}
				</div>
			</div>
		</div>
	</div>
</section>
