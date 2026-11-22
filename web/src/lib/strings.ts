/**
 * Every shell string in one place, so translating the web (the Django pages
 * are translated per user) is a change here, not a hunt through components.
 */
export const t = {
	appName: 'Floppy',
	mainNav: 'Main',
	search: 'Search',
	home: 'Home',
	discover: 'Discover',
	calendar: 'Calendar',
	library: 'Library',
	lists: 'Lists',
	more: 'More',
	collection: 'Collection',
	tags: 'Tags',
	addEntry: 'Add custom entry',
	you: 'You',
	history: 'History',
	stats: 'Stats',
	settings: 'Settings',
	appearance: 'Appearance',
	notifications: 'Notifications',
	accountSettings: 'Account settings',
	signOut: 'Sign out',
	signIn: 'Sign in',
	libraryEmpty: 'No media types are turned on.',

	// Home (P4-A), worded as the Django Home.
	inProgress: 'In Progress',
	airingThisWeek: 'Airing This Week',
	recentlyWatched: 'Recently Watched',
	comingSoon: 'Coming Soon',
	all: 'All',
	movies: 'Movies',
	shows: 'Shows',
	filterInProgress: 'Filter In Progress by type',
	today: 'Today',
	premiere: 'Premiere',
	finale: 'Finale',
	rewatch: 'Rewatch',
	nowPlaying: 'Now Playing',
	paused: 'Paused',
	homeEmptyTitle: 'Nothing to show yet',
	homeEmptyBody: 'Track a show, anime or movie to see it here.',
	checkFailed: 'Not saved. Try again.',
	checkUnavailable: 'The provider is not answering. Try again later.',
	catchUp: (count: number, shows: number) =>
		`${count} ${count === 1 ? 'episode' : 'episodes'} to catch up on` +
		(shows > 1 ? ` across ${shows} shows` : ''),
	airingCount: (count: number) => `${count} airing this week`,
	episodesLeft: (count: number) => `${count} left`,
	timeLeft: (time: string) => `${time} left`,
	markWatched: (title: string, season: number, episode: number) =>
		`Mark ${title} S${season} E${episode} watched`,

	// Library (P4-B), worded as the Django Library.
	status: 'Status',
	sort: 'Sort',
	ascending: 'Ascending',
	descending: 'Descending',
	searchLibrary: 'Search',
	libraryViews: 'TV view',
	loadingMore: 'Loading more…',
	loadMoreFailed: 'More could not load. Scroll to try again.',
	libraryNoMatch: (title: string) => `No ${title.toLowerCase()} match.`,
	libraryCount: (count: number, title: string, inProgress: number) =>
		`${count} ${title.toLowerCase()}` + (inProgress ? ` · ${inProgress} in progress` : ''),

	// Library table, bulk select and card menu (P4-B3 to B5); the menus' own
	// strings load with them (#lib/library/menu-strings.ts).
	layout: 'Layout',
	grid: 'Grid',
	table: 'Table',
	viewSettings: 'View settings',
	shareFailed: 'The view could not be shared. Try again.',
	selectedCount: (count: number) => `${count} selected`,
	add: 'Add',
	bulkFailed: 'That did not work. Try again.',
	cardActions: (title: string) => `Actions for ${title}`,
	nextEp: 'Next ep',
	jumpToNextEpisode: 'Jump to next episode',


	// Detail page (P4-C1), worded as the Django movie and show page.
	back: 'Back',
	track: 'Track',
	unknown: 'Unknown',

	// Library filter menu (P4-B2), worded as the Django menu.
	filter: 'Filter',
	any: 'Any',
	active: 'Active',
	rating: 'Rating',
	progress: 'Progress',
	genre: 'Genre',
	impliedGenre: 'Implied Genre',
	date: 'Date',
	released: 'Released',
	source: 'Source',
	availability: 'Availability',
	language: 'Language',
	country: 'Country',
	platform: 'Platform',
	origin: 'Origin',
	format: 'Format',
	author: 'Author',
	streamingService: 'Streaming Service',
	tag: 'Tag',
	clearTags: 'Clear Tags',
	filterMode: 'Match any (OR), all (AND) or none (NOT)',
	filterOptions: (pane: string) => `Filter ${pane}`,
	releaseDate: 'Release Date',
	completedDate: 'Completed Date',
	from: 'From',
	to: 'To',
	apply: 'Apply',
	withinLast: 'Within the last',
	unit: 'Unit',

	// Detail page, P4-C2.
	close: 'Close',
} as const;
