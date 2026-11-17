import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import Login from './+page.svelte';

describe('/next/login', () => {
	it('asks for a username and password', async () => {
		render(Login, { props: { data: { next: '/' } } as never });

		await expect.element(page.getByRole('heading', { level: 1 })).toHaveTextContent('Sign in');
		await expect.element(page.getByLabelText('Username')).toBeVisible();
		await expect.element(page.getByLabelText('Password')).toBeVisible();
		await expect
			.element(page.getByRole('link', { name: 'Use a recovery code' }))
			.toHaveAttribute('href', '/accounts/password/recover/');
	});
});
