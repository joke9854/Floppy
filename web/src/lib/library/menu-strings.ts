/**
 * Strings of the Library's menus that load on first use (Columns, View
 * settings, the bulk bar, the card menu, the table), worded as the Django
 * page. Kept out of #lib/strings.ts, which every page loads (bundle budget).
 */
export const lt = {
	columns: 'Columns',
	configureColumns: 'Configure Table Columns',
	resetDefaults: 'Reset to defaults',
	moveUp: (label: string) => `Move ${label} up`,
	moveDown: (label: string) => `Move ${label} down`,
	columnsFailed: 'The columns could not be saved. Try again.',

	shareView: 'Share View',
	sharing: 'Sharing…',
	selectItems: 'Select Items',
	cancelSelect: 'Cancel Select',
	showEntriesSeparately: 'Show matching entries separately',
	on: 'On',
	off: 'Off',
	selected: 'Selected',
	updateStatus: 'Update Status',
	addToList: 'Add to List',
	addToCollection: 'Add to Collection',
	applyTag: 'Apply Tag',
	remove: 'Remove',
	clear: 'Clear',
	noEditableLists: 'No editable lists.',
	noTagsYet: 'No tags yet.',
	editTracking: 'Edit tracking',
	viewHistory: 'View your activity history',
} as const;
