/**
 * Move to the new version: tell the waiting service worker to take over,
 * reload once it controls the page. Without a waiting worker (none
 * installed yet, or the browser has none) just reload.
 */
export async function reloadToNewVersion(): Promise<void> {
	const registration = await navigator.serviceWorker?.getRegistration();
	const waiting = registration?.waiting;
	if (!waiting) {
		location.reload();
		return;
	}
	navigator.serviceWorker.addEventListener('controllerchange', () => location.reload(), { once: true });
	waiting.postMessage('floppy-web:activate');
	// If the new worker never takes over, reload anyway.
	setTimeout(() => location.reload(), 4000);
}
