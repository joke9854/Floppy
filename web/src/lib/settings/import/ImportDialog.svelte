<script lang="ts">
	import ExternalLink from '@lucide/svelte/icons/external-link';
	import FileUp from '@lucide/svelte/icons/file-up';
	import X from '@lucide/svelte/icons/x';
	import { invalidate } from '$app/navigation';
	import { onMount } from 'svelte';
	import { postForm } from '../integrations/actions.ts';
	import { st } from '../strings.ts';
	import type { SavedAnswer, SettingsImport } from '../types.ts';
	import { IMPORT_SOURCES, PERIODIC_UPLOAD_NOTE, sharedFields, standardImportsDisabled } from './sources.ts';
	import AccountPanel from './AccountPanel.svelte';
	import AniListPanel from './AniListPanel.svelte';
	import OAuthForm from './OAuthForm.svelte';
	import TraktPanel from './TraktPanel.svelte';
	import { postUpload } from './upload.ts';

	/**
	 * One source's import dialog (import_data.html's per-source forms). Every
	 * form posts the page's Import Settings too. Files are chosen first and sent
	 * with an Import button; Simkl is a real form submit (it leaves for Simkl).
	 */
	let {
		sourceKey,
		data,
		frequency,
		time,
		mode,
		onclose,
		onsaved
	}: {
		sourceKey: string;
		data: SettingsImport;
		frequency: string;
		time: string;
		mode: string;
		onclose: () => void;
		onsaved: () => void;
	} = $props();

	const source = $derived(IMPORT_SOURCES[sourceKey]);
	const tile = $derived(data.tiles.find((item) => item.key === sourceKey));
	const urls = $derived(data.urls);
	const shared = $derived(sharedFields({ frequency, time, mode }));
	const standardOff = $derived(standardImportsDisabled(mode));
	const uploadOff = $derived(frequency !== 'once' || standardOff || data.is_demo);
	const description = $derived(source && (source.kind === 'file' || source.kind === 'files') && frequency !== 'once' ? PERIODIC_UPLOAD_NOTE : source?.description);

	let dialog = $state<HTMLDialogElement>();
	let busy = $state(false);
	let notice = $state<{ text: string; failed: boolean } | null>(null);
	let nonce = $state(0);
	let files = $state<Record<string, File | null>>({});
	let user = $state('');
	let apiKey = $state('');
	let hardcoverKey = $state('');

	onMount(() => {
		dialog?.showModal();
	});

	function pick(name: string, event: Event) {
		files[name] = (event.currentTarget as HTMLInputElement).files?.[0] ?? null;
	}

	function reset() {
		files = {};
		user = '';
		apiKey = '';
		hardcoverKey = '';
		nonce += 1;
	}

	async function run(send: () => Promise<SavedAnswer>) {
		busy = true;
		notice = null;
		try {
			const answer = await send();
			notice = { text: answer.saved ? answer.message || st.saved : (answer.message ?? st.failed), failed: !answer.saved };
			if (answer.saved) {
				reset();
				onsaved();
			}
		} catch {
			notice = { text: st.failed, failed: true };
		} finally {
			busy = false;
		}
	}

	/** A K2 action: refresh the page and the activity whether it saved or failed (connect can create the account and still fail). */
	async function runRemote(send: () => Promise<SavedAnswer>): Promise<SavedAnswer | null> {
		busy = true;
		notice = null;
		let answer: SavedAnswer | null = null;
		try {
			answer = await send();
			notice = { text: answer.saved ? answer.message || st.saved : (answer.message ?? st.failed), failed: !answer.saved };
		} catch {
			notice = { text: st.failed, failed: true };
		}
		try {
			await invalidate('floppy:settings');
		} catch {
			// The answer above is what the user needs; the next load refreshes the page.
		}
		onsaved();
		busy = false;
		return answer;
	}

	function chosenFiles(): Record<string, File | null> {
		const picked: Record<string, File | null> = {};
		for (const field of source.files ?? []) picked[field.name] = files[field.name] ?? null;
		return picked;
	}

	const hasFile = $derived((source?.files ?? []).some((field) => files[field.name]));

	function submit(event: SubmitEvent) {
		event.preventDefault();
		if (busy) return;
		if (source.kind === 'file' || source.kind === 'files') {
			void run(() => postUpload(urls[source.url!], shared, chosenFiles()));
		} else if (source.kind === 'username') {
			void run(() => postForm(urls[source.url!], { ...shared, user: user.trim() }));
		} else if (source.kind === 'mdblist') {
			void run(() => postForm(urls[source.url!], data.mdblist_connected ? shared : { ...shared, api_key: apiKey.trim() }));
		} else if (source.kind === 'hardcover') {
			const fields = hardcoverKey.trim() ? { ...shared, hardcover_api_key: hardcoverKey.trim() } : shared;
			void run(() => postUpload(urls.hardcover, fields, chosenFiles()));
		}
	}

	function backdrop(event: MouseEvent) {
		if (event.target === dialog) dialog?.close();
	}
</script>

