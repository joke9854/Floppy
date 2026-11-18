<script lang="ts">
	import Check from '@lucide/svelte/icons/check';
	import { DropdownMenu } from 'bits-ui';
	import type { Snippet } from 'svelte';

	/**
	 * A toolbar menu that picks one value (bits-ui: keyboard, focus, Escape,
	 * outside click). Choosing calls `onselect`; the URL, not the menu, holds
	 * the state, so the page reloads its list from it.
	 */
	let {
		label,
		options,
		value,
		onselect,
		triggerClass = 'ct-toolbar-button',
		trigger,
		footer
	}: {
		label: string;
		options: { value: string; label: string }[];
		value: string;
		onselect: (value: string) => void;
		triggerClass?: string;
		trigger: Snippet;
		footer?: Snippet;
	} = $props();
</script>

<DropdownMenu.Root>
	<DropdownMenu.Trigger class={triggerClass} aria-label={label}>
		{@render trigger()}
	</DropdownMenu.Trigger>
	<DropdownMenu.Portal>
		<DropdownMenu.Content
			side="bottom"
			align="end"
			sideOffset={8}
			class="ct-menu z-50 max-h-[min(70dvh,520px)] min-w-[220px] overflow-y-auto p-1.5 outline-none"
		>
			<DropdownMenu.RadioGroup {value} onValueChange={(next) => next && onselect(next)}>
				{#each options as option (option.value)}
					<DropdownMenu.RadioItem
						value={option.value}
						class="flex h-10 cursor-pointer items-center justify-between gap-3 rounded-ct-xs px-3 text-[14px] font-semibold text-text-secondary outline-none data-highlighted:bg-white/8 data-highlighted:text-text"
					>
						{#snippet children({ checked })}
							{option.label}
							{#if checked}<Check class="size-4 text-accent" aria-hidden="true" />{/if}
						{/snippet}
					</DropdownMenu.RadioItem>
				{/each}
			</DropdownMenu.RadioGroup>
			{#if footer}
				<DropdownMenu.Separator class="my-1 h-px bg-white/8" />
				{@render footer()}
			{/if}
		</DropdownMenu.Content>
	</DropdownMenu.Portal>
</DropdownMenu.Root>
