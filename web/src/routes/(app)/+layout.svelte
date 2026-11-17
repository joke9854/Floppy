<script lang="ts">
	import Shell from '#lib/shell/Shell.svelte';
	import type { LayoutProps } from './$types';

	let { data, children }: LayoutProps = $props();
</script>

<Shell username={data.username} library={data.library}>
	{@render children()}
</Shell>
