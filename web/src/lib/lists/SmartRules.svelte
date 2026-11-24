<script lang="ts">
	import './list-extras.css';
	import FilterMenu from '#lib/library/LazyFilterMenu.svelte';
	import { djangoWrite } from '#lib/csrf.ts';
	import type { ParamChanges } from '#lib/library/filters.ts';
	import {
		applyRuleChanges,
		rulesFilters,
		saveQueue,
		selectedTypes,
		toggleAllTypes,
		typesForSubmit,
		type ListPageSmart,
		type SmartRules
	} from './smart.ts';
	import { ld } from './strings.ts';
	import { toggleValue } from './types.ts';

	/**
	 * A smart list's rule builder (smart_rules_builder.html in edit mode):
	 * search, types, statuses, the Library's filter menu, and the ranges and
	 * linked lists. Every change saves the whole rule set (a key left out
	 * would be cleared) one save at a time, then `onsaved` reloads the items.
	 */
	let {
		smart,
		sort,
		direction,
		onsaved
	}: { smart: ListPageSmart; sort: string; direction: string; onsaved: () => void } = $props();

	// The builder edits its own copy; the page's data follows the saves.
	// svelte-ignore state_referenced_locally
	let rules = $state<SmartRules>(structuredClone($state.snapshot(smart.rules)) as SmartRules);
	let saveState = $state<'idle' | 'saving' | 'saved' | 'error'>('idle');
	let timer: ReturnType<typeof setTimeout> | undefined;

	const available = $derived(smart.media_types.map((option) => option.value));
	// svelte-ignore state_referenced_locally
	let picked = $state(selectedTypes(smart.rules.media_types, smart.media_types.map((option) => option.value), smart.granular_media_types));
	const broad = $derived(available.filter((value) => !smart.granular_media_types.includes(value)));
	const allPicked = $derived(broad.length > 0 && broad.every((value) => picked.includes(value)));
	const typesLabel = $derived.by(() => {
		if (allPicked && !picked.some((value) => smart.granular_media_types.includes(value))) return ld.allTypes2;
		if (picked.length === 0) return ld.noTypes;
		if (picked.length === 1) return smart.media_types.find((option) => option.value === picked[0])?.label ?? picked[0];
		return ld.typesCount(picked.length);
	});

	const save = saveQueue(
		async () => {
			const response = await djangoWrite(smart.save_url, 'POST', $state.snapshot(rules));
			return response.ok;
		},
		(ok) => {
			saveState = ok ? 'saved' : 'error';
			if (ok) onsaved();
		}
	);

	function change(next: SmartRules, delay = 350) {
		rules = next;
		saveState = 'saving';
		clearTimeout(timer);
		timer = setTimeout(save, delay);
	}

	function setTypes(next: string[]) {
		picked = next;
		change({ ...rules, media_types: typesForSubmit(next, available, smart.granular_media_types) }, 0);
	}

	// A sort pick in edit mode is saved with the rules, as on the Django page.
	// svelte-ignore state_referenced_locally
	let lastSort = `${sort}|${direction}`;
	$effect(() => {
		const current = `${sort}|${direction}`;
		if (current === lastSort) return;
		lastSort = current;
		change({ ...rules, sort, sort_direction: direction }, 0);
	});

	const units = $derived(smart.filter_options.relative_date_units);
	const ranges = $derived(
		[
			rules.rating_min,
			rules.rating_max,
			rules.release_date_from,
			rules.release_date_to,
			rules.release_date_within,
			rules.date_added_from,
			rules.date_added_to,
			rules.date_added_within
		].filter(Boolean).length + rules.list.length
	);
	const clearedRanges = $derived({
		...rules,
		rating_min: '',
		rating_max: '',
		release_date_from: '',
		release_date_to: '',
		release_date_within: '',
		date_added_from: '',
		date_added_to: '',
		date_added_within: '',
		list: []
	});

	type DateRule = 'release_date' | 'date_added';
	const dateRules: { key: DateRule; label: string }[] = [
		{ key: 'release_date', label: ld.releaseDate },
		{ key: 'date_added', label: ld.dateAdded }
	];
</script>

