/** The Plex dialog's pure logic, as import_data.html's Alpine helpers. */

export type PlexLibrary = { value: string; label: string; is_music: boolean; audiobook_hint: boolean; content_kind: string };

/** A section from the live `plex_sections` answer (it carries no token). */
export type PlexSection = {
	id: string | number;
	title?: string;
	type?: string;
	server_name?: string;
	machine_identifier: string;
	is_music?: boolean;
	audiobook_hint?: boolean;
	content_kind?: string;
};

export type PlexSelection = { libraries: string[]; kinds: Record<string, string> };

export const PLEX_KINDS: [string, string][] = [
	['auto', 'Auto-detect'],
	['music', 'Music'],
	['audiobook', 'Audiobooks']
];

export const ALL_LIBRARIES = 'all';

export const plexLibraryLabel = (section: PlexSection): string => {
	let label = section.title || 'Unknown library';
	if (section.server_name) label += ` - ${section.server_name}`;
	if (section.type) label += ` (${String(section.type).charAt(0).toUpperCase()}${String(section.type).slice(1)})`;
	return label;
};

export const sectionToLibrary = (section: PlexSection): PlexLibrary => ({
	value: `${section.machine_identifier}::${section.id}`,
	label: plexLibraryLabel(section),
	is_music: !!section.is_music,
	audiobook_hint: !!section.audiobook_hint,
	content_kind: section.content_kind ?? 'auto'
});

export function defaultContentKind(library: Pick<PlexLibrary, 'audiobook_hint' | 'content_kind'>): string {
	if (library.content_kind && library.content_kind !== 'auto') return library.content_kind;
	return library.audiobook_hint ? 'audiobook' : 'auto';
}

export const initialSelection = (): PlexSelection => ({ libraries: [ALL_LIBRARIES], kinds: {} });

export const selectAllLibraries = (): PlexSelection => initialSelection();

/** Toggle one library: from "all" it becomes the only one; a newly chosen music library gets its default kind. */
export function toggleLibrary(selection: PlexSelection, library: PlexLibrary): PlexSelection {
	const key = library.value;
	let libraries: string[];
	const kinds = { ...selection.kinds };
	if (selection.libraries.includes(ALL_LIBRARIES)) {
		libraries = [key];
	} else if (selection.libraries.includes(key)) {
		delete kinds[key];
		return { libraries: selection.libraries.filter((value) => value !== key), kinds };
	} else {
		libraries = [...selection.libraries, key];
	}
	if (library.is_music && !(key in kinds)) kinds[key] = defaultContentKind(library);
	return { libraries, kinds };
}

/** Drop selections whose library is gone (live answers can differ from the cache). */
export function reconcileSelection(selection: PlexSelection, libraries: PlexLibrary[]): PlexSelection {
	if (selection.libraries.includes(ALL_LIBRARIES)) return selection;
	const available = new Set(libraries.map((library) => library.value));
	const kinds: Record<string, string> = {};
	for (const [key, kind] of Object.entries(selection.kinds)) if (available.has(key)) kinds[key] = kind;
	return { libraries: selection.libraries.filter((key) => available.has(key)), kinds };
}

export function plexStatusLabel(state: string): string {
	if (state === 'connected') return 'Connected';
	if (state === 'error') return 'Connection failed';
	if (state === 'checking') return 'Checking';
	return 'Disconnected';
}

export function plexPrimaryLabel(mode: string, watchlistEnabled: boolean): string {
	if (mode === 'update_collection') return 'Update';
	if (mode === 'watchlist') return watchlistEnabled ? 'Sync Now' : 'Enable Sync';
	return 'Import';
}

export function plexSubmitDisabled(state: string, mode: string, selection: PlexSelection, hasLibraries: boolean): boolean {
	if (state === 'error') return true;
	if (mode === 'watchlist') return false;
	return !selection.libraries.length || !hasLibraries;
}

/** The `library_content_kind` values: `<library>::<kind>` for every music library with a kind. */
export const contentKindFields = (kinds: Record<string, string>): string[] => Object.entries(kinds).map(([key, kind]) => `${key}::${kind}`);

/** GET one of the dialog's JSON helpers (same headers as import_data.html's fetches). */
export async function getJson<T>(url: string, signal?: AbortSignal): Promise<{ ok: boolean; body: T }> {
	const response = await fetch(url, { credentials: 'same-origin', signal, headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' } });
	const body = (await response.json()) as T;
	return { ok: response.ok, body };
}
