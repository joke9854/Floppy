<script lang="ts">
	import { djangoForm } from '#lib/csrf.ts';
	import Dialog from '#lib/ui/Dialog.svelte';
	import { dc } from './strings.ts';

	/**
	 * A Discover card's Lists dialog (the page's lists_modal,
	 * fill_lists.html): the user's manual lists with Add or Remove for this
	 * title, the tag filter and "On N lists". Opening it creates the title's
	 * Item when it has none, as the page does.
	 */
	let { url = $bindable(null) }: { url?: string | null } = $props();

	interface ListsPayload {
		item_id: number;
		title: string;
		toggle_url: string;
		tags: string[];
		selected_tag: string;
		on_list_count: number;
		lists: { id: number; name: string; has_item: boolean }[];
	}

	let payload = $state<ListsPayload | null>(null);
	let failed = $state('');
	let busy = $state<number | null>(null);
	let tag = $state('');
	let open = $derived(url !== null);

	async function load(source: string, filter: string) {
		failed = '';
		try {
			const query = filter ? `?${new URLSearchParams({ tag: filter })}` : '';
			const response = await fetch(`${source}${query}`, {
				credentials: 'same-origin',
				headers: { accept: 'application/json' }
			});
			if (!response.ok) throw new Error(String(response.status));
			const next: ListsPayload = await response.json();
			if (url === source) payload = next;
		} catch {
			if (url === source) failed = dc.failed;
		}
	}

	$effect(() => {
		// A new card: start from all lists.
		if (url) {
			payload = null;
			tag = '';
			load(url, '');
		}
	});

	async function toggle(listId: number) {
		if (!payload || busy !== null) return;
		busy = listId;
		try {
			const response = await djangoForm(
				payload.toggle_url,
				{ item_id: String(payload.item_id), custom_list_id: String(listId) },
				{ json: true }
			);
			const body = await response.json();
			if (!response.ok) throw new Error(body.error ?? String(response.status));
			const list = payload.lists.find((entry) => entry.id === listId);
			if (list && list.has_item !== body.has_item) {
				list.has_item = body.has_item;
				payload.on_list_count += body.has_item ? 1 : -1;
			}
		} catch (error) {
			failed = error instanceof Error && error.message && !/^\d+$/.test(error.message) ? error.message : dc.failed;
		}
		busy = null;
	}

	function filterBy(value: string) {
		tag = value;
		if (url) load(url, value);
	}
</script>

<Dialog
	bind:open={() => open, (value) => {
		if (!value) url = null;
	}}
	title={dc.lists}
	sheet
>
	{#if payload}
		{#if payload.tags.length}
			<div class="ct-lists-filter">
				<label for="ct-lists-tag">{dc.filterByTag}</label>
				<select id="ct-lists-tag" value={tag} onchange={(event) => filterBy(event.currentTarget.value)}>
					<option value="">{dc.allLists}</option>
					{#each payload.tags as entry (entry)}
						<option value={entry}>{entry}</option>
					{/each}
				</select>
			</div>
		{/if}
		{#if payload.on_list_count}
			<p class="ct-lists-count">{dc.onLists(payload.on_list_count)}</p>
		{/if}
		<ul class="ct-lists-rows">
			{#each payload.lists as list (list.id)}
				<li class="ct-lists-row">
					<span>{list.name}</span>
					<button
						type="button"
						class={['ct-lists-toggle', list.has_item && 'is-on']}
						disabled={busy === list.id}
						aria-label={list.has_item ? dc.removeFrom(list.name) : dc.addTo(list.name)}
						onclick={() => toggle(list.id)}
					>
						{list.has_item ? dc.remove : dc.add}
					</button>
				</li>
			{:else}
				<li class="ct-lists-empty">{dc.noLists}</li>
			{/each}
		</ul>
	{:else if !failed}
		<p class="ct-lists-empty" aria-live="polite">{dc.loadingLists}</p>
	{/if}
	{#if failed}<p class="ct-lists-error" role="alert">{failed}</p>{/if}
</Dialog>
