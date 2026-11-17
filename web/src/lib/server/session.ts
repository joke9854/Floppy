import { error } from '@sveltejs/kit';

export const SESSION_PATH = '/_allauth/browser/v1/auth/session';

export interface SessionUser {
	id: number;
	username: string;
	display: string;
}

/**
 * The signed-in user, from allauth headless, or null when signed out.
 * `fetch` is the request's own `event.fetch`, so the visitor's cookie goes
 * along (handleFetch routes it to Django).
 */
export async function sessionUser(fetch: typeof globalThis.fetch, origin: string): Promise<SessionUser | null> {
	let response: Response;
	try {
		response = await fetch(new URL(SESSION_PATH, origin));
	} catch (failure) {
		// The reason only: never the request, which carries the session cookie.
		console.error(`[web] Session check failed: ${failure instanceof Error ? failure.message : failure}`);
		error(503, "Floppy's server is not answering. Try again in a moment.");
	}
	if (response.status === 401) return null;
	if (!response.ok) error(503, "Floppy's server could not check your sign-in. Try again in a moment.");
	const body = (await response.json()) as { data?: { user?: SessionUser } };
	return body.data?.user ?? null;
}
