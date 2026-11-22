/**
 * The History screen's strings (P4-E), worded as the Django page
 * (history.html, ct/history_header.html, ct/history_row.html). They load
 * with the screen only.
 */
export const ht = {
	title: 'History',
	all: 'All',
	mediaType: 'Media type',
	refreshing: 'Refreshing history in background...',
	dismiss: 'Dismiss',
	emptyTitle: 'No watch history yet',
	emptyBody: 'Start tracking movies and episodes to see them here.',
	loadMore: (n: number) => `Load more (${n} remaining)`,
	loadFailed: 'That did not load. Try again.',
	editTracking: 'Edit tracking',
	addToLists: 'Add to custom lists',
	added: 'Added to the list.',
	viewHistory: 'View your activity history',
	months: 'Months',
	previous: 'Previous',
	next: 'Next',
	page: (n: number) => `Page ${n}`,
	pages: 'Pages',
	filters: 'Filters',
	filterCount: (n: number) => `Filters (${n})`,
	filterHistory: 'Filter History',
	from: 'From',
	to: 'To',
	allTypes: 'All types',
	viewMode: 'View mode',
	activity: 'Activity (watched)',
	releases: 'Release dates',
	genre: 'Genre',
	allGenres: 'All genres',
	impliedGenre: 'Implied Genre',
	clearFilters: 'Clear filters',
	apply: 'Apply'
} as const;
