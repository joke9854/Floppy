import type { Component } from 'svelte';

/**
 * Menus kept out of the Library's first load (bundle budget): each module is
 * fetched once, on the first hover, focus or tap of its button.
 */
const loading = new Map<string, Promise<Component<never>>>();

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function lazyComponent<P extends Record<string, any>>(key: string, load: () => Promise<{ default: unknown }>): Promise<Component<P>> {
	let promise = loading.get(key);
	if (!promise) {
		promise = load().then((module) => module.default as Component<never>);
		loading.set(key, promise);
	}
	return promise as unknown as Promise<Component<P>>;
}
