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

test('the service worker serves the app offline and shows an offline page', async ({ page, context }) => {
	await page.goto('/next/login');
	const scope = await page.evaluate(async () => (await navigator.serviceWorker.ready).scope);
	expect(new URL(scope).pathname).toBe('/next/');
	await page.waitForFunction(() => navigator.serviceWorker.controller !== null);

	await context.setOffline(true);
	try {
		// A file of this build comes from the worker's cache.
		const cssLoads = await page.evaluate(async () => {
			const href = document.querySelector<HTMLLinkElement>('link[rel="stylesheet"]')?.href;
			return href ? (await fetch(href)).ok : false;
		});
		expect(cssLoads).toBe(true);

		// A page load gets the offline page, never a stored copy of a page.
		await page.goto('/next/login');
		await expect(page.getByRole('heading', { level: 1 })).toHaveText('You are offline');
	} finally {
		await context.setOffline(false);
	}
});

test('the worker script and version file are not behind sign-in or long-lived caching', async ({ request }) => {
	const worker = await request.get('/next/service-worker.js', { maxRedirects: 0 });
	expect(worker.status()).toBe(200);
	expect(worker.headers()['cache-control'] ?? '').not.toContain('immutable');

	const version = await request.get('/next/_app/version.json', { maxRedirects: 0 });
	expect(version.status()).toBe(200);
	expect(await version.json()).toHaveProperty('version');
});
