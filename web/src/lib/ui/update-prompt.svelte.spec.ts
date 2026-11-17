import { page } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import UpdatePrompt from './UpdatePrompt.svelte';

describe('UpdatePrompt', () => {
	it('stays hidden until a new version is out', async () => {
		render(UpdatePrompt, { visible: false, onreload: () => {} });

		await expect.element(page.getByRole('status')).not.toBeInTheDocument();
	});

	it('reloads once when asked', async () => {
		const onreload = vi.fn();
		render(UpdatePrompt, { visible: true, onreload });

		await expect.element(page.getByText('A new version of Floppy is ready.')).toBeVisible();
		await page.getByRole('button', { name: 'Reload' }).click();

		expect(onreload).toHaveBeenCalledOnce();
		await expect.element(page.getByRole('button', { name: 'Reload' })).toBeDisabled();
	});
});
