<script lang="ts">
	import Settings2 from '@lucide/svelte/icons/settings-2';
	import { DropdownMenu } from 'bits-ui';
	import { t } from '#lib/strings.ts';
	import type { ViewMenuProps } from './view-menu.ts';

	/**
	 * View settings (media_settings_menu.html): Show matching entries
	 * separately, Share View, and Select Items / Cancel Select. The grid /
	 * table choice is the switch beside it.
	 */
	let {
		grouping,
		canSelect,
		selecting,
		sharing,
		ongrouping,
		onshare,
		onselect,
		initialOpen = false
	}: ViewMenuProps = $props();

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
					{t.showEntriesSeparately}
					<span class="ml-auto text-[12px] text-muted">{grouping.enabled ? t.on : t.off}</span>
				</DropdownMenu.Item>
			{/if}
			<DropdownMenu.Item class={item} disabled={sharing} onSelect={onshare}>
				{sharing ? t.sharing : t.shareView}
			</DropdownMenu.Item>
			{#if canSelect}
				<DropdownMenu.Item class={item} onSelect={onselect}>
					{selecting ? t.cancelSelect : t.selectItems}
				</DropdownMenu.Item>
			{/if}
		</DropdownMenu.Content>
	</DropdownMenu.Portal>
</DropdownMenu.Root>
