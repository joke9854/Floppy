import { expect, test } from '@playwright/test';

// No Django here: these check what the web app answers on its own. The
// container smoke test signs in through nginx against the real Django.

test('the sign-in page opens even when Django is not answering', async ({ page }) => {
	await page.goto('/next/login');
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('Sign in');
});

test('the health route answers ok', async ({ request }) => {
	const response = await request.get('/next/health');
	expect(response.ok()).toBeTruthy();
	expect(await response.json()).toMatchObject({ status: 'ok' });
});
