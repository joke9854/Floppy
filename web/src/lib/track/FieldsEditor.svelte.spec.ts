import { page } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import FieldsEditor from './FieldsEditor.svelte';

const schema = {
	save_url: '/collection/fields/save/',
	groups: [
		{
			id: 1,
			name: 'Shelf',
			fields: [{ id: 5, label: 'Room', field_type: 'select', options: ['Den', 'Attic'], media_types: ['episode'] }]
		}
	],
	field_types: [
		{ value: 'text', label: 'Text' },
		{ value: 'select', label: 'Select' }
	],
	media_types: [
		{ value: 'episode', label: 'Episode' },
		{ value: 'movie', label: 'Movie' }
	]
};

describe('custom field editor', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('saves the whole schema with a new field first, as the page', async () => {
		document.cookie = 'csrftoken=test-token';
		const saved = [{ id: 1, name: 'Shelf', fields: [] }];
		const fetch = vi.fn(async () => new Response(JSON.stringify({ success: true, groups: saved })));
		vi.stubGlobal('fetch', fetch);
		const onsaved = vi.fn();
		render(FieldsEditor, {
			props: { schema, itemId: 9, itemMediaType: 'episode', onsaved, oncancel: () => {} }
		});

		await page.getByRole('button', { name: 'Add field' }).click();
		await page.getByRole('textbox', { name: 'Field name' }).nth(1).fill('Edition');
		await page.getByRole('button', { name: 'Move Edition up' }).click();
		await expect.element(page.getByText('Unsaved changes')).toBeVisible();
		await page.getByRole('button', { name: 'Save Fields' }).click();

		await expect.poll(() => onsaved.mock.calls.length).toBe(1);
		expect(onsaved).toHaveBeenCalledWith(saved);
		const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toBe('/collection/fields/save/');
		expect(JSON.parse(String(init.body))).toEqual({
			item_id: 9,
			known_field_ids: [5],
			groups: [
				{
					id: 1,
					name: 'Shelf',
					fields: [
						{ id: null, label: 'Edition', field_type: 'text', media_types: ['episode'], options: [] },
						{ id: 5, label: 'Room', field_type: 'select', media_types: ['episode'], options: ['Den', 'Attic'] }
					]
				}
			]
		});
	});

	it('asks for a name before saving', async () => {
		vi.stubGlobal('fetch', vi.fn());
		render(FieldsEditor, {
			props: { schema, itemId: 9, itemMediaType: 'episode', onsaved: () => {}, oncancel: () => {} }
		});

		await page.getByRole('button', { name: 'Add group' }).click();
		await page.getByRole('button', { name: 'Save Fields' }).click();

		await expect.element(page.getByRole('alert')).toHaveTextContent('Every group needs a name.');
	});
});
