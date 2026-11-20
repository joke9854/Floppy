<script lang="ts">
	import Columns3 from '@lucide/svelte/icons/columns-3';
	import type { Component } from 'svelte';
	import { t } from '#lib/strings.ts';
	import { lazyComponent } from './lazy.ts';
	import type { LibraryScreen } from './query.ts';

	/** The Columns button, with its menu loaded on first use (bundle budget). */
	type Props = {
		mediaType: string;
		sort: string;
		config: LibraryScreen['column_config'];
		defaults: LibraryScreen['column_defaults'];
		initialOpen?: boolean;
	};
	let props: Props = $props();

	let Menu = $state<Component<Props> | null>(null);
	let openOnLoad = $state(false);

	function load(open = false) {
		if (open) openOnLoad = true;
		lazyComponent<Props>('column-menu', () => import('./ColumnMenu.svelte')).then((menu) => {
			Menu = menu;
		});
	}
</script>

{#if Menu}
	<Menu {...props} initialOpen={openOnLoad} />
{:else}
	<button
		type="button"
		class="ct-toolbar-button"
		aria-label={t.columns}
		aria-haspopup="dialog"
		onpointerenter={() => load()}
		onfocus={() => load()}
		onclick={() => load(true)}
	>
		<Columns3 class="size-4" aria-hidden="true" />
		<span class="ct-toolbar-label">{t.columns}</span>
	</button>
{/if}
