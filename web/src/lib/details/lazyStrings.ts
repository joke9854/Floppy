/**
 * The strings of the detail page's lazy dialogs (the sessions dialog, the
 * ratings graph) and the studio page (P4-L3b). Kept out of `strings.ts`, which
 * the detail page loads, so they cost nothing until opened.
 */
export const ls = {
	founded: (date: string) => `Founded ${date}`,
	website: 'Website',
	noTitles: 'No titles available.',
	activityHistory: 'Activity history',
	sessionsLoadFailed: 'The activity history could not load.',
	sessionsEmpty: 'No activity recorded.',
	sessionsCapped: (days: number) => `Showing the latest ${days} days.`,
	atAGlance: 'At a glance',
	editTracking: 'Edit tracking',
	viewSessions: 'View session history',
	ratingsGraph: 'Ratings graph',
	graphLoadFailed: 'The ratings graph could not load.',
	graphEmpty: 'No ratings stored yet.',
	graphKind: (kind: string) =>
		kind === 'trakt' ? 'Trakt ratings' : kind === 'imdb' ? 'IMDb ratings' : 'Ratings',
	loading: 'Loading…',
	graphCell: (score: number, votes: number | null) =>
		votes === null ? `${score}` : `${score} · ${votes.toLocaleString('en-US')} ${votes === 1 ? 'vote' : 'votes'}`
};
