<script lang="ts">
	import Shell from './Shell.svelte';
	import type { LibraryType } from './nav.ts';

	let { library }: { library: LibraryType[] } = $props();
</script>

<Shell username="reader" {library}>
	<p data-testid="content">Page content</p>
</Shell>
