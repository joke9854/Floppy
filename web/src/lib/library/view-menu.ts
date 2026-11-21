/** The View settings menu's props (the component itself loads on first use). */
export type ViewMenuProps = {
	mediaType: string;
	search: Iterable<[string, string]>;
	grouping: { enabled: boolean } | null;
	canSelect: boolean;
	selecting: boolean;
	onselect: () => void;
	/** What a write said, or why it failed, for the page's notice line. */
	onnotice: (message: string) => void;
	initialOpen?: boolean;
};
