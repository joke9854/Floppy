<script lang="ts">
	import { goto } from '$app/navigation';
	import { djangoWrite } from '#lib/csrf.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	let username = $state('');
	let password = $state('');
	let message = $state('');
	let busy = $state(false);

	/** allauth headless sign-in, from the browser, so Django sets the session cookie itself. */
	async function signIn(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		message = '';
		try {
			const response = await djangoWrite('/_allauth/browser/v1/auth/login', 'POST', {
				username,
				password
			});
			if (response.ok) {
				await goto(data.next, { invalidateAll: true });
				return;
			}
			message =
				response.status === 429
					? 'Too many attempts. Wait a little and try again.'
					: response.status === 400
						? 'The username or password is not right.'
						: 'Signing in did not work. Try again in a moment.';
		} catch {
			message = "Floppy's server is not answering. Try again in a moment.";
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head>
	<title>Sign in · Floppy</title>
</svelte:head>

<main class="mx-auto max-w-sm p-8">
	<h1 class="text-2xl font-semibold">Sign in</h1>
	<form class="mt-6 flex flex-col gap-4" onsubmit={signIn}>
		<label class="flex flex-col gap-1">
			Username
			<input class="rounded-md border px-3 py-2" name="username" autocomplete="username" required bind:value={username} />
		</label>
		<label class="flex flex-col gap-1">
			Password
			<input
				class="rounded-md border px-3 py-2"
				name="password"
				type="password"
				autocomplete="current-password"
				required
				bind:value={password}
			/>
		</label>
		{#if message}
			<p role="alert" class="text-red-500">{message}</p>
		{/if}
		<button class="rounded-md border px-3 py-2" type="submit" disabled={busy}>Sign in</button>
	</form>
	<p class="mt-6 text-sm opacity-70">
		Forgot your password? <a class="underline" href="/accounts/password/recover/">Use a recovery code</a>.
	</p>
</main>
