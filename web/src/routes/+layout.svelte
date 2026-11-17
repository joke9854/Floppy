<script lang="ts">
	import './layout.css';
	import logo from '#lib/assets/floppy-logo.png';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<svelte:head>
	<link rel="icon" href={logo} />
	<meta name="theme-color" content="#1c1b22" />
</svelte:head>

{@render children()}
