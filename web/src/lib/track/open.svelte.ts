import { mount } from 'svelte';

/**
 * Opening the track dialog (P4-D1). A Track button calls `openTrack`, which
 * mounts the dialog's host on the first tap: no page or layout carries the
 * dialog (bundle budget), only this module.
 */
export type TrackTarget = {
	mediaType: string;
	source: string;
	mediaId: string;
	season?: number | null;
	episode?: number | null;
	instanceId?: number | null;
};

export const trackRequest = $state<{ target: TrackTarget | null; notice: string }>({
	target: null,
	notice: ''
});

let host: Promise<unknown> | null = null;

export function openTrack(target: TrackTarget): void {
	trackRequest.notice = '';
	trackRequest.target = target;
	host ??= import('./TrackHost.svelte').then(({ default: TrackHost }) =>
		mount(TrackHost, { target: document.body })
	);
}
