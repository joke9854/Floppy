import { error } from '@sveltejs/kit';
import { dev } from '$app/env';

/** The base components on one page, for review while developing only. */
export const load = () => {
	if (!dev) error(404, 'Not found');
};
