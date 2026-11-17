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
	signOut: 'Sign out',
	signIn: 'Sign in',
	libraryEmpty: 'No media types are turned on.'
} as const;
