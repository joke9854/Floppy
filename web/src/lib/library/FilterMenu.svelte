<script lang="ts">
	import Check from '@lucide/svelte/icons/check';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import Funnel from '@lucide/svelte/icons/funnel';
	import { Popover } from 'bits-ui';
	import { t } from '#lib/strings.ts';
	import {
		COLLECTION_LABELS,
		PROGRESS_LABELS,
		RATING_LABELS,
		RELEASE_LABELS,
		clearFilters,
		completedLabel,
		filterLabel,
		hasFilters,
		matching,
		nextMode,
		toggled,
		type LibraryFilterOptions,
		type LibraryFilters,
		type ParamChanges
	} from './filters.ts';

	/**
	 * The Library's filter menu (filter_menu.html): a root list of filters,
	 * each opening its pane. A single-value pick applies and closes, as on
	 * the Django page; tags and platforms toggle and stay open. The URL holds
	 * the state, so `onapply` only changes it.
	 */
	let {
		filters,
		options,
		onapply,
		initialOpen = false
	}: {
		filters: LibraryFilters;
		options: LibraryFilterOptions;
		onapply: (changes: ParamChanges) => void;
		initialOpen?: boolean;
	} = $props();

	type Pane =
		| 'root'
		| 'rating'
		| 'collection'
		| 'progress'
		| 'genre'
		| 'implied_genre'
		| 'date'
		| 'release'
		| 'source'
		| 'media_status'
		| 'language'
		| 'country'
		| 'platform'
		| 'origin'
		| 'format'
		| 'author'
		| 'provider'
		| 'tag';

	// Opened by the click that loaded it (LazyFilterMenu).
	// svelte-ignore state_referenced_locally
	let open = $state(initialOpen);
	let pane = $state<Pane>('root');
	let search = $state('');
	// The custom completed-date range and window, edited before Apply.
	let rangeFrom = $state('');
	let rangeTo = $state('');
	let within = $state<string | number>('');
	let withinUnit = $state('days');

	function show(next: Pane) {
		pane = next;
		search = '';
		if (next === 'date') {
			rangeFrom = filters.completed_date_from;
			rangeTo = filters.completed_date_to;
			within = filters.completed_date_within;
			withinUnit = filters.completed_date_within_unit || 'days';
		}
	}

	function apply(changes: ParamChanges, close = true) {
		onapply(changes);
		if (close) {
			open = false;
			pane = 'root';
		}
	}

	const label = $derived(filterLabel(filters, options));
	const active = $derived(hasFilters(filters, options));
	const label3 = (labels: Record<string, string>, value: string) =>
		value && value !== 'all' ? (labels[value] ?? value) : t.any;
	const providerOptions = $derived([
		...options.providers,
		...options.all_providers.filter(
			(option) => !options.providers.some((pinned) => pinned.value === option.value)
		)
	]);

	type Row = { pane: Pane; title: string; value: string; when: boolean; divider?: boolean };
	const rows = $derived<Row[]>([
		{ pane: 'rating', title: t.rating, value: label3(RATING_LABELS, filters.rating), when: true, divider: true },
		{ pane: 'collection', title: t.collection, value: label3(COLLECTION_LABELS, filters.collection), when: true },
		{
			pane: 'progress',
			title: t.progress,
			value: label3(PROGRESS_LABELS, filters.progress),
			when: options.show_progress
		},
		{ pane: 'genre', title: t.genre, value: filters.genre || t.any, when: options.genres.length > 0, divider: true },
		{
			pane: 'implied_genre',
			title: t.impliedGenre,
			value: filters.implied_genre || t.any,
			when: options.implied_genres.length > 0
		},
		{
			pane: 'date',
			title: t.date,
			value:
				(filters.year ? (filters.year === 'unknown' ? t.unknown : filters.year) : '') ||
				completedLabel(filters, options) ||
				t.any,
			when: options.years.length > 0
		},
		{ pane: 'release', title: t.released, value: label3(RELEASE_LABELS, filters.release), when: true },
		{ pane: 'source', title: t.source, value: filters.source ? filters.source.toUpperCase() : t.any, when: options.sources.length > 0 },
		{ pane: 'media_status', title: t.availability, value: filters.media_status || t.any, when: options.media_statuses.length > 0 },
		{ pane: 'language', title: t.language, value: filters.language || t.any, when: options.show_languages },
		{ pane: 'country', title: t.country, value: filters.country || t.any, when: options.show_countries },
		{
			pane: 'platform',
			title: t.platform,
			value: filters.platforms.length ? t.selectedCount(filters.platforms.length) : t.any,
			when: options.show_platforms
		},
		{ pane: 'origin', title: t.origin, value: filters.origin || t.any, when: options.show_origins },
		{ pane: 'format', title: t.format, value: filters.format || t.any, when: options.show_formats },
		{
			pane: 'author',
			title: t.author,
			value: filters.author || t.any,
			when: options.show_authors && options.authors.length > 0
		},
		{ pane: 'provider', title: t.streamingService, value: filters.provider || t.any, when: options.show_providers },
		{
			pane: 'tag',
			title: t.tag,
			value: filters.tags.length ? t.selectedCount(filters.tags.length) : t.any,
			when: options.tags.length > 0,
			divider: true
		}
	]);

	// The single-value list panes: their parameter, options and current value.
	const lists = $derived<Partial<Record<Pane, { param: string; options: { value: string; label: string }[]; value: string; searchable: boolean }>>>({
		genre: { param: 'genre', options: options.genres, value: filters.genre, searchable: true },
		implied_genre: {
			param: 'implied_genre',
			options: options.implied_genres,
			value: filters.implied_genre,
			searchable: true
		},
		source: { param: 'source', options: options.sources, value: filters.source, searchable: false },
		media_status: {
			param: 'media_status',
			options: options.media_statuses,
			value: filters.media_status,
			searchable: false
		},
		language: { param: 'language', options: options.languages, value: filters.language, searchable: true },
		country: { param: 'country', options: options.countries, value: filters.country, searchable: true },
		origin: { param: 'origin', options: options.origins, value: filters.origin, searchable: true },
		format: { param: 'format', options: options.formats, value: filters.format, searchable: false },
		author: { param: 'author', options: options.authors, value: filters.author, searchable: true },
		provider: { param: 'provider', options: providerOptions, value: filters.provider, searchable: true }
	});
	const threeWay = $derived<Partial<Record<Pane, { param: string; labels: Record<string, string>; value: string }>>>({
		rating: { param: 'rating', labels: RATING_LABELS, value: filters.rating || 'all' },
		collection: { param: 'collection', labels: COLLECTION_LABELS, value: filters.collection || 'all' },
		progress: { param: 'progress', labels: PROGRESS_LABELS, value: filters.progress || 'all' },
		release: { param: 'release', labels: RELEASE_LABELS, value: filters.release || 'all' }
	});
	const paneTitle = $derived(rows.find((row) => row.pane === pane)?.title ?? '');
	const completedYear = $derived(
		filters.completed_date_from.endsWith('-01-01') &&
			filters.completed_date_to === `${filters.completed_date_from.slice(0, 4)}-12-31`
			? filters.completed_date_from.slice(0, 4)
			: ''
	);
	const completedOff = {
		completed_date_from: null,
		completed_date_to: null,
		completed_date_within: null,
		completed_date_within_unit: null
	};
