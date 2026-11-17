import { describe, expect, it } from 'vitest';
import { playbackClock, playbackLeft, playbackPosition, type NowPlaying } from './playback.ts';

const playing = (status: string, offset: number, duration: number | null): NowPlaying => ({
	active: true,
	status,
	offset_seconds: offset,
	duration_seconds: duration,
	updated_at: '2026-11-17T21:00:00Z'
});

describe('Now Playing clock', () => {
	it('advances while playing, holds while paused, stops at the runtime', () => {
		const later = Date.parse('2026-11-17T21:00:30Z');

		expect(playbackPosition(playing('playing', 60, 3000), later)).toEqual({
			position: 90,
			duration: 3000
		});
		expect(playbackPosition(playing('paused', 60, 3000), later)).toEqual({
			position: 60,
			duration: 3000
		});
		expect(playbackPosition(playing('playing', 2990, 3000), later).position).toBe(3000);
	});

	it('formats like the Django pill', () => {
		expect(playbackClock(245)).toBe('4:05');
		expect(playbackClock(3723)).toBe('1:02:03');
		expect(playbackLeft(1800, 3000)).toBe('20 min');
		expect(playbackLeft(0, 3900)).toBe('1h 5m');
		expect(playbackLeft(10, 0)).toBeNull();
	});
});
