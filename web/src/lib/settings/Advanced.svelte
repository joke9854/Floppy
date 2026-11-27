<script lang="ts">
	import ExternalLink from '@lucide/svelte/icons/external-link';
	import { invalidate } from '$app/navigation';
	import { djangoForm } from '#lib/csrf.ts';
	import { st } from './strings.ts';
	import { readAnswer, type SettingsScreen } from './types.ts';

	/**
	 * Advanced (advanced.html): logs and bug reports, external image caching
	 * (superusers), clearing caches, deleting one media type, the TMDB proxy.
	 * Each clear and the delete ask first, as on the Django page; the delete
	 * needs DELETE typed. The proxy URL is never read back.
	 */
	let { screen }: { screen: SettingsScreen } = $props();
	const advanced = $derived(screen.advanced!);

	const local = {
		title: 'Advanced',
		logs: 'Logs & Bug Reports',
		logsNote:
			'Download recent application logs with tokens, passwords, and API keys automatically redacted — safe to attach to a bug report. If this Floppy instance is shared with other users, the logs may still include their activity, just not their secrets.',
		logsAdminOnly:
			'The logs cover every account on this instance, so only an administrator can download them. The server owner can make an account an administrator with: manage.py promote_superuser USERNAME',
		downloadLogs: 'Download Sanitized Logs',
		bugReport: 'File a Bug Report',
		images: 'External Image Caching',
		imagesNote: (days: number) =>
			`Proxy artwork from approved metadata providers through Floppy so browsers and API clients do not need direct access to those providers. Cached images use disk space: one unused for ${days} days is removed, and a copy older than ${days} days is downloaded again overnight so changed artwork shows up.`,
		cachedImages: 'Cached images',
		diskUsage: 'Disk usage',
		status: 'Status',
		enabled: 'Enabled',
		disabled: 'Disabled',
		imagesHosts:
			'Only known provider image hosts are cached (including TMDB, TVDB, MyAnimeList, IGDB, Open Library, Hardcover, ComicVine, BoardGameGeek, MusicBrainz, Pocket Casts, iTunes, Kitsu, and AniList). Manual URLs, local services, placeholders, and unknown hosts stay unchanged.',
		enableImages: 'Enable external image caching',
		keepFor: 'Keep for',
		days: (days: number) => `${days} days`,
		save: 'Save',
		clearImages: 'Clear Image Cache',
		clearImagesBody: 'Every cached provider image is removed; they are fetched again as pages need them.',
		imagesAdminOnly: 'Only a superuser can change this setting or clear the cache.',
		caches: 'Cache Management',
		cachesNote:
			'Floppy caches computed pages (History, Statistics, Discover) and provider search results so they load fast. If one looks stale or wrong, clearing it forces a rebuild from your actual data — nothing about your library, watch history, ratings, or lists is touched by any of these.',
		clear: 'Clear',
		clearAll: 'Clear All Caches',
		cancel: 'Cancel',
		danger: 'Danger Zone',
		dangerNote:
			'Permanently delete every tracked entry for one media type in your account, including its progress, ratings, notes, and history. This cannot be undone.',
		typeToDelete: 'Media type to delete',
		deleteType: 'Delete Selected Type',
		sure: 'Are you sure?',
		sureBody: (label: string) =>
			`You are about to permanently delete every tracked ${label} entry in your account. This removes its progress, ratings, notes, and history.`,
		music: 'For music this covers your whole library page: the followed artists and albums as well as the individual tracks and their play counts.',
		alsoMetadata: 'Also delete cached metadata (posters, cast/crew, and for music, artists & albums) with no remaining tracked entries.',
		metadataNote: 'Metadata deletion also removes any custom list entries, collections, or calendar events still pointing at that now-untracked media.',
		cannotUndo: 'This action cannot be undone.',
		typeDelete: 'Type DELETE to confirm.',
		deleteForever: 'Permanently Delete',
		proxy: 'TMDB Proxy',
		configured: 'Configured',
		notConfigured: 'Not configured',
		proxyNote: 'If TMDB is blocked from this server, route TMDB requests through a proxy (HTTP or SOCKS5).',
		proxyUrl: 'Proxy URL',
		removeProxy: 'Remove proxy'
	};
	type Confirm = { key: string; title: string; lines: string[]; action: string; url: string; danger?: boolean };
	const cacheText: Record<string, { title: string; lines: string[] }> = {
		search: {
			title: 'Clear Search Cache?',
			lines: [
				'This is the one shared cache here — clearing it affects every user on this Floppy instance, not just you.',
				'No data is lost — this only affects search/lookup results, not your library.',
				'The next search anyone makes will be a bit slower while it re-fetches from TMDB, TVDB, and the other providers.'
			]
		},
		history: {
			title: 'Clear History Cache?',
			lines: [
				'Only affects your own account.',
				'Your watch history itself is not touched — this only clears the cached, day-by-day rendering of it.',
				'The History page will rebuild itself the next time you open it, which may take a moment the first time.'
			]
		},
		statistics: {
			title: 'Clear Statistics Cache?',
			lines: [
				'Only affects your own account.',
				'No underlying data is touched — only the cached charts/totals.',
				'Unlike History, Statistics rebuilds in the background rather than on your next page load — expect placeholder values for a bit until that finishes.'
			]
		},
		discover: {
			title: 'Clear Discover Cache?',
			lines: [
				'Only affects your own account.',
				'Your recommendation rows and taste profile get recomputed from scratch — rows may look different or take a moment to repopulate.',
				"Shared provider data other users' Discover pages also draw on is not affected."
			]
		}
	};
	const clearAllText = {
		title: 'Clear All Caches?',
		lines: [
			'This runs all four clears above at once: Search (instance-wide) plus your History, Statistics, and Discover caches.',
			'Search results go stale for every user on this instance until re-fetched.',
			'Your History and Discover pages will look empty for a moment and rebuild as you browse them.',
			'Your Statistics page will show placeholder values until a background task finishes rebuilding it — this is the slowest of the four to recover.',
			'No watch history, ratings, lists, or tracked media is deleted by any of this — only cached, computed views of it.'
		]
	};

	let busy = $state('');
	let notice = $state<{ key: string; text: string; failed: boolean } | null>(null);
	let confirm = $state<Confirm | null>(null);
	let dialog = $state<HTMLDialogElement>();
	let deleteDialog = $state<HTMLDialogElement>();

	// svelte-ignore state_referenced_locally
	let imagesOn = $state(screen.advanced!.image_cache.enabled);
	// svelte-ignore state_referenced_locally
	let imageDays = $state(String(screen.advanced!.image_cache.days));
	let deleteType = $state('');
	let deleteMetadata = $state(false);
	let deleteTyped = $state('');
	let proxy = $state('');

	const deleteLabel = $derived(advanced.media_types.find((type) => type.value === deleteType)?.label ?? '');

	async function post(key: string, url: string, fields: Record<string, string> = {}, after?: () => void) {
		busy = key;
		notice = null;
		try {
			const answer = await readAnswer(await djangoForm(url, fields, { json: true }));
			notice = { key, text: answer.saved ? answer.message || st.saved : (answer.message ?? st.failed), failed: !answer.saved };
			if (answer.saved) {
				after?.();
				await invalidate('floppy:settings');
			}
		} catch {
			notice = { key, text: st.failed, failed: true };
		} finally {
			busy = '';
		}
	}

	function ask(next: Confirm) {
		confirm = next;
		dialog?.showModal();
	}

	async function confirmed(event: SubmitEvent) {
		event.preventDefault();
		const action = confirm;
		dialog?.close();
		if (action) await post(action.key, action.url);
	}

	function askDelete() {
		deleteTyped = '';
		deleteMetadata = false;
		deleteDialog?.showModal();
	}

	async function confirmedDelete(event: SubmitEvent) {
		event.preventDefault();
		if (deleteTyped !== 'DELETE') return;
		deleteDialog?.close();
		await post('delete', advanced.urls.delete_media_type, { media_type: deleteType, delete_metadata: deleteMetadata ? 'true' : 'false' }, () => {
			deleteType = '';
		});
	}
