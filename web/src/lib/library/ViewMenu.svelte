<script lang="ts">
	import Settings2 from '@lucide/svelte/icons/settings-2';
	import { DropdownMenu } from 'bits-ui';
	import { invalidateAll } from '$app/navigation';
	import { t } from '#lib/strings.ts';
	import { setEntryGrouping, shareView } from './actions.ts';
	import { lt } from './menu-strings.ts';
	import type { ViewMenuProps } from './view-menu.ts';

	/**
	 * View settings (media_settings_menu.html): Show matching entries
	 * separately, Share View, and Select Items / Cancel Select. The grid /
	 * table choice is the switch beside it.
	 */
	let {
		mediaType,
		search,
		grouping,
		canSelect,
		selecting,
		onselect,
		onnotice,
		initialOpen = false
	}: ViewMenuProps = $props();

	let sharing = $state(false);

	async function onshare() {
		// Opened inside the click, so the browser does not block it as a pop-up.
		const tab = window.open('', '_blank');
		sharing = true;
		try {
			const url = await shareView(mediaType, search);
			if (tab) tab.location.href = url;
			else window.open(url, '_blank');
		} catch {
			tab?.close();
			onnotice(t.shareFailed);
		} finally {
			sharing = false;
		}
	}

	async function ongrouping() {
		if (!grouping) return;
		try {
			await setEntryGrouping(mediaType, !grouping.enabled);
			await invalidateAll();
		} catch {
			onnotice(t.bulkFailed);
		}
	}

	// svelte-ignore state_referenced_locally
	let open = $state(initialOpen);
	const item =
		'flex h-10 cursor-pointer items-center gap-3 rounded-ct-xs px-3 text-[14px] font-semibold text-text-secondary outline-none data-highlighted:bg-white/8 data-highlighted:text-text';
</script>

<DropdownMenu.Root bind:open>
	<DropdownMenu.Trigger class="ct-toolbar-button ct-icon-button" aria-label={t.viewSettings} title={t.viewSettings}>
		<Settings2 class="size-4" aria-hidden="true" />
	</DropdownMenu.Trigger>
	<DropdownMenu.Portal>
		<DropdownMenu.Content side="bottom" align="end" sideOffset={8} class="ct-menu z-50 min-w-[260px] p-1.5 outline-none">
			{#if grouping}
				<DropdownMenu.Item class={item} onSelect={ongrouping}>
					{lt.showEntriesSeparately}
					<span class="ml-auto text-[12px] text-muted">{grouping.enabled ? lt.on : lt.off}</span>
				</DropdownMenu.Item>
			{/if}
			<DropdownMenu.Item class={item} disabled={sharing} onSelect={onshare}>
				{sharing ? lt.sharing : lt.shareView}
			</DropdownMenu.Item>
			{#if canSelect}
				<DropdownMenu.Item class={item} onSelect={onselect}>
					{selecting ? lt.cancelSelect : lt.selectItems}
				</DropdownMenu.Item>
			{/if}
		</DropdownMenu.Content>
	</DropdownMenu.Portal>
</DropdownMenu.Root>
