import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

/** Liveness of the Node server, for the container smoke test and nginx checks. */
export const GET: RequestHandler = () =>
	json({ status: 'ok', app: 'floppy-web' }, { headers: { 'cache-control': 'no-store' } });
