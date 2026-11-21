/**
 * The track dialog's strings (P4-D1), worded as the Django dialog
 * (fill_track.html, date_time_picker.html). They load with the dialog, not
 * with every page (bundle budget); the shared ones stay in #lib/strings.ts.
 */
export const tt = {
	loading: 'Loading…',
	start: 'Start',
	end: 'End',
	startNow: 'Start Now',
	justFinished: 'Just Finished',
	releaseDateUnavailable: 'Release date unavailable',
	now: 'Now',
	copyFrom: (label: string) => `Copy from ${label}`,
	clearDate: 'Clear date',
	dateQuickActions: (label: string) => `${label} quick actions`,
	increase: (label: string) => `Increase ${label}`,
	decrease: (label: string) => `Decrease ${label}`,
	notes: 'Notes',
	koreaderId: 'KOReader document ID',
	koreaderPlaceholder: '32-character document hash',
	koreaderHelp:
		'Find this in KOReader under sync settings or document info. Required on official sync servers without metadata.',
	delete: 'Delete',
	since: 'Since',
	sinceHelp: 'Leave empty to start the rewatch today',
	rewatchingSince: (date: string) => `Rewatching since ${date}`,
	update: 'Update',
	trackDeleted: 'Deleted.',
	trackFixErrors: 'Check the highlighted fields.',
	trackSaveFailed: 'That did not save. Try again.',
	trackLoadFailed: 'The tracking form could not load.',
	trackProviderDown: 'The provider is not answering. Try again later.',
} as const;
