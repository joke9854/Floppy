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

	it('hides a title from Discover on the Discover tab', async () => {
		document.cookie = 'csrftoken=test-token';
		const fetch = vi.fn(async (url: string) =>
			url.startsWith('/api/v1/track/')
				? new Response(
						JSON.stringify({ ...screen, discover: { item_id: 42, hidden: false, save_url: '/discover/toggle-hidden/' } })
					)
				: new Response(JSON.stringify({ hidden: true, message: 'Hidden "The Matrix" from Discover.' }))
		);
		vi.stubGlobal('fetch', fetch);
		const onsaved = vi.fn();
		render(TrackDialog, {
			props: { target: { mediaType: 'movie', source: 'tmdb', mediaId: '603' }, onclose: () => {}, onsaved }
		});

		await page.getByRole('tab', { name: 'Discover' }).click();
		await expect.element(page.getByRole('button', { name: 'Save' })).toBeDisabled();
		await page.getByRole('combobox', { name: 'Status' }).selectOptions('hidden');
		await page.getByRole('button', { name: 'Save' }).click();

		await expect.poll(() => onsaved.mock.calls.length).toBe(1);
		expect(onsaved).toHaveBeenCalledWith('Hidden "The Matrix" from Discover.');
		const [url, init] = fetch.mock.calls[1] as unknown as [string, RequestInit];
		expect(url).toBe('/discover/toggle-hidden/');
		expect(Object.fromEntries(new URLSearchParams(String(init.body)))).toMatchObject({ item_id: '42', action: 'hide' });
	});

	it('adds and removes owned copies on the Collection tab', async () => {
		document.cookie = 'csrftoken=test-token';
		const withCollection = {
			...screen,
			media_type: 'episode',
			collection: {
				item_id: 9,
				save_url: '/collection/add/?next=%2Fdetails',
				add_label: 'Add Another Copy',
				fields: [
					field('media_type', 'select', '', {
						label: 'Format',
						choices: [
							{ value: '', label: 'Select' },
							{ value: 'Blu-ray', label: 'Blu-ray' }
						]
					}),
					field('is_3d', 'checkbox', '', { label: '3D' }),
					field('purchase_price', 'number', '', { label: 'Purchase Price', step: '0.01', min: '0' })
				],
				custom_groups: [
					{
						name: 'Shelf',
						fields: [
							field('custom_field_1', 'checkbox', '', { label: 'Boxed' }),
							field('custom_field_2', 'select', 'Attic', {
								label: 'Room',
								choices: [
									{ value: '', label: 'Select' },
									{ value: 'Attic', label: 'Attic' }
								]
							})
						]
					}
				],
				entries: [{ id: 5, lines: ['Format: DVD'], remove_url: '/collection/5/remove/' }]
			}
		};
		const fetch = vi.fn(async (url: string) =>
			url.startsWith('/api/v1/track/')
				? new Response(JSON.stringify(withCollection))
				: new Response(JSON.stringify({ saved: true, message: 'Added Pilot to collection' }))
		);
		vi.stubGlobal('fetch', fetch);
		const onsaved = vi.fn();
		render(TrackDialog, {
			props: { target: { mediaType: 'episode', source: 'tmdb', mediaId: '1' }, onclose: () => {}, onsaved }
		});

		await page.getByRole('tab', { name: 'Collection' }).click();
		await expect.element(page.getByText('Format: DVD')).toBeVisible();
		await page.getByRole('button', { name: 'Remove collection entry' }).click();
		await expect.poll(() => onsaved.mock.calls.length).toBe(1);
		expect(fetch.mock.calls[1]?.[0]).toBe('/collection/5/remove/');

		await page.getByRole('combobox', { name: 'Format' }).selectOptions('Blu-ray');
		await page.getByRole('checkbox', { name: '3D' }).click();
		await page.getByRole('button', { name: 'Increase Purchase Price' }).click();
		await page.getByRole('button', { name: 'Add Copy' }).click();

		await expect.poll(() => onsaved.mock.calls.length).toBe(2);
		const [url, init] = fetch.mock.calls[2] as unknown as [string, RequestInit];
		expect(url).toBe('/collection/add/?next=%2Fdetails');
		expect((init.headers as Record<string, string>).accept).toBe('application/json');
		const body = Object.fromEntries(new URLSearchParams(String(init.body)));
		expect(body).toEqual({
			item_id: '9',
			media_type: 'Blu-ray',
			is_3d: 'on',
			purchase_price: '0.01',
			custom_field_2: 'Attic'
		});
	});

	it('saves the language on the Metadata tab and sends the image with the General form', async () => {
		document.cookie = 'csrftoken=test-token';
		const withMetadata = {
			...screen,
			metadata: {
				provider: null,
				language: {
					save_url: '/details/language/tmdb/movie/603',
					value: '',
					options: [
						{ value: '', label: 'Server Default (en-US)' },
						{ value: 'it-IT', label: 'Italian' }
					]
				},
				image: {
					field: field('image_url', 'text', 'http://example.com/m.jpg', { label: 'Image URL' }),
					save_url: '/details/image/7'
				},
				custom: null
			}
		};
		const fetch = vi.fn(async (url: string) =>
			url.startsWith('/api/v1/track/')
				? new Response(JSON.stringify(withMetadata))
				: new Response(JSON.stringify({ saved: true, message: 'Done.', warnings: [] }))
		);
		vi.stubGlobal('fetch', fetch);
		const onsaved = vi.fn();
		render(TrackDialog, {
			props: { target: { mediaType: 'movie', source: 'tmdb', mediaId: '603' }, onclose: () => {}, onsaved }
		});

		await page.getByRole('tab', { name: 'Metadata' }).click();
		await page.getByRole('combobox', { name: 'Metadata Language' }).selectOptions('it-IT');
		await page.getByRole('button', { name: 'Save Language' }).click();
		await expect.poll(() => onsaved.mock.calls.length).toBe(1);
		const [languageUrl, languageInit] = fetch.mock.calls[1] as unknown as [string, RequestInit];
		expect(languageUrl).toBe('/details/language/tmdb/movie/603');
		expect(Object.fromEntries(new URLSearchParams(String(languageInit.body)))).toEqual({ language: 'it-IT' });

		await page.getByRole('textbox', { name: 'Image URL' }).fill('http://example.com/new.jpg');
		await page.getByRole('tab', { name: 'General' }).click();
		await page.getByRole('button', { name: 'Update' }).click();
		await expect.poll(() => onsaved.mock.calls.length).toBe(2);
		const [saveUrl, saveInit] = fetch.mock.calls[2] as unknown as [string, RequestInit];
		expect(saveUrl).toBe(screen.save_url);
		expect(new URLSearchParams(String(saveInit.body)).get('image_url')).toBe('http://example.com/new.jpg');
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
