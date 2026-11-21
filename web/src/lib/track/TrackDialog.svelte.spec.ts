import { page } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import TrackDialog from './TrackDialog.svelte';

const field = (name: string, kind: string, value: string, extra: object = {}) => ({
	name,
	label: name.replace('_', ' ').replace(/^./, (c) => c.toUpperCase()),
	kind,
	value,
	choices: [],
	required: false,
	min: null,
	max: null,
	step: null,
	placeholder: '',
	help_text: '',
	...extra
});

const screen = {
	media_type: 'movie',
	title: 'The Matrix',
	subtitle: '',
	tracked: true,
	track_time: true,
	max_progress: null,
	hidden: [
		field('instance_id', 'hidden', '7'),
		field('media_id', 'hidden', '603'),
		field('source', 'hidden', 'tmdb'),
		field('media_type', 'hidden', 'movie')
	],
	fields: [
		field('score', 'number', '7', { min: '0', max: '10', step: '0.1' }),
		field('status', 'select', 'Completed', {
			choices: [
				{ value: '', label: 'No Status' },
				{ value: 'Completed', label: 'Completed' },
				{ value: 'Planning', label: 'Planning' }
			]
		}),
		field('start_date', 'datetime', '2026-03-04 20:01:07.123456'),
		field('end_date', 'datetime', '2026-03-04 22:17:59.654321')
	],
	notes: field('notes', 'textarea', 'Good'),
	koreader: null,
	date_suggestion: { label: 'Release Date', date: '1999-03-31', runtime_minutes: 136 },
	week_start: 'monday',
	save_url: '/media_save?next=%2Fdetails%2Ftmdb%2Fmovie%2F603%2Fthe-matrix',
	delete_url: '/media_delete?next=%2Fdetails%2Ftmdb%2Fmovie%2F603%2Fthe-matrix',
	save_as_new: 'Save as another play',
	rewatch: null,
	page_url: '/details/tmdb/movie/603/the-matrix'
};

