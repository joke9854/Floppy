// See https://svelte.dev/docs/kit/types#app.d.ts
import type { SessionUser } from '#lib/server/session.ts';

declare global {
	/** The app's base path, from vite.config.ts (`/next`, empty in tests). */
	const __FLOPPY_BASE__: string;

	namespace App {
		interface Locals {
			/** The signed-in user (allauth headless), or null. */
			user: SessionUser | null;
		}
	}
}

export {};
