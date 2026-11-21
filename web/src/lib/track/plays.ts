/**
 * The Episode Plays tab's rules (P4-D3), ported from the Django dialog's
 * episodeBulkTrackForm.js: the episode list follows the season, the range
 * runs by watch order from the first pick to the last, and the summary and
 * warning say what saving will do. The server spreads the dates.
 */
import type { components } from '#lib/api/client.ts';

export type Plays = components['schemas']['TrackPlays'];
export type PlaysEpisode = components['schemas']['TrackPlaysEpisode'];
export type Side = 'first' | 'last';
export type Range = { firstSeason: string; firstEpisode: string; lastSeason: string; lastEpisode: string };

/** The page's first pick: the form's value, else the domain default. */
export function initialRange(plays: Plays): Range {
	const range = {
		firstSeason: String(plays.first.season_number ?? ''),
		firstEpisode: String(plays.first.episode_number ?? ''),
		lastSeason: String(plays.last.season_number ?? ''),
		lastEpisode: String(plays.last.episode_number ?? '')
	};
	return syncEpisode(plays, syncEpisode(plays, range, 'first'), 'last');
}

export function seasonEpisodes(plays: Plays, season: string): PlaysEpisode[] {
	return plays.episodes[season] ?? [];
}

export function episodeLabel(episode: PlaysEpisode): string {
	return episode.selector_label || `E${episode.episode_number} - ${episode.episode_title}`;
}

export function selectedEpisode(plays: Plays, range: Range, side: Side): PlaysEpisode | undefined {
	const season = side === 'first' ? range.firstSeason : range.lastSeason;
	const number = side === 'first' ? range.firstEpisode : range.lastEpisode;
	return seasonEpisodes(plays, season).find((episode) => String(episode.episode_number) === number);
}

/**
 * Keep the side's episode when its season still has it, else the season's
 * first episode for the first pick and its last for the last (syncEpisodeOptions).
 */
export function syncEpisode(plays: Plays, range: Range, side: Side): Range {
	const episodes = seasonEpisodes(plays, side === 'first' ? range.firstSeason : range.lastSeason);
	const current = side === 'first' ? range.firstEpisode : range.lastEpisode;
	if (!episodes.length || episodes.some((episode) => String(episode.episode_number) === current)) return range;
	const pick = String((side === 'first' ? episodes[0] : episodes[episodes.length - 1]).episode_number);
	return side === 'first' ? { ...range, firstEpisode: pick } : { ...range, lastEpisode: pick };
}

/** Every episode from the first pick to the last, by watch order (selectedRangeEpisodes). */
export function rangeEpisodes(plays: Plays, range: Range): PlaysEpisode[] {
	const first = selectedEpisode(plays, range, 'first');
	const last = selectedEpisode(plays, range, 'last');
	if (!first || !last) return [];
	return Object.values(plays.episodes)
		.flat()
		.filter((episode) => first.order <= episode.order && episode.order <= last.order);
}

const count = (n: number, one: string, many: string) => (n === 1 ? one : many).replace('%(count)s', String(n));

/** The summary and the warning under it (refreshSummary). */
export function summary(
	plays: Plays,
	range: Range,
	writeMode: string,
	distributionMode: string
): { text: string; warning: string } {
	const episodes = rangeEpisodes(plays, range);
	if (!episodes.length) return { text: 'Choose a valid ordered range to log plays.', warning: '' };

	const existing = episodes.reduce((total, episode) => total + (episode.existing_play_count || 0), 0);
	const distribution =
		distributionMode === 'air_date'
			? 'the target dates within the selected date range'
			: 'an even distribution across the date range';
	const text = (
		writeMode === 'replace'
			? count(
					episodes.length,
					'This will replace plays for %(count)s ordered item using ',
					'This will replace plays for %(count)s ordered items using '
				)
			: count(
					episodes.length,
					'This will add plays for %(count)s ordered item using ',
					'This will add plays for %(count)s ordered items using '
				)
	).concat(`${distribution}.`);

	if (distributionMode === 'air_date') {
		const missing = episodes.filter((episode) => !episode.air_date).length;
		if (missing > 0) {
			const warning = count(
				missing,
				'%(count)s selected item has no target date.',
				'%(count)s selected items have no target date.'
			);
			return {
				text,
				warning:
					plays.missing_target_fallback === 'even'
						? `${warning} Saving will fall back to even distribution.`
						: warning
			};
		}
	}
	if (writeMode === 'replace') {
		return {
			text,
			warning:
				existing > 0
					? count(
							existing,
							'This will delete %(count)s existing play in the selected range before adding the new ordered pass.',
							'This will delete %(count)s existing plays in the selected range before adding the new ordered pass.'
						)
					: 'No existing plays are currently logged in the selected range.'
		};
	}
	return {
		text,
		warning:
			existing > 0
				? count(
						existing,
						'This range already has %(count)s logged play. New plays will be appended in order.',
						'This range already has %(count)s logged plays. New plays will be appended in order.'
					)
				: ''
	};
}

/** The fields the page's form posts (fill_track_episode_bulk.html). */
export function playsData(
	plays: Plays,
	range: Range,
	values: Record<string, string>
): Record<string, string> {
	const data: Record<string, string> = {};
	for (const field of plays.hidden) data[field.name] = values[field.name] ?? field.value;
	return {
		...data,
		first_season_number: range.firstSeason,
		first_episode_number: range.firstEpisode,
		last_season_number: range.lastSeason,
		last_episode_number: range.lastEpisode,
		write_mode: values.write_mode ?? plays.write_mode.value,
		distribution_mode: values.distribution_mode ?? plays.distribution_mode.value,
		start_date: values.start_date ?? '',
		end_date: values.end_date ?? '',
		episode_count: String(rangeEpisodes(plays, range).length)
	};
}
