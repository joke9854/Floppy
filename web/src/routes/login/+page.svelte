<script lang="ts">
	import { goto } from '$app/navigation';
	import { djangoWrite } from '#lib/csrf.ts';
	import Button from '#lib/ui/Button.svelte';
	import TextField from '#lib/ui/TextField.svelte';
	import logo from '#lib/assets/floppy-logo.png';
	import { t } from '#lib/strings.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	let username = $state('');
	let password = $state('');
	let message = $state('');
	let busy = $state(false);
	// The form signs in with a script. Until it has loaded, the button stays
	// off: a native submit would only reach the no-script fallback.
	let ready = $state(false);
	$effect(() => {
		ready = true;
	});

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

<main class="flex min-h-dvh items-center justify-center px-5 py-10">
	<div class="ct-card w-full max-w-sm rounded-ct-lg p-7">
		<div class="flex items-center gap-3">
			<img src={logo} alt="" width="40" height="40" class="size-10 rounded-ct-sm" />
			<span class="text-lg font-bold">{t.appName}</span>
		</div>
		<h1 class="mt-6 text-2xl font-bold tracking-tight">Sign in</h1>
		<!-- method="post": a submit before the script loads never puts the
		     password in a URL; the no-script fallback is the Django sign-in. -->
		<form class="mt-6 flex flex-col gap-4" method="post" onsubmit={signIn}>
			<TextField label="Username" name="username" autocomplete="username" required bind:value={username} />
			<TextField
				label="Password"
				name="password"
				type="password"
				autocomplete="current-password"
				required
				bind:value={password}
			/>
			{#if message}
				<p role="alert" class="text-sm text-error">{message}</p>
			{/if}
			<Button variant="primary" type="submit" disabled={busy || !ready} class="mt-2 w-full">{t.signIn}</Button>
		</form>
		<p class="mt-6 text-sm text-muted">
			Forgot your password?
			<a class="text-link underline-offset-2 hover:text-link-hover hover:underline" href="/accounts/password/recover/"
				>Use a recovery code</a
			>.
		</p>
	</div>
</main>
