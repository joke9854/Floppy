import { csrfToken, djangoForm } from '#lib/csrf.ts';
import { readAnswer, type SavedAnswer } from '../types.ts';

/** An answer with the fields Integrations forms add (the new token, once). */
export type IntegrationsAnswer = SavedAnswer & { new_token?: { name: string; secret: string } };

/**
 * Post one of the Integrations page's Django forms and read its JSON answer
 * (helpers.answers_json). A view that refuses with 404 fails the answer.
 */
export async function postForm(url: string, fields: Record<string, string | string[]> = {}): Promise<IntegrationsAnswer> {
	const response = await djangoForm(url, fields, { json: true });
	const copy = response.clone();
	const answer: IntegrationsAnswer = await readAnswer(response);
	if (answer.saved) {
		const body = (await copy.json().catch(() => ({}))) as { new_token?: { name: string; secret: string } };
		if (body.new_token) answer.new_token = body.new_token;
	}
	return answer;
}

/** Post a file upload form (multipart) and read its JSON answer. */
export async function postFile(url: string, field: string, file: File): Promise<IntegrationsAnswer> {
	const body = new FormData();
	body.append(field, file);
	const response = await fetch(url, {
		method: 'POST',
		credentials: 'same-origin',
		redirect: 'manual',
		headers: { 'x-csrftoken': await csrfToken(), accept: 'application/json' },
		body
	});
	return readAnswer(response);
}