</script>

{#snippet status(key: string)}
	{#if notice?.key === key}<span class={['ct-settings-status', notice.failed && 'is-error']} role="status">{notice.text}</span>{/if}
{/snippet}

<section class="ct-settings-section">
	<h2>{local.logs}</h2>
	<p class="ct-settings-note">{local.logsNote}</p>
	{#if !advanced.is_superuser}<p class="ct-settings-note">{local.logsAdminOnly}</p>{/if}
	<div class="ct-settings-actions" style="justify-content: flex-start">
		{#if advanced.is_superuser}<a class="ct-settings-button is-primary" href={advanced.urls.logs} download>{local.downloadLogs}</a>{/if}
		<a class="ct-settings-button" href={advanced.bug_report_url} target="_blank" rel="noopener noreferrer"
			>{local.bugReport} <ExternalLink class="size-4" aria-hidden="true" /><span class="sr-only">{st.newTab}</span></a
		>
	</div>
</section>

<section class="ct-settings-section">
	<h2>{local.images}</h2>
	<p class="ct-settings-note">{local.imagesNote(advanced.image_cache.days)}</p>
	<div class="ct-settings-actions" style="justify-content: flex-start">
		<span class="ct-settings-badge">{local.cachedImages}: {advanced.image_cache.count}</span>
		<span class="ct-settings-badge">{local.diskUsage}: {advanced.image_cache.size}</span>
		<span class={['ct-settings-badge', advanced.image_cache.enabled && 'is-on']}
			>{local.status}: {advanced.image_cache.enabled ? local.enabled : local.disabled}</span
		>
	</div>
	<p class="ct-settings-note">{local.imagesHosts}</p>
	{#if advanced.is_superuser}
		<div class="ct-settings-pref">
			<label class="ct-settings-check"><input type="checkbox" bind:checked={imagesOn} /><span>{local.enableImages}</span></label>
			<label class="ct-settings-weeks"
				>{local.keepFor}
				<select class="ct-settings-select" bind:value={imageDays}>
					{#each advanced.image_cache.day_choices as days (days)}<option value={String(days)}>{local.days(days)}</option>{/each}
				</select>
			</label>
		</div>
		<div class="ct-settings-actions">
			{@render status('images')}
			<button
				type="button"
				class="ct-settings-button"
				disabled={busy !== ''}
				onclick={() =>
					ask({ key: 'images', title: `${local.clearImages}?`, lines: [local.clearImagesBody], action: local.clearImages, url: advanced.urls.clear_image_cache })}
				>{local.clearImages}</button
			>
			<button
				type="button"
				class="ct-settings-button is-primary"
				disabled={busy !== ''}
				onclick={() => post('images', advanced.urls.image_cache, { image_caching_enabled: imagesOn ? '1' : '0', image_cache_days: imageDays })}
				>{local.save}</button
			>
		</div>
	{:else}
		<p class="ct-settings-note">{local.imagesAdminOnly}</p>
	{/if}
</section>

<section class="ct-settings-section">
	<div>
		<h2>{local.caches}</h2>
		<p class="ct-settings-note">{local.cachesNote}</p>
	</div>
	<ul class="ct-settings-rows">
		{#each advanced.caches as cache (cache.key)}
			<li class="ct-settings-row">
				<span>{cache.label}<small>{cache.note}</small></span>
				<button
					type="button"
					class="ct-settings-button"
					disabled={busy !== ''}
					onclick={() => ask({ key: 'caches', ...cacheText[cache.key], action: `${local.clear} ${cache.label}`, url: cache.url })}
					>{local.clear}</button
				>
			</li>
		{/each}
	</ul>
	<div class="ct-settings-actions">
		{@render status('caches')}
		<button
			type="button"
			class="ct-settings-button is-danger"
			disabled={busy !== ''}
			onclick={() => ask({ key: 'caches', ...clearAllText, action: local.clearAll, url: advanced.urls.clear_all, danger: true })}
			>{local.clearAll}</button
		>
	</div>
</section>

<section class="ct-settings-section">
	<div>
		<h2>{local.danger}</h2>
		<p class="ct-settings-note">{local.dangerNote}</p>
	</div>
	<label class="ct-settings-field">
		{local.typeToDelete}
		<select bind:value={deleteType}>
			<option value="" disabled>—</option>
			{#each advanced.media_types as type (type.value)}<option value={type.value}>{type.label}</option>{/each}
		</select>
	</label>
	<div class="ct-settings-actions">
		{@render status('delete')}
		<button type="button" class="ct-settings-button is-danger" disabled={busy !== '' || !deleteType || advanced.is_demo} onclick={askDelete}
			>{local.deleteType}</button
		>
	</div>
</section>

<section class="ct-settings-section">
	<div class="ct-settings-actions is-split">
		<h2>{local.proxy}</h2>
		<span class={['ct-settings-badge', advanced.tmdb_proxy_configured && 'is-on']}
			>{advanced.tmdb_proxy_configured ? local.configured : local.notConfigured}</span
		>
	</div>
	<p class="ct-settings-note">{local.proxyNote}</p>
	<label class="ct-settings-field">
		{local.proxyUrl}
		<input type="text" autocomplete="off" spellcheck="false" placeholder="socks5://user:pass@host:port" bind:value={proxy} />
	</label>
	<div class="ct-settings-actions">
		{@render status('proxy')}
		{#if advanced.tmdb_proxy_configured}
			<button type="button" class="ct-settings-button" disabled={busy !== ''} onclick={() => post('proxy', advanced.urls.tmdb_proxy, { tmdb_proxy_url: '' })}
				>{local.removeProxy}</button
			>
		{/if}
		<button
			type="button"
			class="ct-settings-button is-primary"
			disabled={busy !== '' || !proxy.trim()}
			onclick={() => post('proxy', advanced.urls.tmdb_proxy, { tmdb_proxy_url: proxy.trim() }, () => (proxy = ''))}>{local.save}</button
		>
	</div>
</section>

<dialog class="ct-settings-dialog" bind:this={dialog} aria-labelledby="ct-confirm-title" onclose={() => (confirm = null)}>
	{#if confirm}
		<form onsubmit={confirmed}>
			<h2 id="ct-confirm-title">{confirm.title}</h2>
			{#each confirm.lines as line (line)}<p class="ct-settings-note">{line}</p>{/each}
			<div class="ct-settings-actions">
				<button type="button" class="ct-settings-button" onclick={() => dialog?.close()}>{local.cancel}</button>
				<button type="submit" class={['ct-settings-button', confirm.danger ? 'is-danger' : 'is-primary']}>{confirm.action}</button>
			</div>
		</form>
	{/if}
</dialog>

<dialog class="ct-settings-dialog" bind:this={deleteDialog} aria-labelledby="ct-delete-title">
	<form onsubmit={confirmedDelete}>
		<h2 id="ct-delete-title">{local.sure}</h2>
		<p class="ct-settings-note">{local.sureBody(deleteLabel)}</p>
		{#if deleteType === 'music'}<p class="ct-settings-note">{local.music}</p>{/if}
		<label class="ct-settings-check">
			<input type="checkbox" bind:checked={deleteMetadata} />
			<span>{local.alsoMetadata}<small>{local.metadataNote}</small></span>
		</label>
		<p class="ct-settings-status is-error">{local.cannotUndo}</p>
		<label class="ct-settings-field">
			{local.typeDelete}
			<input type="text" autocomplete="off" spellcheck="false" bind:value={deleteTyped} />
		</label>
		<div class="ct-settings-actions">
			<button type="button" class="ct-settings-button" onclick={() => deleteDialog?.close()}>{local.cancel}</button>
			<button type="submit" class="ct-settings-button is-danger" disabled={deleteTyped !== 'DELETE'}>{local.deleteForever}</button>
		</div>
	</form>
</dialog>
