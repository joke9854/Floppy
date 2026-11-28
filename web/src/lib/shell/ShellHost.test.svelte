<script lang="ts">
	import Shell from './Shell.svelte';
	import type { LibraryType } from './nav.ts';

	let {
		library,
		sidebarStyle,
		floatingSidebar
	}: { library: LibraryType[]; sidebarStyle?: string; floatingSidebar?: string } = $props();
</script>

<Shell username="reader" {library} {sidebarStyle} {floatingSidebar}>
	<p data-testid="content">Page content</p>
</Shell>
