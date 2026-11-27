<script lang="ts">
	import X from '@lucide/svelte/icons/x';
	import { invalidate } from '$app/navigation';
	import { djangoForm, djangoWrite } from '#lib/csrf.ts';
	import { st } from './strings.ts';
	import { notificationsForm, readAnswer, type SettingsItem, type SettingsScreen } from './types.ts';

	/**
	 * Notifications (notifications.html): Apprise URLs and the three
	 * notification switches (every field posts back), the test send, and the
	 * items excluded from notifications with a search to add more.
	 */
	let { screen }: { screen: SettingsScreen } = $props();
	const notifications = $derived(screen.notifications!);

	// svelte-ignore state_referenced_locally
	let values = $state({
		notification_urls: screen.notifications!.notification_urls,
		daily_digest_enabled: screen.notifications!.daily_digest_enabled,
		release_notifications_enabled: screen.notifications!.release_notifications_enabled,
		premiere_notifications_enabled: screen.notifications!.premiere_notifications_enabled
	});
	let errors = $state<Record<string, string[]>>({});
	let status = $state('');
	let failed = $state(false);
	let busy = $state<'' | 'save' | 'test'>('');

	let query = $state('');
	let results = $state<SettingsItem[] | null>(null);
	let searchTimer: ReturnType<typeof setTimeout> | undefined;
	let searchCount = 0;
	let changing = $state<number | null>(null);

	const switches = [
		{ key: 'daily_digest_enabled', label: st.dailyDigest, note: st.dailyDigestNote },
		{ key: 'release_notifications_enabled', label: st.releases, note: st.releasesNote },
		{ key: 'premiere_notifications_enabled', label: st.premieres, note: st.premieresNote }
	] as const;

	async function save(event: SubmitEvent) {
		event.preventDefault();
		busy = 'save';
		status = '';
		try {
			const answer = await readAnswer(await djangoForm(notifications.urls.save, notificationsForm(values), { json: true }));
			errors = answer.errors ?? {};
			failed = !answer.saved;
			status = answer.saved ? st.notificationsSaved : Object.values(errors).flat()[0] ?? st.failed;
			if (answer.saved) await invalidate('floppy:settings');
		} catch {
			failed = true;
			status = st.failed;
		} finally {
			busy = '';
		}
	}

	async function test() {
		busy = 'test';
		status = '';
		try {
			const response = await djangoWrite(notifications.urls.test, 'POST');
			const body = (await response.json().catch(() => ({}))) as { detail?: string };
			failed = !response.ok;
			status = response.ok ? st.testSent : (body.detail ?? st.failed);
		} catch {
			failed = true;
			status = st.failed;
		} finally {
			busy = '';
		}
	}

	function search(value: string) {
		query = value;
		clearTimeout(searchTimer);
		if (value.trim().length <= 1) {
			results = null;
			return;
		}
		searchTimer = setTimeout(async () => {
			const mine = ++searchCount;
			const response = await fetch(`${notifications.urls.search}?q=${encodeURIComponent(value.trim())}`, {
				credentials: 'same-origin',
				headers: { accept: 'application/json' }
			});
			if (mine !== searchCount || !response.ok) return;
			results = ((await response.json()) as { items: SettingsItem[] }).items;
		}, 300);
	}

	async function setExcluded(item: SettingsItem, excluded: boolean) {
		changing = item.id;
		try {
			const response = await djangoWrite(notifications.urls.exclusions, excluded ? 'POST' : 'DELETE', { item_id: item.id });
			if (!response.ok) throw new Error(String(response.status));
			if (excluded) results = (results ?? []).filter((row) => row.id !== item.id);
			await invalidate('floppy:settings');
		} catch {
			failed = true;
			status = st.failed;
		} finally {
			changing = null;
		}
	}
</script>

<form class="ct-settings-rows" onsubmit={save}>
	<section class="ct-settings-section">
		<div>
			<h2>{st.notifications}</h2>
			<p class="ct-settings-note">{st.notificationsNote}</p>
		</div>
		<label class="ct-settings-field">
			{st.appriseUrls}
			<textarea rows="5" wrap="off" spellcheck="false" bind:value={values.notification_urls}></textarea>
			{#each errors.notification_urls ?? [] as message (message)}<small class="ct-settings-error">{message}</small>{/each}
		</label>
		<p class="ct-settings-note">
			{st.appriseMore}
			{st.appriseHelp}
			<a class="ct-settings-link" href="https://github.com/caronc/apprise/wiki" target="_blank" rel="noopener noreferrer"
				>Apprise <span class="sr-only">{st.newTab}</span></a
			>
		</p>
		<h3>{st.notificationSettings}</h3>
		{#each switches as option (option.key)}
			<label class="ct-settings-check">
				<input type="checkbox" bind:checked={values[option.key]} />
				<span>{option.label}<small>{option.note}</small></span>
			</label>
		{/each}
		<div class="ct-settings-actions is-split">
			<button type="button" class="ct-settings-button" disabled={busy !== ''} onclick={test}>{st.testNotifications}</button>
			<div class="ct-settings-actions">
				{#if status}<span class={['ct-settings-status', failed && 'is-error']} role="status">{status}</span>{/if}
				<button type="submit" class="ct-settings-button is-primary" disabled={busy !== ''}>{st.saveSettings}</button>
			</div>
		</div>
	</section>
</form>

<section class="ct-settings-section">
	<div>
		<h2>{st.excluded}</h2>
		<p class="ct-settings-note">{st.excludedNote}</p>
	</div>
	<label class="ct-settings-search">
		<input type="search" placeholder={st.searchExclude} aria-label={st.searchExclude} value={query} oninput={(event) => search(event.currentTarget.value)} />
	</label>
	{#if results}
		{#if results.length}
			<ul class="ct-settings-rows">
				{#each results as item (item.id)}
					<li class="ct-settings-row">
						<img src={item.image} alt="" loading="lazy" />
						<span>{item.title}<small>{item.media_type}</small></span>
						<button type="button" class="ct-settings-button" disabled={changing !== null} onclick={() => setExcluded(item, true)}>{st.exclude}</button>
					</li>
				{/each}
			</ul>
		{:else}
			<p class="ct-settings-note">{st.noMatches}</p>
		{/if}
	{/if}
	<h3>{st.currentlyExcluded}</h3>
	{#if notifications.excluded.length}
		<ul class="ct-settings-rows">
			{#each notifications.excluded as item (item.id)}
				<li class="ct-settings-row">
					<img src={item.image} alt="" loading="lazy" />
					<span>{item.title}<small>{item.media_type}</small></span>
					<button type="button" class="is-icon" aria-label="{st.include}: {item.title}" disabled={changing !== null} onclick={() => setExcluded(item, false)}>
						<X class="size-4" aria-hidden="true" />
					</button>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="ct-settings-note">{st.noneExcluded}</p>
	{/if}
</section>

<p><a class="ct-settings-link" href={notifications.urls.rss} data-sveltekit-reload>{st.rssFeeds}</a></p>