</script>

<Popover.Root bind:open onOpenChange={(next) => next && show('root')}>
	<Popover.Trigger class="ct-toolbar-button" aria-label={t.filter} data-active={active}>
		<Funnel class="size-4" aria-hidden="true" />
		<span class="ct-toolbar-label">{label === 'All' ? t.filter : label}</span>
	</Popover.Trigger>
	<Popover.Portal>
		<Popover.Content
			side="bottom"
			align="end"
			sideOffset={8}
			class="ct-menu ct-filter-menu z-50 max-h-[min(72dvh,560px)] w-[300px] max-w-[calc(100vw-24px)] overflow-y-auto p-1.5 outline-none"
		>
			{#if pane === 'root'}
				<button type="button" class="ct-filter-row" onclick={() => apply(clearFilters())}>
					<span>{t.all}</span>
					{#if !active}<span class="ct-filter-value">{t.active}</span>{/if}
				</button>
				{#each rows.filter((row) => row.when) as row (row.pane)}
					{#if row.divider}<div class="ct-filter-divider"></div>{/if}
					<button type="button" class="ct-filter-row" onclick={() => show(row.pane)}>
						<span>{row.title}</span>
						<span class="ct-filter-value">{row.value}</span>
						<ChevronRight class="size-3.5 flex-none text-muted" aria-hidden="true" />
					</button>
				{/each}
			{:else}
				<div class="ct-filter-head">
					<button type="button" class="ct-filter-back" aria-label={t.back} onclick={() => show('root')}>
						<ChevronLeft class="size-4" aria-hidden="true" />
					</button>
					<span class="ct-filter-title">{paneTitle}</span>
					{#if pane === 'tag' || pane === 'platform'}
						{@const param = pane === 'tag' ? 'tag_mode' : 'platform_mode'}
						{@const mode = (pane === 'tag' ? filters.tag_mode : filters.platform_mode) || 'or'}
						<button
							type="button"
							class="ct-filter-mode"
							title={t.filterMode}
							onclick={() => apply({ [param]: nextMode(mode) }, false)}>{mode.toUpperCase()}</button
						>
					{/if}
				</div>

				{#if threeWay[pane]}
					{@const choice = threeWay[pane]!}
					{#each Object.entries(choice.labels) as [value, text] (value)}
						<button
							type="button"
							class="ct-filter-row"
							aria-pressed={choice.value === value}
							onclick={() => apply({ [choice.param]: value === 'all' ? null : value })}
						>
							<span>{value === 'all' ? t.any : text}</span>
							{#if choice.value === value}<Check class="size-4 text-accent" aria-hidden="true" />{/if}
						</button>
					{/each}
				{:else if lists[pane]}
					{@const list = lists[pane]!}
					{#if list.searchable}
						<input
							class="ct-filter-search"
							type="search"
							placeholder={t.filterOptions(paneTitle)}
							aria-label={t.filterOptions(paneTitle)}
							bind:value={search}
						/>
					{/if}
					<button
						type="button"
						class="ct-filter-row"
						aria-pressed={!list.value}
						onclick={() => apply({ [list.param]: null })}
					>
						<span>{t.any}</span>
						{#if !list.value}<Check class="size-4 text-accent" aria-hidden="true" />{/if}
					</button>
					{#each matching(list.options, search) as option (option.value)}
						<button
							type="button"
							class="ct-filter-row"
							aria-pressed={list.value === option.value}
							onclick={() => apply({ [list.param]: option.value })}
						>
							<span class="truncate">{option.label}</span>
							{#if list.value === option.value}<Check class="size-4 flex-none text-accent" aria-hidden="true" />{/if}
						</button>
					{/each}
				{:else if pane === 'tag' || pane === 'platform'}
					{@const param = pane === 'tag' ? 'tag' : 'platform'}
					{@const selected = pane === 'tag' ? filters.tags : filters.platforms}
					{@const choices = pane === 'tag' ? options.tags : options.platforms}
					<input
						class="ct-filter-search"
						type="search"
						placeholder={t.filterOptions(paneTitle)}
						aria-label={t.filterOptions(paneTitle)}
						bind:value={search}
					/>
					<button
						type="button"
						class="ct-filter-row"
						aria-pressed={selected.length === 0}
						onclick={() => apply({ [param]: null }, false)}
					>
						<span>{pane === 'tag' ? t.clearTags : t.any}</span>
						{#if selected.length === 0}<Check class="size-4 text-accent" aria-hidden="true" />{/if}
					</button>
					{#each matching(choices, search) as option (option.value)}
						<button
							type="button"
							class="ct-filter-row"
							aria-pressed={selected.includes(option.value)}
							onclick={() => apply({ [param]: toggled(selected, option.value) }, false)}
						>
							<span class="truncate">{option.label}</span>
							{#if 'count' in option}<span class="ct-filter-count">{option.count}</span>{/if}
							{#if selected.includes(option.value)}<Check class="size-4 flex-none text-accent" aria-hidden="true" />{/if}
						</button>
					{/each}
				{:else if pane === 'date'}
					<div class="ct-filter-section">{t.releaseDate}</div>
					<button
						type="button"
						class="ct-filter-row"
						aria-pressed={!filters.year}
						onclick={() => apply({ year: null })}
					>
						<span>{t.any}</span>
						{#if !filters.year}<Check class="size-4 text-accent" aria-hidden="true" />{/if}
					</button>
					{#each options.years as option (option.value)}
						<button
							type="button"
							class="ct-filter-row"
							aria-pressed={filters.year === option.value}
							onclick={() => apply({ year: option.value })}
						>
							<span>{option.label}</span>
							{#if filters.year === option.value}<Check class="size-4 text-accent" aria-hidden="true" />{/if}
						</button>
					{/each}
					<div class="ct-filter-divider"></div>
					<div class="ct-filter-section">{t.completedDate}</div>
					<button
						type="button"
						class="ct-filter-row"
						aria-pressed={!completedLabel(filters, options)}
						onclick={() => apply(completedOff)}
					>
						<span>{t.any}</span>
						{#if !completedLabel(filters, options)}<Check class="size-4 text-accent" aria-hidden="true" />{/if}
					</button>
					{#each options.years.filter((option) => option.value !== 'unknown') as option (option.value)}
						<button
							type="button"
							class="ct-filter-row"
							aria-pressed={completedYear === option.value}
							onclick={() =>
								apply({
									...completedOff,
									completed_date_from: `${option.value}-01-01`,
									completed_date_to: `${option.value}-12-31`
								})}
						>
							<span>{option.label}</span>
							{#if completedYear === option.value}<Check class="size-4 text-accent" aria-hidden="true" />{/if}
						</button>
					{/each}
					<form
						class="ct-filter-form"
						onsubmit={(event) => {
							event.preventDefault();
							apply({ ...completedOff, completed_date_from: rangeFrom || null, completed_date_to: rangeTo || null });
						}}
					>
						<label>
							<span>{t.from}</span>
							<input type="date" bind:value={rangeFrom} />
						</label>
						<label>
							<span>{t.to}</span>
							<input type="date" bind:value={rangeTo} />
						</label>
						<button type="submit" class="ct-filter-apply">{t.apply}</button>
					</form>
					<form
						class="ct-filter-form"
						onsubmit={(event) => {
							event.preventDefault();
							apply({
								...completedOff,
								completed_date_within: within ? String(within) : null,
								completed_date_within_unit: within ? withinUnit : null
							});
						}}
					>
						<label>
							<span>{t.withinLast}</span>
							<input type="number" min="1" inputmode="numeric" bind:value={within} />
						</label>
						<label>
							<span class="sr-only">{t.unit}</span>
							<select bind:value={withinUnit}>
								{#each options.relative_date_units as unit (unit.value)}
									<option value={unit.value}>{unit.label}</option>
								{/each}
							</select>
						</label>
						<button type="submit" class="ct-filter-apply">{t.apply}</button>
					</form>
				{/if}
			{/if}
		</Popover.Content>
	</Popover.Portal>
</Popover.Root>
