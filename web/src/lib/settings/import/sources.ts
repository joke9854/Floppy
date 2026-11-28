/**
 * The Import sources the web draws (P4-K1), worded as import_data.html.
 * Every form also posts the page's Import Settings as `frequency`, `time`
 * and `mode` (the views read them; several fail without them).
 *
 * Kinds:
 * - `file`: one file input; uploads only run with frequency "once".
 * - `files`: several optional file inputs and an Import button (TV Time).
 * - `username`: a text field `user`; "once" queues, otherwise it schedules.
 * - `mdblist`: an API key field (`api_key`) unless an account is connected.
 * - `hardcover`: an optional API key (`hardcover_api_key`) and/or a CSV.
 * - `simkl`: leaves for Simkl's sign-in (a real form submit, not fetch),
 *   with `next` set so it comes back to the web Import page.
 * - `trakt`, `anilist` (K2): a public username import, or OAuth (a real
 *   form submit like Simkl); Trakt also takes a data export (`trakt_export`,
 *   several files, frequency "once" only, not mode-gated).
 * - `account` (K2): connect once, then Sync now / full history / Disconnect
 *   (see `ImportAccount`). None of these is mode-gated.
 * - `plex`, `arr` (Radarr, Sonarr), `storyteller`, `koreader` (K3): their
 *   own panels (see the screen's `plex`, `radarr`/`sonarr`,
 *   `storyteller_pending` and `koreader`).
 */
export type ImportUrlKey =
	| 'yamtrack'
	| 'clz'
	| 'hltb'
	| 'grouvee'
	| 'imdb'
	| 'goodreads'
	| 'hardcover'
	| 'storygraph'
	| 'tvtime'
	| 'mal'
	| 'kitsu'
	| 'mdblist'
	| 'simkl'
	| 'steam';

/** The K2 accounts on the screen (`accounts.<key>`) and their `urls.<key>_connect|_disconnect|_sync|_history`. */
export type ImportAccountKey = 'lastfm' | 'koito' | 'xbox' | 'psn' | 'pocketcasts' | 'gpodder' | 'stremio' | 'audiobookshelf';

export type ImportConnectField = {
	name: string;
	label: string;
	type: 'text' | 'url' | 'email' | 'password';
	placeholder: string;
	required: boolean;
	/** The field's starting value (GPodder's server). */
	value?: string;
	/** A help line under the field. */
	hint?: string;
};

export type ImportLink = { label: string; href: string };

/** What a page-level value the account texts depend on. */
export type ImportAccountContext = { frequency: string; pollInterval: number; absPollInterval: number };

/**
 * An account source (import_data.html's Last.fm, Koito, Xbox, PSN, Pocket
 * Casts and GPodder dialogs). Connect posts `connectFields` (plus the page's
 * frequency/time/mode when `connectPostsShared`); Sync posts the trio when
 * `syncPostsShared`. The connect views call the provider before answering.
 */
export type ImportAccount = {
	key: ImportAccountKey;
	connectFields: ImportConnectField[];
	connectButton: string;
	connectPostsShared: boolean;
	syncPostsShared: boolean;
	/** The text when no account is saved. */
	disconnected: (context: ImportAccountContext) => string;
	/** The text when an account is saved. */
	connected: (context: ImportAccountContext) => string;
	syncLabel: (context: ImportAccountContext) => string;
	/** The label before `accounts.<key>.name` (Koito's server, gamertag, online ID). */
	nameLabel?: string;
	/** Links shown under the not-connected text. */
	links?: ImportLink[];
	/** A note under the connect form, or under both branches with `footnoteAlways`. */
	footnote?: string;
	footnoteAlways?: boolean;
	history?: boolean;
	/** When the connect button can be used, if not "every required field is filled". */
	connectReady?: (values: Record<string, string>) => boolean;
};

export type ImportFileField = { name: string; label: string; accept: string; title?: string };

export type ImportSource = {
	key: string;
	/** Where the file and username kinds post. */
	url?: ImportUrlKey;
	kind: 'file' | 'files' | 'username' | 'mdblist' | 'hardcover' | 'simkl' | 'trakt' | 'anilist' | 'account' | 'plex' | 'arr' | 'storyteller' | 'koreader';
	/** The text above the form when the frequency is "once" (uploads) or always. */
	description: string;
	files?: ImportFileField[];
	/** username kind: the field's placeholder and an optional hint. */
	placeholder?: string;
	hint?: string;
	button?: string;
	docs?: boolean;
	account?: ImportAccount;
};

