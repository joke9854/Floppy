<script lang="ts">
	import { djangoForm } from '#lib/csrf.ts';
	import DateField, { type DateAction } from './DateField.svelte';
	import {
		episodeLabel,
		initialRange,
		playsData,
		seasonEpisodes,
		selectedEpisode,
		summary,
		syncEpisode,
		type Plays,
		type Range,
		type Side
	} from './plays.ts';
	import {
		clearDate,
		formatValue,
		initialState,
		justFinished,
		releaseDate,
		setDate,
		startNow,
		type DateField as DateName,
		type TrackState
	} from './rules.ts';
	import { tt } from './strings.ts';

	/**
	 * The Episode Plays tab (P4-D3), as the Django dialog's
	 * fill_track_episode_bulk.html: a first and a last episode (or track), the
	 * two dates the plays spread over, Add or Replace, by target date or
	 * evenly. Saving queues the page's own job, which writes the plays.
	 */
	let { plays, trackTime, onsaved }: { plays: Plays; trackTime: boolean; onsaved: (message: string) => void } =
		$props();

	// svelte-ignore state_referenced_locally
	let range = $state.raw<Range>(initialRange(plays));
	// svelte-ignore state_referenced_locally
	let form = $state.raw<TrackState>(
		initialState(
			[...plays.hidden, plays.write_mode, plays.distribution_mode, plays.start_date, plays.end_date],
			trackTime,
			new Date(),
			true
		)
	);
	let busy = $state(false);
	let problem = $state('');

	const writeMode = $derived(form.values.write_mode ?? plays.write_mode.value);
	const distributionMode = $derived(form.values.distribution_mode ?? plays.distribution_mode.value);
	const said = $derived(summary(plays, range, writeMode, distributionMode));
	const shortcut = $derived(plays.labels.date_shortcut || 'Release Date');
	const seasonLabel = $derived(plays.labels.season_field || 'Season');
	const episodeFieldLabel = $derived(plays.labels.episode_field || 'Episode');

	function pickSeason(side: Side, season: string) {
		const next = side === 'first' ? { ...range, firstSeason: season } : { ...range, lastSeason: season };
		range = syncEpisode(plays, next, side);
	}

	function pickEpisode(side: Side, episode: string) {
		range = side === 'first' ? { ...range, firstEpisode: episode } : { ...range, lastEpisode: episode };
	}

	function choose(name: string, next: string) {
		form = { ...form, values: { ...form.values, [name]: next } };
	}

	/** The picker's quick actions, with the first or last pick's date and runtime. */
	function dateAction(name: DateName, action: DateAction) {
		const episode = selectedEpisode(plays, range, name === 'start_date' ? 'first' : 'last');
		const runtime = episode?.runtime_minutes ?? null;
		const now = new Date();
		if (action === 'start-now') form = startNow(form, name, runtime, now);
		else if (action === 'just-finished') form = justFinished(form, name, runtime, now);
		else if (action === 'release-date') form = releaseDate(form, name, episode?.air_date ?? '', runtime, now);
		else if (action === 'now') form = setDate(form, name, formatValue(now, trackTime));
		else if (action === 'clear') form = clearDate(form, name);
	}

	async function save() {
		if (busy) return;
		busy = true;
		problem = '';
		try {
			const response = await djangoForm(plays.save_url, playsData(plays, range, form.values), { json: true });
			const body = await response.json().catch(() => ({}));
			if (response.ok && body.queued) onsaved(body.message ?? '');
			else problem = body.error ?? tt.trackSaveFailed;
		} catch {
			problem = tt.trackSaveFailed;
		} finally {
			busy = false;
		}
	}
</script>

<form
	class="ct-track__form"
	novalidate
	onsubmit={(event) => {
		event.preventDefault();
		save();
	}}
>
	{#if plays.mode_notice}<p class="ct-plays__notice">{plays.mode_notice}</p>{/if}

	<div class="ct-plays__sides">
		{#each ['first', 'last'] as const as side (side)}
			{@const season = side === 'first' ? range.firstSeason : range.lastSeason}
			{@const episode = side === 'first' ? range.firstEpisode : range.lastEpisode}
			<fieldset class="ct-plays__side">
				<legend class="ct-plays__legend">
					{side === 'first'
						? plays.labels.first_selection || 'First Play'
						: plays.labels.last_selection || 'Last Play'}
				</legend>
				{#if !plays.hide_season_selectors}
					<label class="ct-track-label" for="plays-{side}-season">{seasonLabel}</label>
					<select
						id="plays-{side}-season"
						class="ct-track-input"
						value={season}
						onchange={(e) => pickSeason(side, e.currentTarget.value)}
					>
						{#each plays.seasons as option (option.season_number)}
							<option value={String(option.season_number)}>{option.season_title}</option>
						{/each}
					</select>
				{/if}
				<label class="ct-track-label mt-3" for="plays-{side}-episode">{episodeFieldLabel}</label>
				<select
					id="plays-{side}-episode"
					class="ct-track-input"
					value={episode}
					onchange={(e) => pickEpisode(side, e.currentTarget.value)}
				>
					{#each seasonEpisodes(plays, season) as option (option.episode_number)}
						<option value={String(option.episode_number)}>{episodeLabel(option)}</option>
					{/each}
				</select>
			</fieldset>
		{/each}
	</div>
	{#if plays.locked_season_number != null && !plays.hide_season_selectors}
		<p class="ct-track__help">{tt.playsLocked}</p>
	{/if}

	<div class="ct-track__grid">
		{#each [plays.start_date, plays.end_date] as field (field.name)}
			{@const name = field.name as DateName}
			{@const pick = selectedEpisode(plays, range, name === 'start_date' ? 'first' : 'last')}
			<div class="ct-track__field is-wide">
				<DateField
					id="plays-{field.name}"
					label={name === 'start_date' ? tt.startDate : tt.endDate}
					value={form.values[name] ?? ''}
					trackTime={field.kind === 'datetime'}
					releaseLabel={pick?.air_date ? shortcut : ''}
					copyLabel=""
					oninput={(next) => (form = setDate(form, name, next))}
					onaction={(action) => dateAction(name, action)}
				/>
			</div>
		{/each}
		{#each [plays.write_mode, plays.distribution_mode] as field (field.name)}
			<div class="ct-track__field is-wide">
				<label class="ct-track-label" for="plays-{field.name}">{field.label}</label>
				<select
					id="plays-{field.name}"
					class="ct-track-input"
					value={form.values[field.name] ?? field.value}
					onchange={(e) => choose(field.name, e.currentTarget.value)}
				>
					{#each field.choices as choice (choice.value)}
						<option value={choice.value}>{choice.label}</option>
					{/each}
				</select>
			</div>
		{/each}
	</div>

	<div class="ct-plays__summary" aria-live="polite">
		<p>{said.text}</p>
		{#if said.warning}<p class="mt-2">{said.warning}</p>{/if}
	</div>

	{#if problem}<p class="ct-track__problem" role="alert">{problem}</p>{/if}
	<div class="ct-track__actions">
		<div class="ct-track__actions-end">
			<button type="submit" class="ct-track-btn is-primary" disabled={busy}>{plays.submit_label}</button>
		</div>
	</div>
</form>
