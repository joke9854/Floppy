import { redirect } from '@sveltejs/kit';
import type { Handle, HandleFetch } from '@sveltejs/kit/hooks';
import { callDjango, djangoCall } from '#lib/server/django.ts';
import { sessionUser } from '#lib/server/session.ts';
import { BASE } from '#lib/paths.ts';

/** The visitor's address from nginx (X-Real-IP); empty when the header is missing. */
function clientAddress(event: { getClientAddress(): string }): string {
	try {
		return event.getClientAddress();
	} catch {
		return '';
	}
}

/** Pages a signed-out visitor may open. */
const PUBLIC_PATHS = new Set(['/login']);

export const handle: Handle = async ({ event, resolve }) => {
	const path = event.url.pathname.slice(BASE.length).replace(/\/$/, '') || '/';
	if (path === '/health') return resolve(event);

	const isPublic = PUBLIC_PATHS.has(path);
	try {
		event.locals.user = await sessionUser(event.fetch, event.url.origin);
	} catch (failure) {
		// The sign-in page still opens when Django is not answering.
		if (!isPublic) throw failure;
		event.locals.user = null;
	}

	if (!event.locals.user && !isPublic) {
		const next = encodeURIComponent(event.url.pathname + event.url.search);
		redirect(303, `${BASE}/login?next=${next}`);
	}

	const response = await resolve(event);
	if (event.locals.user) {
		// A signed-in page is the visitor's own: never kept by a shared cache
		// or shown again from the back/forward history after signing out.
		response.headers.set('cache-control', 'private, no-store');
	}
	return response;
};

export const handleFetch: HandleFetch = async ({ event, request, fetch }) => {
	const call = djangoCall(request, {
		url: event.url,
		address: clientAddress(event),
		cookie: event.request.headers.get('cookie')
	});
	if (!call) return fetch(request);
	return callDjango(call, request.body);
};