describe('track dialog', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('posts the form back with untouched dates exactly as read', async () => {
		document.cookie = 'csrftoken=test-token';
		const fetch = vi.fn(async (url: string) =>
			url.startsWith('/api/v1/track/')
				? new Response(JSON.stringify(screen))
				: new Response(JSON.stringify({ saved: true, message: 'Updated The Matrix.', warnings: [] }))
		);
		vi.stubGlobal('fetch', fetch);
		const onsaved = vi.fn();
		render(TrackDialog, {
			props: { target: { mediaType: 'movie', source: 'tmdb', mediaId: '603' }, onclose: () => {}, onsaved }
		});

		await expect.element(page.getByRole('heading', { name: 'The Matrix' })).toBeVisible();
		await page.getByRole('spinbutton', { name: 'Score' }).fill('8.5');
		await page.getByRole('button', { name: 'Update' }).click();

		await expect.poll(() => onsaved.mock.calls.length).toBe(1);
		expect(onsaved).toHaveBeenCalledWith('Updated The Matrix.');
		const [url, init] = fetch.mock.calls[1] as unknown as [string, RequestInit];
		expect(url).toBe(screen.save_url);
		expect((init.headers as Record<string, string>).accept).toBe('application/json');
		const body = new URLSearchParams(String(init.body));
		expect(body.get('score')).toBe('8.5');
		expect(body.get('instance_id')).toBe('7');
		expect(body.get('start_date')).toBe('2026-03-04T20:01:07.123456');
		expect(body.get('end_date')).toBe('2026-03-04T22:17:59.654321');
		expect(body.get('notes')).toBe('Good');
	});

	it('queues episode plays from the Episode Plays tab', async () => {
		document.cookie = 'csrftoken=test-token';
		const episode = (order: number, number: number) => ({
			order,
			season_number: 1,
			episode_number: number,
			episode_title: `Episode ${number}`,
			selector_label: '',
			existing_play_count: 0,
			runtime_minutes: 47,
			air_date: '2008-01-20'
		});
		const withPlays = {
			...screen,
			media_type: 'tv',
			title: 'Breaking Bad',
			plays: {
				tab_label: 'Episode Plays',
				submit_label: 'Save plays',
				save_url: '/episode_bulk_save',
				mode_notice: '',
				hidden: [field('media_id', 'hidden', '1396'), field('media_type', 'hidden', 'tv')],
				first: { season_number: 1, episode_number: 1 },
				last: { season_number: 1, episode_number: 3 },
				write_mode: field('write_mode', 'select', 'add', {
					choices: [
						{ value: 'add', label: 'Add additional plays' },
						{ value: 'replace', label: 'Replace all plays' }
					]
				}),
				distribution_mode: field('distribution_mode', 'select', 'air_date', {
					choices: [
						{ value: 'air_date', label: 'Target air date' },
						{ value: 'even', label: 'Even distribution' }
					]
				}),
				start_date: field('start_date', 'datetime', '2026-03-01 20:00:00'),
				end_date: field('end_date', 'datetime', '2026-03-03 22:00:00'),
				seasons: [{ season_number: 1, season_title: 'Season 1' }],
				episodes: { '1': [episode(1, 1), episode(2, 2), episode(3, 3)] },
				locked_season_number: null,
				hide_season_selectors: false,
				labels: {
					first_selection: '',
					last_selection: '',
					season_field: '',
					episode_field: '',
					noun: '',
					noun_plural: '',
					target: '',
					date_shortcut: ''
				},
				missing_target_fallback: 'even'
			}
		};
		const fetch = vi.fn(async (url: string) =>
			url.startsWith('/api/v1/track/')
				? new Response(JSON.stringify(withPlays))
				: new Response(JSON.stringify({ queued: true, message: 'Adding plays to 2 episodes.', task_id: 'x' }))
		);
		vi.stubGlobal('fetch', fetch);
		const onsaved = vi.fn();
		render(TrackDialog, {
			props: { target: { mediaType: 'tv', source: 'tmdb', mediaId: '1396' }, onclose: () => {}, onsaved }
		});

		await page.getByRole('tab', { name: 'Episode Plays' }).click();
		await page.getByRole('combobox', { name: 'Episode' }).first().selectOptions('2');
		await expect
			.element(page.getByText('This will add plays for 2 ordered items using the target dates within the selected date range.'))
			.toBeVisible();
		await page.getByRole('button', { name: 'Save plays' }).click();

		await expect.poll(() => onsaved.mock.calls.length).toBe(1);
		expect(onsaved).toHaveBeenCalledWith('Adding plays to 2 episodes.');
		const [url, init] = fetch.mock.calls[1] as unknown as [string, RequestInit];
		expect(url).toBe('/episode_bulk_save');
		const body = new URLSearchParams(String(init.body));
		expect(Object.fromEntries(body)).toMatchObject({
			media_id: '1396',
			first_episode_number: '2',
			last_episode_number: '3',
			start_date: '2026-03-01T20:00',
			end_date: '2026-03-03T22:00',
			write_mode: 'add',
			distribution_mode: 'air_date',
			episode_count: '2'
		});
	});

	it('shows the form errors the page sends back', async () => {
		document.cookie = 'csrftoken=test-token';
		vi.stubGlobal(
			'fetch',
			vi.fn(async (url: string) =>
				url.startsWith('/api/v1/track/')
					? new Response(JSON.stringify(screen))
					: new Response(JSON.stringify({ saved: false, errors: { score: ['Enter a number.'] } }), {
							status: 400
						})
			)
		);
		render(TrackDialog, {
			props: {
				target: { mediaType: 'movie', source: 'tmdb', mediaId: '603' },
				onclose: () => {},
				onsaved: () => {}
			}
		});

		await page.getByRole('button', { name: 'Update' }).click();

		await expect.element(page.getByText('Enter a number.')).toBeVisible();
		await expect.element(page.getByRole('alert')).toHaveTextContent('Check the highlighted fields.');
	});
});
