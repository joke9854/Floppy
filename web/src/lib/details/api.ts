import type { components } from '#lib/api/client.ts';

export type DetailShell = components['schemas']['DetailShell'];
export type DetailSections = components['schemas']['DetailSections'];
export type DetailSeason = components['schemas']['DetailSeason'];
export type DetailEpisode = components['schemas']['DetailEpisode'];
export type DetailCard = components['schemas']['DetailCard'];
export type DetailIssue = components['schemas']['DetailIssue'];
export type DetailTrailer =components['schemas']['DetailTrailer'];

/** A movie or show page's three reads (GET details/...). */
export function detailApiPath(
	type: string,
	source: string,
	id: string,
	part: 'shell' | 'sections' | 'trailers' = 'shell',
	season?: string | null,
	page?: number | null
): string {
	const base =
		`/api/v1/details/${encodeURIComponent(type)}/${encodeURIComponent(source)}/` +
		`${encodeURIComponent(id)}/`;
	if (part === 'shell') return base;
	if (part === 'trailers') return `${base}trailers/`;
	const query = new URLSearchParams();
	if (season) query.set('season', season);
	// A comic volume's next page of issues (`issues_more.page`).
	if (page) query.set('episode_page', String(page));
	const text = query.toString();
	return text ? `${base}sections/?${text}` : `${base}sections/`;
}

export type PersonScreen = components['schemas']['PersonScreen'];
export type EpisodeScreen = components['schemas']['EpisodeScreen'];

/** A person page's read (GET details/person/...). */
export function personApiPath(source: string, id: string): string {
	return `/api/v1/details/person/${encodeURIComponent(source)}/${encodeURIComponent(id)}/`;
}

/** An episode page's read (GET details/episode/...). */
export function episodeApiPath(
	source: string,
	id: string,
	season: string | number,
	episode: string | number
): string {
	return (
		`/api/v1/details/episode/${encodeURIComponent(source)}/${encodeURIComponent(id)}/` +
		`${encodeURIComponent(String(season))}/${encodeURIComponent(String(episode))}/`
	);
}

/** One season of a show's episode list, or its next batch (`load_more`). */
export function seasonApiPath(source: string, id: string, query: string): string {
	return (
		`/api/v1/details/tv/${encodeURIComponent(source)}/${encodeURIComponent(id)}/season/?` + query
	);
}

/**
 * The watch time the Django "Mark as watched" form sends (ctShell.js
 * `ctWatchNow`): the browser's local wall time, or its date when the
 * instance records dates only. The form reads it in the user's time zone.
 */
export function formWatchNow(at: Date, trackTime: boolean): string {
	const pad = (value: number) => String(value).padStart(2, '0');
	const date = `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}`;
	if (!trackTime) return date;
	return `${date}T${pad(at.getHours())}:${pad(at.getMinutes())}:${pad(at.getSeconds())}`;
}
