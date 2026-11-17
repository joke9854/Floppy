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
		`Mark ${title} S${season} E${episode} watched`
} as const;
