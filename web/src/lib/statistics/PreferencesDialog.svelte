<script lang="ts">
	import { djangoForm } from '#lib/csrf.ts';
	import Dialog from '#lib/ui/Dialog.svelte';
	import { st } from './strings.ts';
	import type { StatisticsScreen } from './types.ts';

	/**
	 * Statistics Preferences (the page's modal): Activity History view,
	 * duration format, week start, rating scale and, without the Anime type
	 * but with TVDB, how anime is counted. Save posts them all, as the page.
	 */
	let {
		open = $bindable(false),
		preferences,
		url,
		onsaved
	}: {
		open?: boolean;
		preferences: StatisticsScreen['preferences'];
		url: string;
		onsaved: () => void;
	} = $props();

	let values = $state({ history: '', duration: '', week: '', rating: '', anime: 'false' });
	let saving = $state(false);
	let failed = $state('');

	$effect(() => {
		// Each opening starts from the saved values.
		if (open) {
			values = {
				history: preferences.activity_history_view,
				duration: preferences.duration_format,
				week: preferences.week_start_day,
				rating: preferences.rating_scale,
				anime: String(preferences.stats_split_tv_anime)
			};
			failed = '';
		}
	});

	async function save() {
		saving = true;
		failed = '';
		try {
			const fields: Record<string, string> = {
				activity_history_view: values.history,
				duration_format: values.duration,
				week_start_day: values.week,
				rating_scale: values.rating
			};
			if (preferences.show_anime_split) fields.stats_split_tv_anime = values.anime;
			const response = await djangoForm(url, fields, { json: true });
			if (!response.ok) throw new Error(String(response.status));
			open = false;
			onsaved();
		} catch {
			failed = st.failed;
		}
		saving = false;
	}

	const groups = $derived([
		{ id: 'history', label: st.historyView, options: st.historyViews },
		{ id: 'duration', label: st.durationFormat, options: st.durationFormats },
		{ id: 'week', label: st.weekStart, options: st.weekStarts },
		{ id: 'rating', label: st.ratingScale, options: st.ratingScales },
		...(preferences.show_anime_split ? [{ id: 'anime', label: st.animeSplit, options: st.animeSplits }] : [])
	] as { id: keyof typeof values; label: string; options: Record<string, string> }[]);
</script>

<Dialog bind:open title={st.preferences} sheet>
	<form
		class="ct-stats-prefs"
		onsubmit={(event) => {
			event.preventDefault();
			save();
		}}
	>
		{#each groups as group (group.id)}
			<label>
				<span>{group.label}</span>
				<select bind:value={values[group.id]}>
					{#each Object.entries(group.options) as [value, label] (value)}
						<option {value}>{label}</option>
					{/each}
				</select>
			</label>
		{/each}
		{#if failed}<p class="ct-stats-prefs__error" role="alert">{failed}</p>{/if}
		<div class="ct-stats-prefs__actions">
			<button type="button" class="ct-stats-button" onclick={() => (open = false)}>{st.cancel}</button>
			<button type="submit" class="ct-stats-button is-primary" disabled={saving}>{saving ? st.saving : st.save}</button>
		</div>
	</form>
</Dialog>
