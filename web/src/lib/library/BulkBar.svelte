<script lang="ts">
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import { DropdownMenu } from 'bits-ui';
	import { t } from '#lib/strings.ts';
	import { lt } from './menu-strings.ts';
	import { addToCollection, addToList, bulkStatus, bulkTag } from './actions.ts';
	import type { LibraryScreen } from './query.ts';

	type Bulk = NonNullable<LibraryScreen['bulk']>;

	/**
	 * Bulk select's toolbar (bulk_selection_toolbar.html): the count, then
	 * Update Status, Add to List, Add to Collection and Apply Tag (Add or
	 * Remove), and Clear. Each posts the page's own endpoint; `ondone` ends
	 * Select mode and reloads the list with the page's message.
	 */
	let {
		bulk,
		selected,
		onclear,
		ondone
	}: {
		bulk: Bulk;
		selected: number[];
		onclear: () => void;
		ondone: (message: string) => void;
	} = $props();

	let busy = $state(false);
	let problem = $state('');

	async function run(action: () => Promise<{ message: string } | void>) {
		if (busy || !selected.length) return;
		busy = true;
		problem = '';
		try {
			const outcome = await action();
			ondone(outcome?.message ?? '');
		} catch {
			problem = t.bulkFailed;
		} finally {
			busy = false;
		}
	}

	const trigger = 'ct-toolbar-button';
	const item = 'flex h-10 cursor-pointer items-center gap-3 rounded-ct-xs px-3 text-[14px] font-semibold text-text-secondary outline-none data-highlighted:bg-white/8 data-highlighted:text-text';
	const content = 'ct-menu z-50 max-h-[min(60dvh,420px)] min-w-[220px] overflow-y-auto p-1.5 outline-none';
</script>