const consoleSync = ({ frequency }: ImportAccountContext) => (frequency === 'once' ? 'Sync Now' : 'Schedule Sync');
const consoleText =
	(name: string) =>
	({ frequency }: ImportAccountContext) =>
		frequency === 'once'
			? `Sync played games and hours played from your ${name} account now.`
			: `Sync played games and hours played from your ${name} account on a schedule.`;

export const PERIODIC_UPLOAD_NOTE = 'File uploads are not available for periodic imports';

export const IMPORT_SOURCES: Record<string, ImportSource> = {
	yamtrack: {
		key: 'yamtrack',
		url: 'yamtrack',
		kind: 'file',
		description: 'Import a Floppy backup (media + lists)',
		files: [{ name: 'yamtrack_csv', label: 'Select CSV File', accept: '.csv' }],
		docs: true
	},
	yamtrack_native: {
		key: 'yamtrack_native',
		url: 'yamtrack',
		kind: 'file',
		description: 'Import a CSV exported from Yamtrack (media + lists)',
		files: [{ name: 'yamtrack_csv', label: 'Select CSV File', accept: '.csv' }],
		docs: true
	},
	clz: {
		key: 'clz',
		url: 'clz',
		kind: 'file',
		description:
			'Import a CLZ CSV or XML export. Columns Floppy has no built-in home for become custom collection fields.',
		files: [{ name: 'clz_export', label: 'Select CLZ Export', accept: '.csv,.txt,.xml' }]
	},
	hltb: {
		key: 'hltb',
		url: 'hltb',
		kind: 'file',
		description: 'Import games',
		files: [{ name: 'hltb_csv', label: 'Select CSV File', accept: '.csv' }]
	},
	grouvee: {
		key: 'grouvee',
		url: 'grouvee',
		kind: 'file',
		description: 'Import games',
		files: [{ name: 'grouvee_json', label: 'Select File', accept: '.json,.zip' }]
	},
	imdb: {
		key: 'imdb',
		url: 'imdb',
		kind: 'file',
		description: 'Import movies and TV shows from your ratings',
		files: [{ name: 'imdb_csv', label: 'Select CSV File', accept: '.csv' }]
	},
	goodreads: {
		key: 'goodreads',
		url: 'goodreads',
		kind: 'file',
		description: 'Import from Goodreads backup',
		files: [{ name: 'goodreads_csv', label: 'Select CSV File', accept: '.csv' }]
	},
	hardcover: {
		key: 'hardcover',
		url: 'hardcover',
		kind: 'hardcover',
		description: 'Import from Hardcover export (Account -> Export Data)',
		files: [{ name: 'hardcover_csv', label: 'Select CSV File', accept: '.csv' }],
		placeholder: 'Optional — also settable in Settings > Metadata',
		button: 'Save'
	},
	storygraph: {
		key: 'storygraph',
		url: 'storygraph',
		kind: 'file',
		description: 'Import from StoryGraph export (Profile -> Manage Account -> Export StoryGraph Library)',
		files: [{ name: 'storygraph_csv', label: 'Select CSV File', accept: '.csv' }]
	},
	tvtime: {
		key: 'tvtime',
		url: 'tvtime',
		kind: 'files',
		description:
			'Import from a TV Time GDPR data export (Settings -> Export My Data). Select the shows file, the movies file, or both.',
		files: [
			{ name: 'tvtime_shows_csv', label: 'Select CSV File', accept: '.csv', title: 'Shows CSV (tracking-prod-records.csv)' },
			{ name: 'tvtime_movies_csv', label: 'Select CSV File', accept: '.csv', title: 'Movies CSV (tracking-prod-records-v2.csv)' }
		],
		button: 'Import'
	},
	myanimelist: {
		key: 'myanimelist',
		url: 'mal',
		kind: 'username',
		description: 'Import anime and manga',
		placeholder: 'MAL username',
		button: 'Import'
	},
	kitsu: {
		key: 'kitsu',
		url: 'kitsu',
		kind: 'username',
		description: 'Import anime and manga',
		placeholder: 'Kitsu user ID',
		hint: 'Find it on your Kitsu profile URL: kitsu.app/users/1234567',
		button: 'Import'
	},
	simkl: {
		key: 'simkl',
		url: 'simkl',
		kind: 'simkl',
		description: 'Import TV shows, movies and anime',
		button: 'Connect with Simkl & Import'
	},
	steam: {
		key: 'steam',
		url: 'steam',
		kind: 'username',
		description: 'Import games from your Steam library',
		placeholder: 'Steam 64-bit ID',
		hint: 'Find it on your Steam account details page under your username. Your profile must be public if the API key you are using is not linked to the steamid you are requesting.',
		button: 'Import'
	},
	trakt: {
		key: 'trakt',
		kind: 'trakt',
		description: 'Import TV shows and movies, including your collection'
	},
	anilist: {
		key: 'anilist',
		kind: 'anilist',
		description: 'Import anime and manga'
	},
	lastfm: {
		key: 'lastfm',
		kind: 'account',
		description: '',
		account: {
			key: 'lastfm',
			connectFields: [{ name: 'lastfm_username', label: 'Last.fm Username', type: 'text', placeholder: 'your_username', required: true }],
			connectButton: 'Connect Last.fm',
			connectPostsShared: false,
			syncPostsShared: false,
			disconnected: ({ pollInterval }) =>
				`Connect Last.fm to enable recurring syncs every ${pollInterval} minutes and import your full listening history. Your scrobbles must be public.`,
			connected: ({ pollInterval }) => `Import your Last.fm listening history automatically every ${pollInterval} minutes.`,
			syncLabel: () => 'Sync now',
			history: true
		}
	},
	koito: {
		key: 'koito',
		kind: 'account',
		description: '',
		account: {
			key: 'koito',
			connectFields: [
				{ name: 'base_url', label: 'Koito Server URL', type: 'url', placeholder: 'https://koito.example.com', required: true },
				{ name: 'api_key', label: 'API Key', type: 'password', placeholder: 'Koito API key', required: true }
			],
			connectButton: 'Connect Koito',
			connectPostsShared: false,
			syncPostsShared: false,
			disconnected: () =>
				'Connect a self-hosted Koito server to import your full listening history and sync new listens every 15 minutes. Generate an API key in Koito under Settings → API Keys. Floppy only reads from Koito and never sends listens back.',
			connected: () =>
				'Import your Koito listening history automatically every 15 minutes. Floppy only reads from Koito and never sends listens back.',
			syncLabel: () => 'Sync now',
			nameLabel: 'Server',
			history: true
		}
	},
	xbox: {
		key: 'xbox',
		kind: 'account',
		description: '',
		account: {
			key: 'xbox',
			connectFields: [{ name: 'api_key', label: 'OpenXBL API key', type: 'password', placeholder: 'OpenXBL API key', required: true }],
			connectButton: 'Connect Xbox',
			connectPostsShared: true,
			syncPostsShared: true,
			disconnected: () =>
				'Xbox has no public API, so Floppy connects through OpenXBL. Sign in at xbl.io with your Microsoft account and paste the API key it gives you.',
			connected: consoleText('Xbox'),
			syncLabel: consoleSync,
			nameLabel: 'Gamertag',
			links: [{ label: 'xbl.io', href: 'https://xbl.io' }],
			footnote: 'Xbox only reports games you have played, not everything you own, and not every title reports hours played.',
			footnoteAlways: true
		}
	},
	psn: {
		key: 'psn',
		kind: 'account',
		description: '',
		account: {
			key: 'psn',
			connectFields: [{ name: 'npsso', label: 'PSN NPSSO token', type: 'password', placeholder: 'PSN NPSSO token', required: true }],
			connectButton: 'Connect PlayStation',
			connectPostsShared: true,
			syncPostsShared: true,
			disconnected: () =>
				"PSN has no public API, so Floppy signs in with your NPSSO token. Log in at playstation.com, then open Sony's SSO cookie page and paste the npsso value it shows. Don't log out of that browser afterwards, or the token stops working.",
			connected: consoleText('PlayStation'),
			syncLabel: consoleSync,
			nameLabel: 'Online ID',
			links: [
				{ label: 'playstation.com', href: 'https://www.playstation.com' },
				{ label: "Sony's SSO cookie page", href: 'https://ca.account.sony.com/api/v1/ssocookie' }
			],
			footnote:
				'PSN only reports games you have played, not everything you own. The NPSSO token expires after about two months and then has to be pasted again.',
			footnoteAlways: true
		}
	},
	pocketcasts: {
		key: 'pocketcasts',
		kind: 'account',
		description: '',
		account: {
			key: 'pocketcasts',
			connectFields: [
				{ name: 'email', label: 'Email', type: 'email', placeholder: 'your.email@example.com', required: true },
				{ name: 'password', label: 'Password', type: 'password', placeholder: 'Your Pocket Casts password', required: true }
			],
			connectButton: 'Connect Pocket Casts',
			connectPostsShared: false,
			syncPostsShared: false,
			disconnected: () => 'Import podcasts every 2 hours (to estimate completion time)',
			connected: () => 'Import podcasts every 2 hours (to estimate completion time)',
			syncLabel: () => 'Sync now',
			footnote: 'For Apple or Google sign-ins, set a password via Forgot Password first, then enter your credentials here.'
		}
	},
	gpodder: {
		key: 'gpodder',
		kind: 'account',
		description: '',
		account: {
			key: 'gpodder',
			connectFields: [
				{ name: 'server_url', label: 'Server URL', type: 'url', placeholder: 'https://gpodder.net', required: true, value: 'https://gpodder.net' },
				{ name: 'username', label: 'Username', type: 'text', placeholder: 'Your GPodder username', required: true },
				{ name: 'password', label: 'Password / App Password', type: 'password', placeholder: 'Your password or app password', required: true },
				{ name: 'device_filter', label: 'Optional Device Filter', type: 'text', placeholder: 'antenna-pod-device', required: false }
			],
			connectButton: 'Connect GPodder',
			connectPostsShared: false,
			syncPostsShared: false,
			disconnected: () => 'Recurring podcast history sync for GPodder, AntennaPod, and self-hosted compatible servers every 2 hours.',
			connected: () => 'Recurring podcast history sync for GPodder, AntennaPod, and self-hosted compatible servers every 2 hours.',
			syncLabel: () => 'Sync now'
		}
	},
	plex: {
		key: 'plex',
		kind: 'plex',
		description: ''
	},
	radarr: {
		key: 'radarr',
		kind: 'arr',
		description: 'Sync owned movies from Radarr every 2 hours and reconcile quality metadata with Plex.'
	},
	sonarr: {
		key: 'sonarr',
		kind: 'arr',
		description: 'Sync owned TV collection from Sonarr every 2 hours and reconcile ownership with Plex.'
	},
	stremio: {
		key: 'stremio',
		kind: 'account',
		description: '',
		account: {
			key: 'stremio',
			connectFields: [
				{ name: 'email', label: 'Email', type: 'email', placeholder: 'Stremio email', required: false },
				{ name: 'password', label: 'Password', type: 'password', placeholder: 'Stremio password', required: false },
				{
					name: 'auth_key',
					label: 'Or an auth key',
					type: 'password',
					placeholder: 'Stremio auth key',
					required: false,
					hint: 'Find it in Stremio Web local storage. Required for accounts created with Facebook login.'
				}
			],
			connectButton: 'Connect Stremio',
			connectPostsShared: false,
			syncPostsShared: false,
			connectReady: (values) => !!values.auth_key?.trim() || (!!values.email?.trim() && !!values.password),
			disconnected: () => 'Connect with your Stremio email and password. Only an API key is stored; your password is never saved.',
			connected: () => 'Sync watched movies and episodes from your Stremio library every 2 hours.',
			syncLabel: () => 'Sync Now'
		}
	},
	audiobookshelf: {
		key: 'audiobookshelf',
		kind: 'account',
		description: '',
		account: {
			key: 'audiobookshelf',
			connectFields: [
				{ name: 'base_url', label: 'Base URL', type: 'url', placeholder: 'https://abs.example.com', required: true },
				{ name: 'api_token', label: 'API Token', type: 'password', placeholder: 'Audiobookshelf API token', required: true }
			],
			connectButton: 'Connect Audiobookshelf',
			connectPostsShared: false,
			syncPostsShared: false,
			disconnected: () => 'Pull audiobook progress from Audiobookshelf.',
			connected: ({ absPollInterval }) => `Sync Audiobook progress from Audiobookshelf every ${absPollInterval} minutes.`,
			syncLabel: () => 'Sync now',
			nameLabel: 'Server'
		}
	},
	storyteller: {
		key: 'storyteller',
		kind: 'storyteller',
		description: ''
	},
	koreader: {
		key: 'koreader',
		kind: 'koreader',
		description: ''
	},
	mdblist: {
		key: 'mdblist',
		url: 'mdblist',
		kind: 'mdblist',
		description:
			'Import watched history, watchlist, ratings, dropped shows and collection. Lists sync separately from the Lists page.',
		placeholder: 'MDBList API key',
		button: 'Import'
	}
};

/** The page-level settings every import form posts. */
export function sharedFields(settings: { frequency: string; time: string; mode: string }): Record<string, string> {
	return { frequency: settings.frequency, time: settings.time, mode: settings.mode };
}

/** Watchlist-only and collection-only modes turn the standard imports off. */
export function standardImportsDisabled(mode: string): boolean {
	return mode === 'update_collection' || mode === 'watchlist';
}
