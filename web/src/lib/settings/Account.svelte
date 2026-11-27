<script lang="ts">
	import { invalidate } from '$app/navigation';
	import { djangoForm } from '#lib/csrf.ts';
	import { st } from './strings.ts';
	import { readAnswer, type SettingsScreen } from './types.ts';

	/**
	 * Account (account.html): the username and password forms. Setting up or
	 * replacing the authenticator and regenerating recovery codes stay on the
	 * Django page, which shows the secret and the codes once.
	 */
	let { screen }: { screen: SettingsScreen } = $props();
	const account = $derived(screen.account!);

	// svelte-ignore state_referenced_locally
	let username = $state(screen.account!.username);
	let usernameErrors = $state<string[]>([]);
	let usernameStatus = $state('');
	let passwords = $state({ old_password: '', new_password1: '', new_password2: '' });
	let passwordErrors = $state<Record<string, string[]>>({});
	let passwordStatus = $state('');
	let busy = $state<'' | 'username' | 'password'>('');

	async function saveUsername(event: SubmitEvent) {
		event.preventDefault();
		busy = 'username';
		usernameStatus = '';
		try {
			const answer = await readAnswer(await djangoForm(account.save_url, { username }, { json: true }));
			usernameErrors = answer.errors?.username ?? answer.errors?.__all__ ?? [];
			if (answer.saved) {
				usernameStatus = st.usernameSaved;
				await invalidate('floppy:settings');
			} else if (!usernameErrors.length) usernameStatus = st.failed;
		} catch {
			usernameStatus = st.failed;
		} finally {
			busy = '';
		}
	}

	async function savePassword(event: SubmitEvent) {
		event.preventDefault();
		busy = 'password';
		passwordStatus = '';
		try {
			const answer = await readAnswer(await djangoForm(account.save_url, { ...passwords }, { json: true }));
			passwordErrors = answer.errors ?? {};
			if (answer.saved) {
				passwords = { old_password: '', new_password1: '', new_password2: '' };
				passwordStatus = st.passwordSaved;
			} else if (!Object.keys(passwordErrors).length) passwordStatus = st.failed;
		} catch {
			passwordStatus = st.failed;
		} finally {
			busy = '';
		}
	}

	const fields = [
		{ name: 'old_password', label: st.currentPassword, autocomplete: 'current-password' },
		{ name: 'new_password1', label: st.newPassword, autocomplete: 'new-password' },
		{ name: 'new_password2', label: st.confirmPassword, autocomplete: 'new-password' }
	] as const;
</script>

<section class="ct-settings-section">
	<h2>{st.profile}</h2>
	<form class="ct-settings-rows" onsubmit={saveUsername}>
		<label class="ct-settings-field">
			{st.username}
			<input name="username" autocomplete="username" required bind:value={username} disabled={account.is_demo} />
			{#each usernameErrors as message (message)}<small class="ct-settings-error">{message}</small>{/each}
		</label>
		<div class="ct-settings-actions">
			{#if usernameStatus}<span class="ct-settings-status" role="status">{usernameStatus}</span>{/if}
			<button type="submit" class="ct-settings-button is-primary" disabled={busy !== '' || account.is_demo}>{st.saveChanges}</button>
		</div>
	</form>
</section>

<section class="ct-settings-section">
	<h2>{st.changePassword}</h2>
	<form class="ct-settings-rows" onsubmit={savePassword}>
		{#each fields as field (field.name)}
			<label class="ct-settings-field">
				{field.label}
				<input type="password" name={field.name} autocomplete={field.autocomplete} required bind:value={passwords[field.name]} />
				{#each passwordErrors[field.name] ?? [] as message (message)}<small class="ct-settings-error">{message}</small>{/each}
			</label>
		{/each}
		{#each passwordErrors.__all__ ?? [] as message (message)}<small class="ct-settings-error">{message}</small>{/each}
		<div class="ct-settings-actions">
			{#if passwordStatus}<span class="ct-settings-status" role="status">{passwordStatus}</span>{/if}
			<button type="submit" class="ct-settings-button is-primary" disabled={busy !== ''}>{st.updatePassword}</button>
		</div>
	</form>
</section>

<section class="ct-settings-section">
	<h2>{st.recovery}</h2>
	<p class="ct-settings-note">{st.recoveryNote}</p>
	<p class="ct-settings-status">
		{account.authenticator_enabled ? st.authenticatorOn : st.authenticatorOff}
		{#if account.authenticator_enabled}· {st.unusedCodes} <b>{account.unused_recovery_codes}</b>{/if}
	</p>
	<div class="ct-settings-actions is-split">
		<a class="ct-settings-button" href={screen.django_url} data-sveltekit-reload>{st.manageAuthenticator}</a>
	</div>
</section>

{#if account.social_connections_url}
	<section class="ct-settings-section">
		<h2>{st.thirdParty}</h2>
		<p class="ct-settings-note">{st.thirdPartyNote}</p>
		<div><a class="ct-settings-button" href={account.social_connections_url} data-sveltekit-reload>{st.manageConnections}</a></div>
	</section>
{/if}
