/**
 * The Calendar screen's strings (P4-F), worded as the Django page
 * (events/calendar.html and its components). They load with the screen only.
 */
export const ct = {
	title: 'Calendar',
	subtitle: 'Track upcoming releases from your list.',
	previousMonth: 'Previous month',
	nextMonth: 'Next month',
	goToToday: 'Go to Today',
	mediaTypes: 'Media Types',
	showAll: 'Show all',
	hideAll: 'Hide all',
	statusOf: (label: string) => `${label} Status`,
	backToTypes: 'Back to media types',
	calendarActions: 'Calendar Actions',
	fetchNewReleases: 'Fetch New Releases',
	downloadCalendar: 'Download Calendar',
	fetchFailed: 'That did not work. Try again.',
	gridView: 'Month grid',
	listView: 'List',
	agenda: 'Agenda',
	month: 'Month',
	today: 'Today',
	noUpcoming: 'No upcoming releases this month.',
	noReleasesDay: 'No releases scheduled for this day.',
	noReleasesFiltered: 'No releases for selected media types.',
	releases: (n: number) => (n === 1 ? '1 release' : `${n} releases`),
	exportLink: 'Export link',
	exportHelp: 'This link can be used to integrate your calendar into any of your calendar applications.',
	exportTypesHelp: 'Choose which media types to include in this calendar URL.',
	status: 'Status',
	exportStatusHelp: 'Choose which statuses to include in this calendar URL.',
	calendarUrl: 'Calendar URL'
} as const;
