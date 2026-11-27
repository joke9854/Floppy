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
	| 'simkl';

export type ImportFileField = { name: string; label: string; accept: string; title?: string };

export type ImportSource = {
	key: string;
	url: ImportUrlKey;
	kind: 'file' | 'files' | 'username' | 'mdblist' | 'hardcover' | 'simkl';
	/** The text above the form when the frequency is "once" (uploads) or always. */
	description: string;
	files?: ImportFileField[];
	/** username kind: the field's placeholder and an optional hint. */
	placeholder?: string;
	hint?: string;
	button?: string;
	docs?: boolean;
};

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
