<script lang="ts">
	import Activity from '@lucide/svelte/icons/activity';
	import CalendarDays from '@lucide/svelte/icons/calendar-days';
	import CircleCheck from '@lucide/svelte/icons/circle-check';
	import Flame from '@lucide/svelte/icons/flame';
	import Star from '@lucide/svelte/icons/star';
	import type { components } from '#lib/api/client.ts';
	import { st } from './strings.ts';

	type Summary = components['schemas']['StatisticsScreenSummary'];

	/**
	 * The summary cards (statistics.html): Completed Items, Average Rating,
	 * Most Active Day, Current Streak for the picked type, and Activity
	 * against the compared period (every type, as on the page).
	 */
	let {
		summary,
		activity,
		scaleMax
	}: {
		summary: Summary | null;
		activity: components['schemas']['StatisticsScreenActivity'];
		scaleMax: number;
	} = $props();
</script>

<div class="ct-stat-cards">
	<div class="ct-stat-card">
		<span class="ct-stat-card__icon"><CircleCheck class="size-5" aria-hidden="true" /></span>
		<div>
			<h3>{st.completed}</h3>
			{#if summary?.total}
				<p class="ct-stat-card__value">{summary.completed} <small>/ {summary.total}</small></p>
			{:else}<p class="ct-stat-card__value is-empty">--</p>{/if}
		</div>
	</div>
	<div class="ct-stat-card">
		<span class="ct-stat-card__icon"><Star class="size-5" aria-hidden="true" /></span>
		<div>
			<h3>{st.averageRating}</h3>
			{#if summary?.has_score}
				<p class="ct-stat-card__value">{summary.average_score} <small>/ {scaleMax}</small></p>
			{:else}<p class="ct-stat-card__value is-empty">--</p>{/if}
		</div>
	</div>
	<div class="ct-stat-card">
		<span class="ct-stat-card__icon"><CalendarDays class="size-5" aria-hidden="true" /></span>
		<div>
			<h3>{st.mostActiveDay}</h3>
			{#if summary?.most_active_day}
				<p class="ct-stat-card__value">{summary.most_active_day}</p>
				<p class="ct-stat-card__sub">{st.ofActivity(summary.most_active_day_percentage)}</p>
			{:else}<p class="ct-stat-card__value is-empty">--</p>{/if}
		</div>
	</div>
	<div class="ct-stat-card">
		<span class="ct-stat-card__icon"><Flame class="size-5" aria-hidden="true" /></span>
		<div>
			<h3>{st.currentStreak}</h3>
			{#if summary?.most_active_day}
				<p class="ct-stat-card__value">{st.days(summary.current_streak)}</p>
				<p class="ct-stat-card__sub" title={summary.longest_streak_dates || undefined}>
					{st.longest(summary.longest_streak)}
				</p>
			{:else}<p class="ct-stat-card__value is-empty">--</p>{/if}
		</div>
	</div>
	<div class="ct-stat-card">
		<span class={['ct-stat-card__icon', `is-${activity.state}`]}><Activity class="size-5" aria-hidden="true" /></span>
		<div>
			<h3>{st.activity}</h3>
			<p class={['ct-stat-card__value', `is-${activity.state}`, !activity.badge && 'is-empty']}>
				{activity.badge || '--'}
			</p>
			{#if activity.badge}
				<p
					class="ct-stat-card__sub"
					title={activity.tooltip
						? `${activity.tooltip.current_label}: ${activity.tooltip.current_total}\n${activity.tooltip.comparison_label}: ${activity.tooltip.comparison_total}`
						: undefined}
				>
					{st.vs(activity.period_label)}
				</p>
			{/if}
		</div>
	</div>
</div>