<dialog class="ct-settings-dialog ct-import-dialog" bind:this={dialog} aria-labelledby="ct-import-title" {onclose} onclick={backdrop}>
	{#if source}
		<div class="ct-import-dialog-head">
			{#if tile?.logo}<img src={tile.logo} alt="" class="ct-import-logo" />{:else}<FileUp class="size-6" aria-hidden="true" />{/if}
			<h2 id="ct-import-title">{tile?.name ?? source.key}</h2>
			<button type="button" class="ct-import-close" aria-label="Close" onclick={() => dialog?.close()}><X class="size-5" aria-hidden="true" /></button>
		</div>
		{#if source.docs}
			<a class="ct-settings-link" href={urls.csv_docs} target="_blank" rel="noopener noreferrer"
				>View CSV format documentation <ExternalLink class="inline size-4" aria-hidden="true" /><span class="sr-only">{st.newTab}</span></a
			>
		{/if}
		{#if description}<p class="ct-settings-note">{description}</p>{/if}

		{#if source.kind === 'simkl'}
			<OAuthForm action={urls.simkl} button={source.button ?? ''} disabled={standardOff || data.is_demo} note="You will sign in on Simkl and come back here." {frequency} {time} {mode} />
		{:else if source.kind === 'trakt'}
			<TraktPanel {data} {frequency} {time} {mode} {busy} run={runRemote} />
		{:else if source.kind === 'anilist'}
			<AniListPanel {data} {frequency} {time} {mode} {busy} run={runRemote} />
		{:else if source.kind === 'account' && source.account}
			<AccountPanel account={source.account} {data} {frequency} {time} {mode} {busy} run={runRemote} />
		{:else}
			{#key nonce}
				<form onsubmit={submit}>
					{#if source.kind === 'file'}
						{#each source.files ?? [] as field (field.name)}
							<label class="ct-settings-field">
								{field.label}
								<input type="file" accept={field.accept} disabled={uploadOff || busy} onchange={(event) => pick(field.name, event)} />
							</label>
						{/each}
						<div class="ct-settings-actions">
							<button type="submit" class="ct-settings-button is-primary" disabled={uploadOff || busy || !hasFile}>Import</button>
						</div>
					{:else if source.kind === 'files'}
						{#each source.files ?? [] as field (field.name)}
							<label class="ct-settings-field">
								{field.title ?? field.label}
								<input type="file" accept={field.accept} disabled={uploadOff || busy} onchange={(event) => pick(field.name, event)} />
							</label>
						{/each}
						<div class="ct-settings-actions">
							<button type="submit" class="ct-settings-button is-primary" disabled={uploadOff || busy || !hasFile}>{source.button ?? 'Import'}</button>
						</div>
					{:else if source.kind === 'username'}
						<label class="ct-settings-field">
							{source.placeholder}
							<input type="text" name="user" autocomplete="off" spellcheck="false" placeholder={source.placeholder} bind:value={user} />
							{#if source.hint}<small class="ct-settings-note">{source.hint}</small>{/if}
						</label>
						<div class="ct-settings-actions">
							<button type="submit" class="ct-settings-button is-primary" disabled={busy || standardOff || data.is_demo || !user.trim()}>{source.button}</button>
						</div>
					{:else if source.kind === 'mdblist'}
						{#if data.mdblist_connected}
							<p class="ct-settings-note">Using your connected MDBList account.</p>
						{:else}
							<label class="ct-settings-field">
								MDBList API key
								<input type="password" name="api_key" autocomplete="off" required placeholder={source.placeholder} bind:value={apiKey} />
							</label>
							<p class="ct-settings-note">
								Get your API key from
								<a class="ct-settings-link" href="https://mdblist.com/preferences/" target="_blank" rel="noopener noreferrer"
									>MDBList Preferences<span class="sr-only"> {st.newTab}</span></a
								>. Connecting also enables list sync from the Lists page.
							</p>
						{/if}
						<div class="ct-settings-actions">
							<button
								type="submit"
								class="ct-settings-button is-primary"
								disabled={busy || standardOff || data.is_demo || (!data.mdblist_connected && !apiKey.trim())}>{source.button}</button
							>
						</div>
					{:else if source.kind === 'hardcover'}
						{#if data.hardcover_key_saved}<p class="ct-settings-note">A personal Hardcover key is saved.</p>{/if}
						<label class="ct-settings-field">
							Hardcover API Key
							<input type="password" name="hardcover_api_key" autocomplete="off" placeholder={source.placeholder} disabled={standardOff || data.is_demo} bind:value={hardcoverKey} />
						</label>
						{#each source.files ?? [] as field (field.name)}
							<label class="ct-settings-field">
								{field.label}
								<input type="file" accept={field.accept} disabled={uploadOff || busy} onchange={(event) => pick(field.name, event)} />
							</label>
						{/each}
						<div class="ct-settings-actions">
							<button
								type="submit"
								class="ct-settings-button is-primary"
								disabled={busy || standardOff || data.is_demo || (!hardcoverKey.trim() && !hasFile)}>{source.button}</button
							>
						</div>
					{/if}
				</form>
			{/key}
		{/if}
		{#if notice}<p class={['ct-settings-status', notice.failed && 'is-error']} role="status">{notice.text}</p>{/if}
	{/if}
</dialog>
