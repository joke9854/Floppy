import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import ShellHost from './ShellHost.test.svelte';

const library = [
	{ media_type: 'tv', label: 'TV Shows' },
	{ media_type: 'movie', label: 'Movies' },
	{ media_type: 'music', label: 'Music' }
];

describe('Shell', () => {
	it('wraps the page and links the web Library and the Django pages', async () => {
		render(ShellHost, { library });

		await expect.element(page.getByTestId('content')).toBeVisible();
		const links = document.querySelectorAll<HTMLAnchorElement>('nav a[href]');
		const hrefs = [...links].map((link) => link.getAttribute('href'));
		// The base path is empty under Vitest: /next/library/tv on a server.
		expect(hrefs).toContain('/library/tv');
		expect(hrefs).toContain('/library/movie');
		expect(hrefs).toContain('/library/music');
		expect(hrefs).toContain('/history');
		expect([...links].every((link) => link.hasAttribute('data-sveltekit-reload'))).toBe(true);
	});

	it('marks the rail attached with the hover mode by default', async () => {
		render(ShellHost, { library });

		const rail = document.querySelector('nav[data-ct-sidebar]');
		expect(rail?.getAttribute('data-ct-sidebar')).toBe('attached');
		expect(rail?.getAttribute('data-ct-floating')).toBe('hover');
	});

	it.each([
		['floating', 'expanded'],
		['floating', 'icons']
	])('marks the rail %s and %s', async (sidebarStyle, floatingSidebar) => {
		render(ShellHost, { library, sidebarStyle, floatingSidebar });

		const rail = document.querySelector('nav[data-ct-sidebar]');
		expect(rail?.getAttribute('data-ct-sidebar')).toBe(sidebarStyle);
		expect(rail?.getAttribute('data-ct-floating')).toBe(floatingSidebar);
	});

	it('opens the Library sheet from the phone bar', async () => {
		await page.viewport(390, 844);
		render(ShellHost, { library });

		await page.getByRole('button', { name: 'Library' }).click();

		const sheet = page.getByRole('dialog');
		await expect.element(sheet).toBeVisible();
		await expect
			.element(sheet.getByRole('link', { name: 'Movies' }))
			.toHaveAttribute('href', '/library/movie');
	});

	it('says so when no media type is on', async () => {
		await page.viewport(390, 844);
		render(ShellHost, { library: [] });

		await page.getByRole('button', { name: 'Library' }).click();

		await expect.element(page.getByText('No media types are turned on.')).toBeVisible();
	});
});
