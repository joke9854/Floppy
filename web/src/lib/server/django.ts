/**
 * The bridge to Django (v2 P3-B). The SvelteKit server calls Django's
 * documented API on loopback with the visitor's own session cookie; it never
 * becomes a second API.
 *
 * Node's fetch drops a custom Host header, and Django needs the public host
 * (ALLOWED_HOSTS, absolute image URLs), so the call goes through node:http.
 */
import http from 'node:http';
import { Readable } from 'node:stream';

export const DJANGO_ORIGIN = process.env.FLOPPY_DJANGO_ORIGIN ?? 'http://127.0.0.1:8001';

/** Only these same-origin paths are Django's; nothing else gets the cookie. */
const DJANGO_PATHS = ['/api/', '/_allauth/'];

export function isDjangoPath(pathname: string): boolean {
	return DJANGO_PATHS.some((prefix) => pathname.startsWith(prefix));
}

interface Visitor {
	/** The page's own URL, as the visitor reached it. */
	url: URL;
	/** The visitor's address (from nginx's X-Real-IP). */
	address: string;
	/**
	 * The visitor's Cookie header. SvelteKit adds it only inside its own fetch,
	 * after handleFetch, so the bridge passes it on itself: the same cookies
	 * nginx would have sent Django for this site.
	 */
	cookie: string | null;
}

export interface DjangoCall {
	target: URL;
	method: string;
	headers: Record<string, string>;
}

/**
 * Describe the Django call for a request made with `event.fetch`, or null when
 * the request is not for Django (another origin, or a SvelteKit route).
 */
export function djangoCall(
	request: Request,
	visitor: Visitor,
	origin: string = DJANGO_ORIGIN
): DjangoCall | null {
	const url = new URL(request.url);
	if (url.origin !== visitor.url.origin || !isDjangoPath(url.pathname)) return null;

	const headers: Record<string, string> = {};
	request.headers.forEach((value, name) => {
		headers[name] = value;
	});
	// Django sees what nginx would have sent: the public host and scheme, and
	// the visitor's address (allauth refuses requests without it in production).
	if (visitor.cookie && !headers.cookie) headers.cookie = visitor.cookie;
	headers.host = visitor.url.host;
	headers['x-forwarded-proto'] = visitor.url.protocol.replace(':', '');
	headers['x-real-ip'] = visitor.address;
	delete headers['content-length'];

	return { target: new URL(url.pathname + url.search, origin), method: request.method, headers };
}

const NO_BODY_STATUSES = new Set([101, 204, 205, 304]);

/** Make the call with node:http and answer it as a fetch Response. Redirects are not followed. */
export function callDjango(call: DjangoCall, body: ReadableStream<Uint8Array> | null): Promise<Response> {
	return new Promise((resolve, reject) => {
		const outgoing = http.request(
			call.target,
			{ method: call.method, headers: call.headers },
			(incoming) => {
				const headers = new Headers();
				for (const [name, value] of Object.entries(incoming.headers)) {
					if (value === undefined) continue;
					for (const item of Array.isArray(value) ? value : [value]) headers.append(name, item);
				}
				const status = incoming.statusCode ?? 502;
				const stream = NO_BODY_STATUSES.has(status)
					? null
					: (Readable.toWeb(incoming) as ReadableStream<Uint8Array>);
				if (stream === null) incoming.resume();
				resolve(new Response(stream, { status, headers }));
			}
		);
		outgoing.on('error', reject);
		if (body) {
			Readable.fromWeb(body as import('node:stream/web').ReadableStream).pipe(outgoing);
		} else {
			outgoing.end();
		}
	});
}
