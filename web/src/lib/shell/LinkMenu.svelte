<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import type { Snippet } from 'svelte';
	import { reloadFor, type NavItem } from './nav.ts';

	/** A menu of links (bits-ui: keyboard, focus, Escape, outside click). */
	let {
		items,
		heading = '',
		side = 'right',
		align = 'start',
		triggerClass,
		triggerLabel,
		trigger,
		footer
	}: {
		items: NavItem[];
		heading?: string;
		side?: 'right' | 'top' | 'bottom' | 'left';
		align?: 'start' | 'center' | 'end';
		triggerClass: string;
		triggerLabel: string;
		trigger: Snippet;
		footer?: Snippet;
	} = $props();
</script>

<DropdownMenu.Root>
	<DropdownMenu.Trigger class={triggerClass} aria-label={triggerLabel} title={triggerLabel}>
		{@render trigger()}
	</DropdownMenu.Trigger>
	<DropdownMenu.Portal>
		<DropdownMenu.Content
			{side}
			{align}
			sideOffset={8}
			class="ct-menu z-50 min-w-[220px] p-1.5 outline-none"
		>
			{#if heading}
				<p class="px-3 pb-1 pt-2 text-xs font-bold tracking-wide text-muted uppercase">{heading}</p>
			{/if}
			{#each items as item (item.href)}
				{@const Icon = item.icon}
				<DropdownMenu.Item>
					{#snippet child({ props })}
						<a
							{...props}
							href={item.href}
							data-sveltekit-reload={reloadFor(item.href)}
							class="flex h-10 items-center gap-3 rounded-ct-xs px-3 text-[14px] font-semibold text-text-secondary outline-none data-highlighted:bg-white/8 data-highlighted:text-text"
						>
							<Icon class="size-5 text-muted" aria-hidden="true" />
							{item.label}
						</a>
					{/snippet}
				</DropdownMenu.Item>
			{/each}
			{#if footer}
				<DropdownMenu.Separator class="my-1 h-px bg-white/8" />
				{@render footer()}
			{/if}
		</DropdownMenu.Content>
	</DropdownMenu.Portal>
</DropdownMenu.Root>
