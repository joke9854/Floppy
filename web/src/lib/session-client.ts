import { goto } from '$app/navigation';
import { djangoWrite } from '#lib/csrf.ts';
import { BASE } from '#lib/paths.ts';

/** Sign out at allauth (it answers 401 once the session is gone), then show sign-in. */
export async function signOut(): Promise<void> {
	await djangoWrite('/_allauth/browser/v1/auth/session', 'DELETE');
	await goto(`${BASE}/login`, { invalidateAll: true });
}
