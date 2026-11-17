<script lang="ts">
	import { goto } from '$app/navigation';
	import { BASE } from '#lib/paths.ts';
	import { djangoWrite } from '#lib/csrf.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	let signingOut = $state(false);

	async function signOut() {
		signingOut = true;
		// allauth answers 401 once the session is gone.
		await djangoWrite('/_allauth/browser/v1/auth/session', 'DELETE');
		await goto(`${BASE}/login`, { invalidateAll: true });
	}
</script>

<svelte:head>
	<title>Floppy</title>
</svelte:head>

<main class="mx-auto max-w-xl p-8">
	<h1 class="text-2xl font-semibold">Floppy</h1>
	<p class="mt-2 opacity-70">The new Floppy web app. Screens arrive here one at a time.</p>
	<p class="mt-6">Signed in as <strong data-testid="username">{data.account.username}</strong></p>
	<button class="mt-4 rounded-md border px-3 py-1.5" onclick={signOut} disabled={signingOut}>
		Sign out
	</button>
</main>
