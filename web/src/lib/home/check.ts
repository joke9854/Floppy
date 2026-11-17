import { djangoWrite } from '#lib/csrf.ts';
import type { components } from '#lib/api/client.ts';

export type CheckTarget = components['schemas']['HomeCheckTarget'];

/** What a check click came to. */
export type CheckOutcome = 'saved' | 'failed' | 'unavailable';

/**
 * Mark the episode an In Progress card names as watched, through the episode
 * ensure route: one event with the click's exact time and a client event id.
 * A retry with the same id answers `already_satisfied`, so it never records a
 * second play; a new click is a new id, so a rewatch stays its own play.
 */
export async function markWatched(
	target: CheckTarget,
	clientEventId: string,
	watchedAt: Date = new Date()
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
					watched_at: watchedAt.toISOString(),
					client_event_id: clientEventId
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
