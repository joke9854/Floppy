<script lang="ts">
	import Button from '#lib/ui/Button.svelte';
	import Card from '#lib/ui/Card.svelte';
	import { signOut } from '#lib/session-client.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	let signingOut = $state(false);
</script>

<svelte:head>
	<title>Floppy</title>
</svelte:head>

<main class="mx-auto max-w-2xl px-5 pt-8 md:px-8 md:pt-10">
	<h1 class="text-3xl font-bold tracking-tight">Floppy</h1>
	<p class="mt-2 text-muted">The new Floppy web app. Screens arrive here one at a time.</p>
	<Card class="mt-8 flex items-center justify-between gap-4">
		<p>Signed in as <strong data-testid="username">{data.account.username}</strong></p>
		<Button
			size="sm"
			disabled={signingOut}
			onclick={async () => {
				signingOut = true;
				await signOut();
			}}
		>
			Sign out
		</Button>
	</Card>
</main>
