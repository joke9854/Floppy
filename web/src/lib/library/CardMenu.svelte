<script lang="ts">
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import Ellipsis from '@lucide/svelte/icons/ellipsis';
	import { DropdownMenu } from 'bits-ui';
	import { t } from '#lib/strings.ts';
	import { addToList } from './actions.ts';
	import { lt } from './menu-strings.ts';
	import { openTrack } from '#lib/track/open.svelte.ts';
	import { TRACK_TYPES, trackTargetFromUrl } from '#lib/track/targets.ts';

	type Choice = { value: string; label: string };

	/**
	 * A Library card's menu (B5), as the page's hover buttons: Edit tracking
	 * (the Django page's track window until P4-D), Add to List, History.
	 */
	let {
		title,
		mediaType,
		url,
		historyUrl,
		lists,
		itemId,
		onnotice,
		initialOpen = false
	}: {
		title: string;
		mediaType: string;
		url: string;
		historyUrl: string;
		lists: Choice[];
		itemId: number;
		onnotice?: (message: string) => void;
		initialOpen?: boolean;
	} = $props();

	// svelte-ignore state_referenced_locally
	let open = $state(initialOpen);

	async function onaddtolist(list: Choice) {
		try {
			onnotice?.((await addToList([itemId], list.value)).message);
		} catch {
			onnotice?.(t.bulkFailed);
		}
	}

	/** The web track dialog for the types it edits; the Django page for the rest. */
	function editTracking() {
		const target = TRACK_TYPES.has(mediaType) ? trackTargetFromUrl(url, mediaType) : null;
		if (target) openTrack(target);
		else location.href = url;
	}
	const item =
		'flex h-10 cursor-pointer items-center gap-3 rounded-ct-xs px-3 text-[14px] font-semibold text-text-secondary outline-none data-highlighted:bg-white/8 data-highlighted:text-text';
</script>

<DropdownMenu.Root bind:open>
	<DropdownMenu.Trigger class="ct-card-menu" aria-label={t.cardActions(title)}>
		<Ellipsis class="size-4" aria-hidden="true" />
	</DropdownMenu.Trigger>
	<DropdownMenu.Portal>
		<DropdownMenu.Content
			side="bottom"
			align="start"
			sideOffset={6}
			class="ct-menu z-50 max-h-[min(70dvh,480px)] min-w-[220px] overflow-y-auto p-1.5 outline-none"
		>
			<DropdownMenu.Item class={item} onSelect={editTracking}>{lt.editTracking}</DropdownMenu.Item>
			{#if lists.length}
				<DropdownMenu.Sub>
					<DropdownMenu.SubTrigger class={item}>
						{lt.addToList}
						<ChevronRight class="ml-auto size-4 text-muted" aria-hidden="true" />
					</DropdownMenu.SubTrigger>
					<DropdownMenu.SubContent
						class="ct-menu z-50 max-h-[min(60dvh,400px)] min-w-[200px] overflow-y-auto p-1.5 outline-none"
					>
						{#each lists as list (list.value)}
							<DropdownMenu.Item class={item} onSelect={() => onaddtolist(list)}>{list.label}</DropdownMenu.Item>
						{/each}
					</DropdownMenu.SubContent>
				</DropdownMenu.Sub>
			{/if}
			{#if historyUrl}
				<DropdownMenu.Item class={item} onSelect={() => (location.href = historyUrl)}>{lt.viewHistory}</DropdownMenu.Item>
			{/if}
		</DropdownMenu.Content>
	</DropdownMenu.Portal>
</DropdownMenu.Root>
