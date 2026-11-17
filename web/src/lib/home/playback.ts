import type { paths } from '#lib/api/client.ts';

export type NowPlaying =
	paths['/api/v1/playback/now-playing/']['get']['responses']['200']['content']['application/json'];

/** "1:02:03" or "4:05", as the Django pill's clock. */
export function playbackClock(totalSeconds: number): string {
	const clamped = Math.max(0, Math.floor(totalSeconds || 0));
	const hours = Math.floor(clamped / 3600);
	const minutes = Math.floor((clamped % 3600) / 60);
	const seconds = clamped % 60;
	if (hours > 0) {
		return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
	}
	return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

/**
 * Where playback is now: the reported offset, advanced by the time since the
 * report while it plays, capped at the runtime.
 */
export function playbackPosition(playing: NowPlaying, nowMs: number) {
	const duration = Math.max(0, playing.duration_seconds ?? 0);
	let position = Math.max(0, playing.offset_seconds ?? 0);
	if (playing.status === 'playing' && playing.updated_at) {
		position += Math.max(0, Math.floor((nowMs - Date.parse(playing.updated_at)) / 1000));
	}
	if (duration > 0) position = Math.min(position, duration);
	return { position, duration };
}

/** "20 min" or "1h 5m" left, or null without a runtime. */
export function playbackLeft(position: number, duration: number): string | null {
	if (duration <= 0) return null;
	const minutes = Math.max(0, Math.ceil((duration - position) / 60));
	const hours = Math.floor(minutes / 60);
	return hours > 0 ? `${hours}h ${minutes % 60}m` : `${minutes} min`;
}
