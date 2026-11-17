/** The app's base path (`/next` until the cutover; empty in tests). */
export const BASE: string = __FLOPPY_BASE__;

/**
 * Where to go after signing in: `next` when it is a path inside this app,
 * otherwise the app's start page. Never another site, and never a
 * protocol-relative (`//host`) or backslash path a browser would treat as one.
 */
export function safeNext(next: string | null | undefined, base: string = BASE): string {
	const home = `${base}/`;
	if (!next || !next.startsWith('/') || next.startsWith('//') || next.includes('\\')) return home;
	if (next !== base && !next.startsWith(`${base}/`)) return home;
	return next;
}
