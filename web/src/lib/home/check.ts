import { djangoWrite } from '#lib/csrf.ts';
import type { components } from '#lib/api/client.ts';

export type CheckTarget = components['schemas']['HomeCheckTarget'];

/** What a check click came to. */
export type CheckOutcome = 'saved' | 'failed' | 'unavailable';

/** One click: its event id and when it happened. A retry reuses both. */
export type Click = { id: string; at: Date };

/**
 * The watch time the check sends: the exact instant, or, when the instance
 * records dates only (TRACK_TIME off), the browser's local date, which
 * Floppy reads as that day's midnight exactly as the Django form's date.
 */
export function watchTime(at: Date, trackTime: boolean): string {
	if (trackTime) return at.toISOString();
	const pad = (value: number) => String(value).padStart(2, '0');
	return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}`;
}

/**
 * Mark the episode an In Progress card names as watched, through the episode
 * ensure route: one event with the click's time and a client event id. A
 * retry with the same id answers `already_satisfied`, so it never records a
 * second play; a new click is a new id, so a rewatch stays its own play.
 */
export async function markWatched(
	target: CheckTarget,
	click: Click,
	trackTime = true
): Promise<CheckOutcome> {
	const path =
		`/api/v1/media/tv/${encodeURIComponent(target.source)}/` +
		`${encodeURIComponent(target.media_id)}/episodes/ensure/`;
	let response: Response;
	try {
		response = await djangoWrite(path, 'POST', {
			events: [
				{
					season_number: target.season_number,
					episode_number: target.episode_number,
					watched_at: watchTime(click.at, trackTime),
					client_event_id: click.id
				}
			],
			...(target.library_media_type ? { library_media_type: target.library_media_type } : {})
		});
	} catch {
		return 'failed';
	}
	if (response.status === 503) return 'unavailable';
	if (!response.ok) return 'failed';
	const body = (await response.json().catch(() => null)) as {
		results?: { status?: string }[];
	} | null;
	const status = body?.results?.[0]?.status;
	if (status === 'created' || status === 'already_satisfied') return 'saved';
	return status === 'metadata_unavailable' ? 'unavailable' : 'failed';
}
