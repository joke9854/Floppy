<script lang="ts">
	import { BASE } from '#lib/paths.ts';
	import CopyField from './integrations/CopyField.svelte';
	import type { SettingsScreen } from './types.ts';

	/**
	 * RSS (rss.html): turn a Discover row backed by external metadata into a
	 * feed URL, with a live preview of what the row holds right now.
	 */
	let { screen }: { screen: SettingsScreen } = $props();
	const rss = $derived(screen.rss!);

	const local = {
		intro: "Turn a Discover row backed by external metadata (Trakt and other providers) into a feed you can subscribe to, or paste into Radarr's or Sonarr's RSS List import.",
		mediaType: 'Media Type',
		row: 'Row',
		skipPlanning: 'Skip Planning',
		skipCollected: 'Skip Collected',
		feedUrl: 'Feed URL',
		empty: 'No items matched this row right now.',
		footA: "Compatible with Radarr's and Sonarr's RSS List import (movies use the Trending Right Now, All-Time Greats and Coming Soon rows for the Movie/TV/Anime media types). This feed uses your account's API token — regenerating it from ",
		footLink: 'Integrations',
		footB: ' invalidates old feed links.'
	};

	type PreviewItem = { title: string; media_type: string; source: string; media_id: string; image: string; release_date: string | null };

	// svelte-ignore state_referenced_locally
	let mediaType = $state(screen.rss!.media_types[0]?.value ?? '');
	// svelte-ignore state_referenced_locally
	let rowKey = $state(screen.rss!.media_types[0]?.rows[0]?.key ?? '');
	let skipPlanning = $state(true);
	let skipCollected = $state(true);
	let items = $state<PreviewItem[] | null>(null);
	let loading = $state(false);
	let request = 0;
	let timer: ReturnType<typeof setTimeout> | undefined;

	const rows = $derived(rss.media_types.find((type) => type.value === mediaType)?.rows ?? []);
	const feedUrl = $derived(
		mediaType && rowKey
			? `${rss.feed_url_template.replace('MEDIA_TYPE_PLACEHOLDER', mediaType).replace('ROW_KEY_PLACEHOLDER', rowKey)}?${new URLSearchParams({
					skip_planning: skipPlanning ? '1' : '0',
					skip_collected: skipCollected ? '1' : '0'
				})}`
			: ''
	);

	function changeType() {
		if (!rows.some((row) => row.key === rowKey)) rowKey = rows[0]?.key ?? '';
	}

	async function refresh(query: string) {
		const mine = ++request;
		loading = true;
		try {
			const response = await fetch(`${rss.preview_url}?${query}`, { headers: { accept: 'application/json' }, credentials: 'same-origin' });
			if (mine !== request) return;
			const body = response.ok ? ((await response.json().catch(() => null)) as { items?: PreviewItem[] } | null) : null;
			if (mine !== request) return;
			items = body?.items ?? [];
		} catch {
			if (mine === request) items = [];
		} finally {
			if (mine === request) loading = false;
		}
	}

	$effect(() => {
		if (!mediaType || !rowKey) return;
		const query = new URLSearchParams({
			media_type: mediaType,
			row_key: rowKey,
			skip_planning: skipPlanning ? '1' : '0',
			skip_collected: skipCollected ? '1' : '0'
		}).toString();
		clearTimeout(timer);
		timer = setTimeout(() => void refresh(query), 250);
		return () => clearTimeout(timer);
	});
</script>

<section class="ct-settings-section">
	<p class="ct-settings-note">{local.intro}</p>
	<label class="ct-settings-field">
		{local.mediaType}
		<select bind:value={mediaType} onchange={changeType}>
			{#each rss.media_types as type (type.value)}<option value={type.value}>{type.label}</option>{/each}
		</select>
	</label>
	<label class="ct-settings-field">
		{local.row}
		<select bind:value={rowKey}>
			{#each rows as row (row.key)}<option value={row.key}>{row.title}</option>{/each}
		</select>
	</label>
	<label class="ct-settings-check"><input type="checkbox" bind:checked={skipPlanning} /><span>{local.skipPlanning}</span></label>
	<label class="ct-settings-check"><input type="checkbox" bind:checked={skipCollected} /><span>{local.skipCollected}</span></label>
	<CopyField value={feedUrl} label={local.feedUrl} />
	<div aria-busy={loading}>
		{#if items === null}
			<p class="ct-settings-note" role="status">Loading…</p>
		{:else if items.length}
			<ul class="flex gap-3 overflow-x-auto pb-2">
				{#each items as item (`${item.source}:${item.media_type}:${item.media_id}`)}
					<li class="w-24 shrink-0">
						{#if item.image}<img src={item.image} alt="" loading="lazy" class="aspect-[2/3] w-24 rounded-md object-cover" />{/if}
						<p class="mt-1 line-clamp-2 text-xs">{item.title}</p>
						{#if item.release_date}<p class="ct-settings-note text-[11px]">{item.release_date}</p>{/if}
					</li>
				{/each}
			</ul>
		{:else}
			<p class="ct-settings-note">{local.empty}</p>
		{/if}
	</div>
	<p class="ct-settings-note">{local.footA}<a class="ct-settings-link" href={rss.integrations_url || `${BASE}/settings/integrations`}>{local.footLink}</a>{local.footB}</p>
</section>
