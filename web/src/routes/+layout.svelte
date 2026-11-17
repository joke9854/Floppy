<script lang="ts">
	import './layout.css';
	import { updated } from '$app/state';
	import logo from '#lib/assets/floppy-logo.png';
	import UpdatePrompt from '#lib/ui/UpdatePrompt.svelte';
	import { reloadToNewVersion } from '#lib/update.ts';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<svelte:head>
	<link rel="icon" href={logo} />
	<meta name="theme-color" content="#1c1b22" />
</svelte:head>

{@render children()}

<UpdatePrompt visible={updated.current} onreload={reloadToNewVersion} />
