// @ts-check
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

/** What the client build is made of; anything else does not change it. */
const INPUTS = ['src', 'static', 'package-lock.json', 'vite.config.ts', 'svelte.config.js'];

/** @param {string} path */
function files(path) {
	let stat;
	try {
		stat = statSync(path);
	} catch {
		return [];
	}
	if (stat.isFile()) return [path];
	return readdirSync(path, { recursive: true, withFileTypes: true })
		.filter((entry) => entry.isFile())
		.map((entry) => join(entry.parentPath, entry.name));
}

/**
 * The app version: a short hash of the web app's sources, static files,
 * lockfile and build config, the same for the same tree on any machine.
 * @param {string} root the web/ directory
 */
export function appVersion(root) {
	const hash = createHash('sha256');
	const paths = INPUTS.flatMap((input) => files(join(root, input)))
		.map((path) => relative(root, path).split(sep).join('/'))
		.sort();
	for (const path of paths) {
		hash.update(path);
		hash.update('\0');
		// Line endings normalised: a Windows checkout builds the same version.
		hash.update(readFileSync(join(root, path)).toString('binary').replace(/\r\n/g, '\n'));
		hash.update('\0');
	}
	return hash.digest('hex').slice(0, 16);
}
