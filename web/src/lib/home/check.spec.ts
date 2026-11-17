import { beforeEach, describe, expect, it, vi } from 'vitest';

const djangoWrite = vi.fn();
vi.mock('#lib/csrf.ts', () => ({ djangoWrite }));

const { markWatched } = await import('./check.ts');

const target = {
	source: 'tmdb',
	media_id: '1668',
	season_number: 2,
	episode_number: 5,
	library_media_type: 'anime'
};

const answer = (status: number, body?: unknown) =>
	new Response(body === undefined ? null : JSON.stringify(body), { status });

describe('markWatched', () => {
	beforeEach(() => djangoWrite.mockReset());

	it('sends one event with the exact time and the client event id', async () => {
		djangoWrite.mockResolvedValue(answer(200, { results: [{ status: 'created' }] }));
		const at = new Date('2026-11-17T21:04:05.123Z');

		expect(await markWatched(target, 'b1e7f0a2-0000-4000-8000-000000000001', at)).toBe('saved');

		expect(djangoWrite).toHaveBeenCalledWith(
			'/api/v1/media/tv/tmdb/1668/episodes/ensure/',
			'POST',
			{
				events: [
					{
						season_number: 2,
						episode_number: 5,
						watched_at: '2026-11-17T21:04:05.123Z',
						client_event_id: 'b1e7f0a2-0000-4000-8000-000000000001'
					}
				],
				library_media_type: 'anime'
			}
		);
	});

	it('counts a retry the server already has as saved', async () => {
		djangoWrite.mockResolvedValue(answer(200, { results: [{ status: 'already_satisfied' }] }));

		expect(await markWatched(target, 'id')).toBe('saved');
	});

	it('tells a provider outage from other failures', async () => {
		djangoWrite.mockResolvedValueOnce(answer(503, { code: 'provider_unavailable' }));
		djangoWrite.mockResolvedValueOnce(
			answer(200, { results: [{ status: 'metadata_unavailable' }] })
		);
		djangoWrite.mockResolvedValueOnce(answer(200, { results: [{ status: 'not_found' }] }));
		djangoWrite.mockResolvedValueOnce(answer(403));
		djangoWrite.mockRejectedValueOnce(new TypeError('offline'));

		const outcomes = [];
		for (let i = 0; i < 5; i++) outcomes.push(await markWatched(target, `id-${i}`));

		expect(outcomes).toEqual(['unavailable', 'unavailable', 'failed', 'failed', 'failed']);
	});
});