<div class="ct-bulk-bar" role="toolbar" aria-label={lt.selectItems} aria-busy={busy}>
	<span class="ct-bulk-count" role="status">{t.selectedCount(selected.length)}</span>
	<DropdownMenu.Root>
		<DropdownMenu.Trigger class={trigger} disabled={busy || !selected.length}>
			{lt.updateStatus}<ChevronDown class="size-4" aria-hidden="true" />
		</DropdownMenu.Trigger>
		<DropdownMenu.Portal>
			<DropdownMenu.Content side="top" align="start" sideOffset={8} class={content}>
				{#each bulk.statuses as status (status.value)}
					<DropdownMenu.Item class={item} onSelect={() => run(() => bulkStatus(selected, status.value))}
						>{status.label}</DropdownMenu.Item
					>
				{/each}
			</DropdownMenu.Content>
		</DropdownMenu.Portal>
	</DropdownMenu.Root>
	<DropdownMenu.Root>
		<DropdownMenu.Trigger class={trigger} disabled={busy || !selected.length}>
			{lt.addToList}<ChevronDown class="size-4" aria-hidden="true" />
		</DropdownMenu.Trigger>
		<DropdownMenu.Portal>
			<DropdownMenu.Content side="top" align="start" sideOffset={8} class={content}>
				{#each bulk.lists as list (list.value)}
					<DropdownMenu.Item class={item} onSelect={() => run(() => addToList(selected, list.value))}
						>{list.label}</DropdownMenu.Item
					>
				{:else}
					<p class="px-3 py-2 text-[14px] text-muted">{lt.noEditableLists}</p>
				{/each}
			</DropdownMenu.Content>
		</DropdownMenu.Portal>
	</DropdownMenu.Root>
	<button type="button" class={trigger} disabled={busy || !selected.length} onclick={() => run(() => addToCollection(selected))}
		>{lt.addToCollection}</button
	>
	<DropdownMenu.Root>
		<DropdownMenu.Trigger class={trigger} disabled={busy || !selected.length}>
			{lt.applyTag}<ChevronDown class="size-4" aria-hidden="true" />
		</DropdownMenu.Trigger>
		<DropdownMenu.Portal>
			<DropdownMenu.Content side="top" align="start" sideOffset={8} class={content}>
				{#each bulk.tags as tag (tag)}
					<DropdownMenu.Sub>
						<DropdownMenu.SubTrigger class={item}>
							{tag}<ChevronRight class="ml-auto size-4 text-muted" aria-hidden="true" />
						</DropdownMenu.SubTrigger>
						<DropdownMenu.SubContent class={content}>
							<DropdownMenu.Item class={item} onSelect={() => run(() => bulkTag(selected, tag, 'add'))}>{t.add}</DropdownMenu.Item>
							<DropdownMenu.Item class={item} onSelect={() => run(() => bulkTag(selected, tag, 'remove'))}
								>{lt.remove}</DropdownMenu.Item
							>
						</DropdownMenu.SubContent>
					</DropdownMenu.Sub>
				{:else}
					<p class="px-3 py-2 text-[14px] text-muted">{lt.noTagsYet}</p>
				{/each}
			</DropdownMenu.Content>
		</DropdownMenu.Portal>
	</DropdownMenu.Root>
	<button type="button" class="ct-bulk-clear" disabled={busy || !selected.length} onclick={onclear}>{lt.clear}</button>
	{#if problem}<p class="ct-bulk-problem" role="alert">{problem}</p>{/if}
</div>

<style>
	.ct-bulk-bar {
		position: sticky;
		bottom: calc(16px + env(safe-area-inset-bottom));
		z-index: 30;
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 8px;
		margin-top: 24px;
		padding: 10px;
		border: 1px solid rgb(255 255 255 / 10%);
		border-radius: 20px;
		background-color: rgb(28 28 34 / 92%);
		box-shadow: 0 10px 30px rgb(0 0 0 / 45%);
		backdrop-filter: blur(16px);
	}

	.ct-bulk-count {
		padding-inline: 8px;
		color: var(--color-text);
		font-size: 14px;
		font-weight: 700;
	}

	.ct-bulk-bar :global(.ct-toolbar-button:disabled) {
		opacity: 0.45;
		cursor: default;
	}

	.ct-bulk-clear {
		margin-left: auto;
		padding: 0 12px;
		height: 40px;
		color: var(--color-text-secondary);
		font-size: 14px;
		font-weight: 600;
		cursor: pointer;
	}

	.ct-bulk-clear:disabled {
		opacity: 0.45;
		cursor: default;
	}

	.ct-bulk-problem {
		flex-basis: 100%;
		padding-inline: 8px;
		color: rgb(248 113 113);
		font-size: 13px;
	}

	/* Select mode's cards (B4): loaded with this bar, which shows while selecting. */
	:global(.ct-library-select) {
		display: block;
		width: 100%;
		text-align: left;
		border-radius: var(--radius-ct-sm);
		cursor: pointer;
	}

	:global(.ct-library-select:focus-visible) {
		outline: 2px solid var(--color-accent);
		outline-offset: 2px;
	}

	:global(.ct-select-mark) {
		position: absolute;
		top: 8px;
		left: 8px;
		display: grid;
		width: 24px;
		height: 24px;
		place-items: center;
		border: 2px solid rgb(255 255 255 / 85%);
		border-radius: 999px;
		background-color: rgb(16 16 20 / 55%);
		color: white;
	}

	:global(.ct-library-card.is-selected .ct-select-mark) {
		border-color: var(--color-accent);
		background-color: var(--color-accent);
	}

	/* The check, drawn in CSS. */
	:global(.ct-library-card.is-selected .ct-select-mark::after) {
		content: '';
		width: 6px;
		height: 11px;
		margin-top: -2px;
		border-right: 2.5px solid white;
		border-bottom: 2.5px solid white;
		transform: rotate(45deg);
	}

	:global(.ct-library-card.is-selected .ct-library-poster) {
		box-shadow: 0 0 0 3px var(--color-accent);
	}

	:global(.ct-library-card.is-selecting:not(.is-selected) .ct-library-poster img) {
		opacity: 0.72;
	}

	@media (max-width: 767.98px) {
		.ct-bulk-bar {
			bottom: calc(96px + env(safe-area-inset-bottom));
		}
	}
</style>
