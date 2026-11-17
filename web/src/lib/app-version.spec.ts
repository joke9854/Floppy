import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { appVersion } from '../../scripts/app-version.js';

const roots: string[] = [];

function tree(files: Record<string, string>): string {
	const root = mkdtempSync(join(tmpdir(), 'floppy-web-version-'));
	roots.push(root);
	for (const [path, content] of Object.entries(files)) {
		mkdirSync(join(root, path, '..'), { recursive: true });
		writeFileSync(join(root, path), content);
	}
	return root;
}

afterEach(() => {
	for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true });
});

describe('appVersion', () => {
	it('is the same for the same files, wherever they are and whatever their line endings', () => {
		const a = tree({ 'src/app.html': '<html>\n</html>\n', 'package-lock.json': '{}' });
		const b = tree({ 'src/app.html': '<html>\r\n</html>\r\n', 'package-lock.json': '{}' });

		expect(appVersion(a)).toBe(appVersion(b));
		expect(appVersion(a)).toMatch(/^[0-9a-f]{16}$/);
	});

	it('changes when a web file changes, not for files outside the app', () => {
		const before = tree({ 'src/app.html': 'one', 'README.md': 'docs' });
		const edited = tree({ 'src/app.html': 'two', 'README.md': 'docs' });
		const docsOnly = tree({ 'src/app.html': 'one', 'README.md': 'other docs' });

		expect(appVersion(edited)).not.toBe(appVersion(before));
		expect(appVersion(docsOnly)).toBe(appVersion(before));
	});
});
