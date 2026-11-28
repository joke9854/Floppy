import { describe, expect, it } from 'vitest';
import { detailApiPath, episodeApiPath, formWatchNow, seasonApiPath } from './api.ts';

describe('detail API paths', () => {
	it('names the three reads', () => {
		expect(detailApiPath('movie', 'tmdb', '238')).toBe('/api/v1/details/movie/tmdb/238/');
		expect(detailApiPath('tv', 'tmdb', '1399', 'sections', '2')).toBe(
			'/api/v1/details/tv/tmdb/1399/sections/?season=2'
		);
		expect(detailApiPath('comic', 'comicvine', '4050-1', 'sections', null, 2)).toBe(
			'/api/v1/details/comic/comicvine/4050-1/sections/?episode_page=2'
		);
		expect(seasonApiPath('tv', 'tmdb', '1399', 'season=2&episode_page=2')).toBe(
			'/api/v1/details/tv/tmdb/1399/season/?season=2&episode_page=2'
		);
		expect(seasonApiPath('anime', 'tmdb', '1', 'season=1')).toBe(
			'/api/v1/details/anime/tmdb/1/season/?season=1'
		);
		expect(episodeApiPath('tmdb', '1', 1, 2, 'anime')).toBe(
			'/api/v1/details/episode/tmdb/1/1/2/?parent=anime'
		);
	});
});

describe('formWatchNow', () => {
	it('sends the local wall time, or the date when the instance keeps dates only', () => {
		const at = new Date(2026, 10, 18, 9, 5, 7);
		expect(formWatchNow(at, true)).toBe('2026-11-18T09:05:07');
		expect(formWatchNow(at, false)).toBe('2026-11-18');
	});
});
