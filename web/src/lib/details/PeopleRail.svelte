<script lang="ts">
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import type { components } from '#lib/api/client.ts';
	import { fadeIn } from '#lib/media/fade.ts';
	import { t } from '#lib/strings.ts';
	import { detailLink } from './link.ts';

	type Person = components['schemas']['DetailPerson'];

	/**
	 * Characters / Cast / Crew (ct/detail_secondary.html): three title tabs
	 * over one rail. Characters lead with the role and show TVDB's picture of
	 * the character where there is one; Cast leads with the actor; Crew with
	 * the person and their job.
	 */
	let {
		cast,
		crew,
		viewAllUrl = null
	}: { cast: Person[]; crew: Person[]; viewAllUrl?: string | null } = $props();

	type Tab = 'characters' | 'cast' | 'crew';
	let chosen = $state<Tab | null>(null);
	const tab = $derived<Tab>(chosen ?? (cast.length ? 'characters' : 'crew'));
	const people = $derived(tab === 'crew' ? crew : cast);
	const tabs = $derived.by(() => {
		const list: { key: Tab; label: string }[] = [];
		if (cast.length) {
			list.push({ key: 'characters', label: t.characters }, { key: 'cast', label: t.cast });
		}
		if (crew.length) list.push({ key: 'crew', label: t.crew });
		return list;
	});
</script>

<section aria-label={t.cast}>
	<div class="ct-row-head ct-title-toggle" role="tablist">
		{#each tabs as item (item.key)}
			<button
				type="button"
				role="tab"
				class={['ct-row-title', item.key !== tab && 'is-off']}
				aria-selected={item.key === tab}
				onclick={() => (chosen = item.key)}>{item.label}</button
			>
		{/each}
		{#if viewAllUrl}
			<a class="ct-row-link" href={viewAllUrl} target="_blank" rel="noopener noreferrer"
				>{t.seeAll} <ChevronRight class="size-4" aria-hidden="true" /></a
			>
		{/if}
	</div>
	<div class="ct-detail-rail" role="tabpanel">
		{#each people as person, index (`${tab}-${index}`)}
			{@const picture = tab === 'characters' ? person.character_image || person.image : person.image}
			{@const primary = tab === 'characters' ? person.role || person.name : person.name}
			{@const secondary = tab === 'characters' ? (person.role ? person.name : '') : person.role}
			<article class="ct-person-card">
				<svelte:element
					this={person.url ? 'a' : 'div'}
					class="ct-person-link"
					{...person.url ? detailLink(person.url) : {}}
				>
					<span class="ct-person-frame">
						{#if picture}
							<img
								alt={primary}
								class="ct-fade-img"
								src={picture}
								width="185"
								height="278"
								loading="lazy"
								decoding="async"
								use:fadeIn
							/>
						{/if}
					</span>
					<span class="ct-person-primary">{primary}</span>
					{#if secondary}<span class="ct-person-secondary">{secondary}</span>{/if}
				</svelte:element>
			</article>
		{/each}
	</div>
</section>
