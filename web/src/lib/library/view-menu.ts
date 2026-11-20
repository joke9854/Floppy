/** The View settings menu's props (the component itself loads on first use). */
export type ViewMenuProps = {
	grouping: { enabled: boolean } | null;
	canSelect: boolean;
	selecting: boolean;
	sharing: boolean;
	ongrouping: () => void;
	onshare: () => void;
	onselect: () => void;
	initialOpen?: boolean;
};