<section class="ct-smart" aria-label={ld.smartRules}>
	<div class="ct-smart__head">
		<h2>{ld.smartRules}</h2>
		<span class={['ct-smart__state', saveState === 'saving' && 'is-saving', saveState === 'error' && 'is-error']} aria-live="polite">
			{ld.editActive}{#if saveState === 'saving'}{ld.saving}{:else if saveState === 'error'}{ld.saveFailed}{/if}
		</span>
	</div>
	<div class="ct-lists-toolbar">
		<label class="ct-lists-search">
			<input
				type="search"
				placeholder={ld.searchRules}
				aria-label={ld.searchRules}
				value={rules.search}
				oninput={(event) => change({ ...rules, search: event.currentTarget.value })}
			/>
		</label>
		<details class="ct-lists-menu">
			<summary class="ct-lists-button">{typesLabel}</summary>
			<div class="ct-lists-menu__panel is-left">
				<button type="button" aria-current={allPicked ? 'true' : undefined} onclick={() => setTypes(toggleAllTypes(picked, available, smart.granular_media_types))}>
					{ld.allTypes2}
				</button>
				{#each smart.media_types as option (option.value)}
					<button type="button" aria-current={picked.includes(option.value) ? 'true' : undefined} onclick={() => setTypes(toggleValue(picked, option.value, ''))}>
						{option.label}
					</button>
				{/each}
			</div>
		</details>
		<details class="ct-lists-menu">
			<summary class="ct-lists-button">{ld.status}{#if rules.status.length} ({rules.status.length}){/if}</summary>
			<div class="ct-lists-menu__panel is-left">
				<button type="button" aria-current={rules.status.length === 0 ? 'true' : undefined} onclick={() => change({ ...rules, status: [] }, 0)}>{ld.allTypes}</button>
				{#each smart.statuses as option (option.value)}
					<button
						type="button"
						aria-current={rules.status.includes(option.value) ? 'true' : undefined}
						onclick={() => change({ ...rules, status: toggleValue(rules.status, option.value, '') }, 0)}
					>
						{option.label}
					</button>
				{/each}
			</div>
		</details>
		<FilterMenu
			filters={rulesFilters(rules)}
			options={smart.filter_options}
			onapply={(changes: ParamChanges) => change(applyRuleChanges(rules, changes), 0)}
		/>
		<details class="ct-lists-menu">
			<summary class="ct-lists-button">{ld.ranges}{#if ranges} ({ranges}){/if}</summary>
			<div class="ct-lists-menu__panel is-left ct-smart__ranges">
				<fieldset>
					<legend>{ld.rating}</legend>
					<input type="number" min="0" max="10" step="0.1" placeholder={ld.min} aria-label="{ld.rating} {ld.min}" value={rules.rating_min} onchange={(event) => change({ ...rules, rating_min: event.currentTarget.value }, 0)} />
					<input type="number" min="0" max="10" step="0.1" placeholder={ld.max} aria-label="{ld.rating} {ld.max}" value={rules.rating_max} onchange={(event) => change({ ...rules, rating_max: event.currentTarget.value }, 0)} />
				</fieldset>
				{#each dateRules as rule (rule.key)}
					<fieldset>
						<legend>{rule.label}</legend>
						<input type="date" aria-label="{rule.label} {ld.from}" value={rules[`${rule.key}_from`]} onchange={(event) => change({ ...rules, [`${rule.key}_from`]: event.currentTarget.value }, 0)} />
						<input type="date" aria-label="{rule.label} {ld.to}" value={rules[`${rule.key}_to`]} onchange={(event) => change({ ...rules, [`${rule.key}_to`]: event.currentTarget.value }, 0)} />
						<span class="ct-smart__within">
							{ld.within}
							<input
								type="number"
								min="1"
								max="999"
								aria-label="{rule.label} {ld.within}"
								value={rules[`${rule.key}_within`]}
								onchange={(event) => change({ ...rules, [`${rule.key}_within`]: event.currentTarget.value }, 0)}
							/>
							<select
								aria-label="{rule.label} {ld.within}"
								value={rules[`${rule.key}_within_unit`]}
								onchange={(event) => change({ ...rules, [`${rule.key}_within_unit`]: event.currentTarget.value }, 0)}
							>
								{#each units as unit (unit.value)}<option value={unit.value}>{unit.label}</option>{/each}
							</select>
						</span>
					</fieldset>
				{/each}
				{#if smart.lists.length}
					<fieldset>
						<legend>{ld.linkedLists}</legend>
						<div class="ct-smart__lists">
							{#each smart.lists as option (option.value)}
								{@const id = Number(option.value)}
								<button
									type="button"
									aria-pressed={rules.list.includes(id)}
									onclick={() => change({ ...rules, list: rules.list.includes(id) ? rules.list.filter((entry) => entry !== id) : [...rules.list, id] }, 0)}
								>
									{option.label}
								</button>
							{/each}
						</div>
					</fieldset>
				{/if}
				{#if ranges}<button type="button" class="ct-lists-button" onclick={() => change(clearedRanges, 0)}>{ld.clear}</button>{/if}
			</div>
		</details>
	</div>
</section>
