import { csrfToken } from '#lib/csrf.ts';
import { readAnswer, type SavedAnswer } from '../types.ts';

/** Post a multipart form (text fields plus one or more files) and read its JSON answer. */
export async function postUpload(url: string, fields: Record<string, string>, files: Record<string, File | File[] | null | undefined> = {}): Promise<SavedAnswer> {
	const body = new FormData();
	for (const [name, value] of Object.entries(fields)) body.append(name, value);
	for (const [name, file] of Object.entries(files)) {
		if (Array.isArray(file)) for (const item of file) body.append(name, item);
		else if (file) body.append(name, file);
	}
	const response = await fetch(url, {
		method: 'POST',
		credentials: 'same-origin',
		redirect: 'manual',
		headers: { 'x-csrftoken': await csrfToken(), accept: 'application/json' },
		body
	});
	return readAnswer(response);
}
