import type { components } from '#lib/api/client.ts';

export type ArtistScreen = components['schemas']['ArtistScreen'];
export type AlbumScreen = components['schemas']['AlbumScreen'];
export type PodcastScreen = components['schemas']['PodcastScreen'];
export type PodcastEpisodesPage = components['schemas']['PodcastEpisodesPage'];
export type PodcastEpisode = components['schemas']['PodcastEpisode'];
export type AlbumTrack = components['schemas']['AlbumTrack'];
export type MediaPlay = components['schemas']['MediaPlay'];
export type MediaActivity = components['schemas']['MediaActivity'];
export type MediaLinkSection = components['schemas']['DetailLinkSection'];

/** The music and podcast pages' reads (GET details/music/..., details/podcast/...). */
export function artistApiPath(artistId: string): string {
	return `/api/v1/details/music/artist/${encodeURIComponent(artistId)}/`;
}

export function albumApiPath(artistId: string, albumId: string): string {
	return `${artistApiPath(artistId)}album/${encodeURIComponent(albumId)}/`;
}

/** A show page, or (`page` above 1) only that page of its episodes. */
export function podcastApiPath(source: string, uuid: string, page?: number | null): string {
	const base = `/api/v1/details/podcast/${encodeURIComponent(source)}/${encodeURIComponent(uuid)}/`;
	return page && page > 1 ? `${base}?episode_page=${page}` : base;
}

const pad = (value: number) => String(value).padStart(2, '0');

/** A `datetime-local` input's value for an instant, in the browser's time zone. */
export function toLocalInput(at: Date): string {
	return (
		`${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}` +
		`T${pad(at.getHours())}:${pad(at.getMinutes())}:${pad(at.getSeconds())}`
	);
}

/**
 * The exact instant a `datetime-local` value names, as ISO 8601 with the
 * browser's UTC offset (never a date alone). Null for a value that is no time.
 */
export function toIsoWithOffset(local: string): string | null {
	const at = new Date(local);
	if (Number.isNaN(at.getTime())) return null;
	const offset = -at.getTimezoneOffset();
	const sign = offset >= 0 ? '+' : '-';
	const hours = pad(Math.floor(Math.abs(offset) / 60));
	const minutes = pad(Math.abs(offset) % 60);
	return `${toLocalInput(at)}${sign}${hours}:${minutes}`;
}

/** A play's date and time for display, in the browser's locale. */
export function playTime(iso: string): string {
	return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

/** The activity line under the title: the text and the dates it spans. */
export function activityLine(activity: MediaActivity | null): string {
	if (!activity) return '';
	const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { dateStyle: 'medium' });
	let range = '';
	if (activity.date_start) {
		range = day(activity.date_start);
		if (activity.date_end && day(activity.date_end) !== range) range += ` – ${day(activity.date_end)}`;
	}
	return [activity.primary_text, range].filter(Boolean).join(' · ');
}
