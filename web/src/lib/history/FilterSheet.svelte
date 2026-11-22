<script lang="ts">
	import X from '@lucide/svelte/icons/x';
	import { Dialog } from 'bits-ui';
	import { t } from '#lib/strings.ts';
	import { ht } from './strings.ts';
	import type { HistoryChoice } from './types.ts';

	/**
	 * The Filter History sheet (P4-E), as history.html's: a date range, media
	 * types, Activity or Release dates, a genre and (for all types or music)
	 * an implied genre. Apply changes the page's query; Clear removes them.
	 */
	let {
		params,
		types,
		onapply,
		onclose
	}: {
		params: { get(name: string): string | null };
		types: HistoryChoice[];
		onapply: (changes: Record<string, string | null>) => void;
		onclose: () => void;
	} = $props();

	// svelte-ignore state_referenced_locally
	let start = $state(params.get('start-date') ?? '');
	// svelte-ignore state_referenced_locally
	let end = $state(params.get('end-date') ?? '');
	// svelte-ignore state_referenced_locally
	let picked = $state<string[]>((params.get('media_type') ?? '').split(',').filter(Boolean));
	// svelte-ignore state_referenced_locally
	let mode = $state(params.get('history_mode') === 'release' ? 'release' : 'activity');
	// svelte-ignore state_referenced_locally
	let genre = $state(params.get('genre') ?? '');
	// svelte-ignore state_referenced_locally
	let implied = $state(params.get('implied_genre') ?? '');
	let genres = $state.raw<{ genres: string[]; implied_genres: string[] } | null>(null);

	const genreNames = $derived(genres?.genres ?? (genre ? [genre] : []));
	const impliedNames = $derived(genres?.implied_genres ?? (implied ? [implied] : []));
	const showImplied = $derived(picked.length === 0 || (picked.length === 1 && picked[0] === 'music'));

	$effect(() => {
		fetch('/api/v1/history/genres/', { credentials: 'same-origin' })
			.then((response) => (response.ok ? response.json() : null))
			.then((body) => (genres = body ?? { genres: [], implied_genres: [] }))
			.catch(() => (genres = { genres: [], implied_genres: [] }));
	});

	function apply() {
		onapply({
			'start-date': start || null,
			'end-date': end || null,
			media_type: picked.join(',') || null,
			history_mode: mode === 'release' ? 'release' : null,
			genre: genre || null,
			implied_genre: showImplied ? implied || null : null
		});
	}
</script>

<Dialog.Root open onOpenChange={(open) => !open && onclose()}>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/70" />
		<Dialog.Content class="ct-history-sheet outline-none" aria-describedby={undefined}>
			<header class="ct-history-sheet__head">
				<Dialog.Title class="ct-history-sheet__title">{ht.filterHistory}</Dialog.Title>
				<Dialog.Close class="ct-history-action" aria-label={t.close}><X class="size-5" aria-hidden="true" /></Dialog.Close>
			</header>
			<div class="ct-history-sheet__grid">
				<label class="ct-history-field">
					<span>{ht.from}</span>
					<input type="date" bind:value={start} />
				</label>
				<label class="ct-history-field">
					<span>{ht.to}</span>
					<input type="date" bind:value={end} />
				</label>
			</div>
			<fieldset class="ct-history-field">
				<legend>{ht.mediaType}</legend>
				<div class="ct-history-checks">
					{#each types as type (type.value)}
						<label>
							<input
								type="checkbox"
								checked={picked.includes(type.value)}
								onchange={(e) =>
									(picked = e.currentTarget.checked ? [...picked, type.value] : picked.filter((value) => value !== type.value))}
							/>
							{type.label}
						</label>
					{/each}
				</div>
				{#if !picked.length}<p class="ct-history-hint">{ht.allTypes}</p>{/if}
			</fieldset>
			<label class="ct-history-field">
				<span>{ht.viewMode}</span>
				<select bind:value={mode}>
					<option value="activity">{ht.activity}</option>
					<option value="release">{ht.releases}</option>
				</select>
			</label>
			<label class="ct-history-field">
				<span>{ht.genre}</span>
				<select bind:value={genre} disabled={!genres}>
					<option value="">{ht.allGenres}</option>
					{#each genreNames as name (name)}
						<option value={name}>{name}</option>
					{/each}
				</select>
			</label>
			{#if showImplied}
				<label class="ct-history-field">
					<span>{ht.impliedGenre}</span>
					<select bind:value={implied} disabled={!genres}>
						<option value="">{ht.allGenres}</option>
						{#each impliedNames as name (name)}
							<option value={name}>{name}</option>
						{/each}
					</select>
				</label>
			{/if}
			<footer class="ct-history-sheet__actions">
				<button
					type="button"
					class="ct-history-btn"
					onclick={() =>
						onapply({
							'start-date': null,
							'end-date': null,
							media_type: null,
							history_mode: null,
							genre: null,
							implied_genre: null
						})}>{ht.clearFilters}</button
				>
				<button type="button" class="ct-history-btn is-primary" onclick={apply}>{ht.apply}</button>
			</footer>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
