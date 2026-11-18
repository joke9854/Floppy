import BookmarkPlus from '@lucide/svelte/icons/bookmark-plus';
import CircleCheckBig from '@lucide/svelte/icons/circle-check-big';
import OctagonX from '@lucide/svelte/icons/octagon-x';
import Pause from '@lucide/svelte/icons/pause';
import Play from '@lucide/svelte/icons/play';
import type { Component } from 'svelte';

/**
 * A tracking status as the Django cards draw it: the state icon, its text
 * colour on the Home chip, and the slug the Library badge colours by.
 */
export interface StatusLook {
	icon: Component;
	color: string;
	slug: string;
}

export const STATUS_LOOKS: Record<string, StatusLook> = {
	Completed: { icon: CircleCheckBig, color: 'text-emerald-400', slug: 'completed' },
	'In progress': { icon: Play, color: 'text-indigo-400', slug: 'in-progress' },
	Paused: { icon: Pause, color: 'text-orange-400', slug: 'paused' },
	Planning: { icon: BookmarkPlus, color: 'text-sky-400', slug: 'planning' },
	Dropped: { icon: OctagonX, color: 'text-red-400', slug: 'dropped' }
};
