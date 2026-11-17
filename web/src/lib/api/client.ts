import createClient from 'openapi-fetch';
import type { paths } from './schema';

/**
 * The typed client for Django's API, generated from the full OpenAPI contract
 * (`npm run api:types`). On the server pass `event.fetch` and the page's
 * origin: handleFetch sends the call to Django with the visitor's session.
 */
export function createApi(fetch: typeof globalThis.fetch, origin: string) {
	return createClient<paths>({ baseUrl: origin, fetch });
}
