import { expect, test } from '@playwright/test';

test('the app answers under /next', async ({ page }) => {
	await page.goto('/next');
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('Floppy');
});

test('the health route answers ok', async ({ request }) => {
	const response = await request.get('/next/health');
	expect(response.ok()).toBeTruthy();
	expect(await response.json()).toMatchObject({ status: 'ok' });
});
