<script lang="ts">
	import Funnel from '@lucide/svelte/icons/funnel';
	import type { Component } from 'svelte';
	import { t } from '#lib/strings.ts';
	import {
		filterLabel,
		hasFilters,
		type LibraryFilterOptions,
		type LibraryFilters,
		type ParamChanges
	} from './filters.ts';

	/**
	 * The filter button, with the menu loaded on first use: the menu and its
	 * popover are kept out of the Library's first load (bundle budget). Hover
	 * or focus starts the download; a click opens the menu once it is in.
	 */
	let {
		filters,
		options,
		onapply
	}: {
		filters: LibraryFilters;
		options: LibraryFilterOptions;
		onapply: (changes: ParamChanges) => void;
	} = $props();

	type MenuProps = {
		filters: LibraryFilters;
		options: LibraryFilterOptions;
		onapply: (changes: ParamChanges) => void;
		initialOpen?: boolean;
	};
	let Menu = $state<Component<MenuProps> | null>(null);
	let openOnLoad = $state(false);
	let loading: Promise<void> | null = null;

	function load(open = false) {
		if (open) openOnLoad = true;
		loading ??= import('./FilterMenu.svelte').then((module) => {
			Menu = module.default as Component<MenuProps>;
		});
	}

	const label = $derived(filterLabel(filters, options));
</script>

{#if Menu}
	<Menu {filters} {options} {onapply} initialOpen={openOnLoad} />
{:else}
	<button
		type="button"
		class="ct-toolbar-button"
		aria-label={t.filter}
		aria-haspopup="dialog"
		data-active={hasFilters(filters, options)}
		onpointerenter={() => load()}
		onfocus={() => load()}
		onclick={() => load(true)}
	>
		<Funnel class="size-4" aria-hidden="true" />
		<span class="ct-toolbar-label">{label === 'All' ? t.filter : label}</span>
	</button>
{/if}
