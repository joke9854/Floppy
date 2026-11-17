import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import Page from './+page.svelte';

describe('/next', () => {
	it('shows who is signed in', async () => {
		render(Page, {
			props: { data: { account: { username: 'reader', authenticator_enabled: false } } } as never
		});

		await expect.element(page.getByRole('heading', { level: 1 })).toHaveTextContent('Floppy');
		await expect.element(page.getByTestId('username')).toHaveTextContent('reader');
		await expect.element(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
	});
});
