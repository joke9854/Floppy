<script lang="ts">
	import { page } from '$app/state';
	import { BASE } from '#lib/paths.ts';
	import Button from '#lib/ui/Button.svelte';
</script>

<svelte:head>
	<title>{page.status} · Floppy</title>
</svelte:head>

<main class="flex min-h-dvh items-center justify-center px-5">
	<div class="ct-card w-full max-w-md rounded-ct-lg p-7 text-center">
		<p class="text-sm font-bold text-muted">{page.status}</p>
		<h1 class="mt-2 text-xl font-bold">
			{page.status === 404 ? 'This page does not exist.' : 'Something went wrong.'}
		</h1>
		{#if page.error?.message && page.status !== 404}
			<p class="mt-3 text-muted">{page.error.message}</p>
		{/if}
		<div class="mt-6 flex justify-center gap-3">
			<Button onclick={() => location.reload()}>Try again</Button>
			<a
				href="{BASE}/"
				class="ct-focus inline-flex h-11 items-center rounded-full px-5 font-semibold text-muted hover:text-text"
				>Start page</a
			>
		</div>
	</div>
</main>
