<script lang="ts">
	import ArrowDown from '@lucide/svelte/icons/arrow-down';
	import ArrowUp from '@lucide/svelte/icons/arrow-up';
	import Columns3 from '@lucide/svelte/icons/columns-3';
	import { Popover } from 'bits-ui';
	import { invalidateAll } from '$app/navigation';
	import { djangoWrite } from '#lib/csrf.ts';
	import { lt } from './menu-strings.ts';
	import type { LibraryScreen } from './query.ts';

	type Column = LibraryScreen['column_config'][number];

	/**
	 * The table's column menu (the Django "Configure Table Columns"): show or
	 * hide a column, move it up or down, or reset to defaults. Each change is
	 * saved at once to the user's table preferences, then the list reloads.
	 */
	let {
		mediaType,
		sort,
		config,
		defaults,
		initialOpen = false,
		tableType = 'media'
	}: {
		mediaType: string;
		sort: string;
		config: Column[];
		defaults: Column[];
		initialOpen?: boolean;
		/** The table the columns belong to: the Library's, or a list's (P4-I2). */
		tableType?: 'media' | 'list';
	} = $props();

	// svelte-ignore state_referenced_locally
	let open = $state(initialOpen);
	let saving = $state(false);
	let failed = $state(false);

	async function save(columns: Column[]) {
		saving = true;
		failed = false;
		try {
			const response = await djangoWrite('/api/v1/user/table-columns/', 'PUT', {
				table_type: tableType,
				media_type: mediaType,
				sort,
				order: columns.map((column) => column.key),
				hidden: columns.filter((column) => !column.visible).map((column) => column.key)
			});
			if (!response.ok) throw new Error(String(response.status));
			await invalidateAll();
		} catch {
			failed = true;
		} finally {
			saving = false;
		}
	}

	function toggle(index: number) {
		save(config.map((column, at) => (at === index ? { ...column, visible: !column.visible } : column)));
	}

	function move(index: number, by: number) {
		const columns = [...config];
		const [column] = columns.splice(index, 1);
		columns.splice(index + by, 0, column);
		save(columns);
	}
</script>

<Popover.Root bind:open>
	<Popover.Trigger class="ct-toolbar-button" aria-label={lt.columns}>
		<Columns3 class="size-4" aria-hidden="true" />
		<span class="ct-toolbar-label">{lt.columns}</span>
	</Popover.Trigger>
	<Popover.Portal>
		<Popover.Content
			side="bottom"
			align="end"
			sideOffset={8}
			class="ct-menu z-50 max-h-[min(72dvh,560px)] w-[280px] max-w-[calc(100vw-24px)] overflow-y-auto p-1.5 outline-none"
		>
			<p class="ct-columns-title">{lt.configureColumns}</p>
			<ul class="ct-columns" aria-busy={saving}>
				{#each config as column, index (column.key)}
					<li>
						<label>
							<input
								type="checkbox"
								checked={column.visible}
								disabled={saving}
								onchange={() => toggle(index)}
							/>
							<span>{column.label}</span>
						</label>
						<button
							type="button"
							aria-label={lt.moveUp(column.label)}
							disabled={saving || index === 0}
							onclick={() => move(index, -1)}><ArrowUp class="size-3.5" aria-hidden="true" /></button
						>
						<button
							type="button"
							aria-label={lt.moveDown(column.label)}
							disabled={saving || index === config.length - 1}
							onclick={() => move(index, 1)}><ArrowDown class="size-3.5" aria-hidden="true" /></button
						>
					</li>
				{/each}
			</ul>
			{#if failed}<p class="ct-columns-problem" role="alert">{lt.columnsFailed}</p>{/if}
			<button type="button" class="ct-columns-reset" disabled={saving} onclick={() => save(defaults)}
				>{lt.resetDefaults}</button
			>
		</Popover.Content>
	</Popover.Portal>
</Popover.Root>

<style>
	.ct-columns-title {
		padding: 8px 10px 6px;
		color: var(--color-muted);
		font-size: 12px;
		font-weight: 600;
	}

	.ct-columns li {
		display: flex;
		align-items: center;
		gap: 2px;
		border-radius: 8px;
	}

	.ct-columns li:hover {
		background-color: rgb(255 255 255 / 5%);
	}

	.ct-columns label {
		display: flex;
		flex: 1;
		align-items: center;
		gap: 10px;
		min-height: 36px;
		padding-inline: 10px;
		color: var(--color-text);
		font-size: 14px;
		cursor: pointer;
	}

	.ct-columns input {
		accent-color: var(--color-accent);
	}

	.ct-columns li button {
		display: grid;
		place-items: center;
		width: 28px;
		height: 28px;
		border-radius: 6px;
		color: var(--color-text-secondary);
		cursor: pointer;
	}

	.ct-columns li button:hover:not(:disabled) {
		background-color: rgb(255 255 255 / 8%);
		color: var(--color-text);
	}

	.ct-columns li button:disabled {
		opacity: 0.3;
		cursor: default;
	}

	.ct-columns-reset {
		width: 100%;
		margin-top: 4px;
		padding: 10px;
		border-top: 1px solid rgb(255 255 255 / 8%);
		color: var(--color-text-secondary);
		font-size: 14px;
		font-weight: 600;
		text-align: left;
		cursor: pointer;
	}

	.ct-columns-reset:hover:not(:disabled) {
		color: var(--color-text);
	}

	.ct-columns-problem {
		padding: 6px 10px;
		color: rgb(248 113 113);
		font-size: 13px;
	}
</style>
