/** Settings (P4-J), worded as the Django pages (users/*.html). */
export const st = {
	settings: 'Settings',
	sections: 'Settings sections',
	saved: 'Saved.',
	failed: 'That did not work. Try again.',
	demo: 'This section is view-only for demo accounts.',

	// Account (account.html)
	profile: 'Profile Information',
	username: 'Username',
	saveChanges: 'Save Changes',
	usernameSaved: 'Your username has been updated!',
	changePassword: 'Change Password',
	currentPassword: 'Current Password',
	newPassword: 'New Password',
	confirmPassword: 'Confirm New Password',
	updatePassword: 'Update Password',
	passwordSaved: 'Your password has been updated!',
	recovery: 'Account Recovery & Authenticator',
	recoveryNote:
		'Floppy cannot send password reset emails or text messages. Authenticator codes, recovery codes, or an admin password reset in the container terminal are the only recovery options.',
	authenticatorOn: 'Authenticator app is enabled.',
	authenticatorOff: 'Authenticator app is not set up.',
	unusedCodes: 'Unused recovery codes:',
	manageAuthenticator: 'Manage authenticator and recovery codes',
	thirdParty: 'Third-Party Connections',
	thirdPartyNote: 'Manage your connected third-party accounts for easier sign-in.',
	manageConnections: 'Manage Account Connections',

	// Appearance (appearance.html)
	sidebar: 'Sidebar',
	sidebarNote: 'Floating applies on screens 1024 px and wider; phones always use the bottom tab bar.',
	floating: 'Floating behaviour',
	appearance: 'Appearance',
	saveAppearance: 'Save appearance',
	appearanceSaved: 'Appearance updated',
	changesAfterSaving: 'Changes apply after saving.',

	// Notifications (notifications.html)
	notifications: 'Notifications',
	notificationsNote: 'Configure how you want to receive notifications about your media.',
	appriseUrls: 'Apprise URLs',
	appriseHelp: 'Enter one URL per line, for example discord://webhook_id/webhook_token or notifiarr://api_key.',
	appriseMore: 'Apprise supports many platforms, including Discord, Notifiarr, Telegram, Slack, Email, Pushover and ntfy.',
	notificationSettings: 'Notification Settings',
	dailyDigest: 'Enable Daily Digest',
	dailyDigestNote: 'Receive a single notification each day with all media scheduled to release that day',
	releases: 'Receive notifications for recently released media',
	releasesNote: 'Get notified when new episodes, chapters, or other media are released',
	premieres: 'Enable Premiere Digest',
	premieresNote: 'Receive a weekly digest of new show and season premieres',
	testNotifications: 'Test Notifications',
	testSent: 'Test notification sent successfully!',
	saveSettings: 'Save Settings',
	notificationsSaved: 'Notification settings updated successfully!',
	excluded: 'Excluded Media Items',
	excludedNote: 'Exclude specific media items from notifications:',
	searchExclude: 'Search for media to exclude...',
	exclude: 'Exclude',
	include: 'Remove from exclusions',
	noMatches: 'No matching items found',
	currentlyExcluded: 'Currently Excluded:',
	noneExcluded: 'No media items excluded yet',
	rssFeeds: 'RSS feeds for Discover rows',

	// Media types (sidebar.html)
	mediaTypesNote: 'Customize the look and behavior of the user interface.',
	hideOverlay: 'Hide Hover Overlay on Touch Devices',
	hideOverlayNote:
		'Hide the media card hover overlay with action buttons on touch devices for a cleaner mobile experience. On desktop, the overlay will still appear when you hover your mouse over media cards.',
	mediaTypes: 'Media Types',
	mediaTypesHelp:
		'Control which media types are visible throughout the app (sidebar, search, calendar, notifications). Use the arrows to set their sidebar order.',
	moveUp: 'Move up',
	moveDown: 'Move down',
	savePreferences: 'Save Preferences',
	mediaTypesSaved: 'Settings updated successfully.',
	noChanges: 'No changes to save.',

	// About (about.html)
	about: 'About Floppy',
	description: 'Description',
	descriptionBody:
		'Floppy is an open-source, self-hosted media tracker and personal diary. Track, rate, and organize movies, shows, video games, books, music, podcasts, anime, comics, and more in one unified place.',
	forkNote: 'Floppy began as a fork of Yamtrack and has diverged substantially since. Yamtrack CSV exports import directly.',
	editionNote:
		'This server runs the CineTrack edition of Floppy, maintained at joke9854/Floppy. It adds the sync API used by CineTrack and Nuvio, built on Floppy by dannyvfilms.',
	install: 'Install Floppy',
	installNote: 'Floppy is an installable PWA. Add it to your Home Screen to launch it like an app directly from your browser.',
	installSteps:
		"On iPhone and iPad: Share, then Add to Home Screen. On Android: the browser menu, then Install app. On a computer: the install icon in the address bar.",
	resources: 'Project Resources',
	specs: 'Developer & API Specifications',
	open: 'Open',
	download: 'Download',
	license: 'License & Legal',
	licenseBody: 'Floppy is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).',
	viewLicense: 'View License',
	version: 'Version:',
	newTab: '(opens in a new tab)'
};

/** About's links (about.html), in the page's order. */
export const ABOUT_RESOURCES = [
	{
		name: 'Upstream Website',
		purpose: "Floppy's official site: guides and release announcements for upstream Floppy",
		href: 'https://dannyvfilms.github.io/floppy/',
		action: 'Visit Site'
	},
	{
		name: 'Source Code',
		purpose: "This edition's GitHub repository: the CineTrack sync API, pull requests and history",
		href: 'https://github.com/joke9854/Floppy',
		action: 'GitHub'
	},
	{
		name: 'Upstream Documentation',
		purpose: "Floppy's wiki: container deployment, reverse proxy setup, and guides",
		href: 'https://github.com/dannyvfilms/Floppy/wiki',
		action: 'Open Wiki'
	},
	{
		name: 'Bug Reports',
		purpose: 'Report bugs in this edition, submit sanitized logs, and request features',
		href: 'https://github.com/joke9854/Floppy/issues',
		action: 'Issues'
	},
	{
		name: 'Upstream Discord',
		purpose: "Floppy's community: homelab users, setups, and live help",
		href: 'https://discord.gg/uFgha7Kb6n',
		action: 'Join Discord'
	}
];
