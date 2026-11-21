const SESSION_PATH = '/_allauth/browser/v1/auth/session';

function cookie(name: string): string | null {
	for (const part of document.cookie.split(';')) {
		const [key, ...value] = part.trim().split('=');
		if (key === name) return decodeURIComponent(value.join('='));
	}
	return null;
}

/**
 * Django's CSRF token for a write from the browser. allauth's session
 * endpoint sets the cookie when there is none yet.
 */
export async function csrfToken(): Promise<string> {
	let token = cookie('csrftoken');
	if (!token) {
		await fetch(SESSION_PATH, { credentials: 'same-origin' });
		token = cookie('csrftoken');
	}
	if (!token) throw new Error('No CSRF token');
	return token;
}

/** A same-origin JSON write to Django with the CSRF token. */
export async function djangoWrite(path: string, method: string, body?: unknown): Promise<Response> {
	return fetch(path, {
		method,
		credentials: 'same-origin',
		headers: {
			'content-type': 'application/json',
			'x-csrftoken': await csrfToken()
		},
		body: body === undefined ? undefined : JSON.stringify(body)
	});
}

/**
 * A same-origin form POST to a Django view (its views read `request.POST`),
 * with the CSRF token. `redirect: 'manual'` keeps a view that answers with a
 * redirect from loading the Django page behind it.
 */
export async function djangoForm(
	path: string,
	fields: Record<string, string | string[]>,
	{ json = false }: { json?: boolean } = {}
): Promise<Response> {
	const body = new URLSearchParams();
	for (const [key, value] of Object.entries(fields)) {
		for (const item of Array.isArray(value) ? value : [value]) body.append(key, item);
	}
	const headers: Record<string, string> = { 'x-csrftoken': await csrfToken() };
	// The track views (P4-D) answer this with JSON instead of a redirect.
	if (json) headers.accept = 'application/json';
	return fetch(path, { method: 'POST', credentials: 'same-origin', redirect: 'manual', headers, body });
}
