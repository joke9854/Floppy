<script lang="ts">
	import './charts.css';
	import type { components } from '#lib/api/client.ts';
	import { djangoForm } from '#lib/csrf.ts';
	import { detailLink } from '#lib/details/link.ts';
	import { cs } from './chart-strings.ts';
	import type { StatisticsScreen } from './types.ts';

	type Talent = components['schemas']['StatisticsTalent'];
	type Bar = components['schemas']['StatisticsTalentBar'];

	/**
	 * H3: the talent section (the page's lazy talent_section.html): the
	 * Featured Repeat Player with their titles, Role Leaders (click a name to
	 * feature them), Studio Footprint and Taste Signals, each with its sort.
	 * The page loads it after the rest; so does this.
	 */
	let { screen, mediaType }: { screen: StatisticsScreen; mediaType: string } = $props();

	let talent = $state<Talent | null>(null);
	let failed = $state(false);
	// A picked person holds for the type it was picked in, as the page resets
	// to the top player when the type changes.
	let picked = $state<{ type: string; source: string; id: string } | null>(null);
	let busy = $state(false);

	function query(): string {
		const params = new URLSearchParams();
		if (screen.range.predefined) params.set('range_name', screen.range.name);
		params.set('start-date', screen.range.start || 'all');
		params.set('end-date', screen.range.end || 'all');
		params.set('compare', screen.compare.mode);
		if (mediaType !== 'all') params.set('media_type', mediaType);
		if (picked && picked.type === mediaType) {
			params.set('person_source', picked.source);
			params.set('person_id', picked.id);
		}
		return params.toString();
	}

	// Only the latest request may fill the section: a slow answer for an
	// earlier pick or type must not overwrite a newer one.
	let requests = 0;

	async function load() {
		const request = ++requests;
		busy = true;
		try {
			const response = await fetch(`${screen.urls.talent}?${query()}`, {
				credentials: 'same-origin',
				headers: { accept: 'application/json' }
			});
			if (!response.ok) throw new Error(String(response.status));
			const next: Talent = await response.json();
			if (request !== requests) return;
			talent = next;
			failed = false;
		} catch {
			if (request === requests) failed = true;
		}
		if (request === requests) busy = false;
	}

	$effect(() => {
		// The range, the type or a picked person changes what it shows.
		void screen.range.start;
		void screen.range.end;
		void screen.compare.mode;
		void mediaType;
		void picked;
		load();
	});

	async function sort(url: string, value: string) {
		try {
			const response = await djangoForm(url, {
				sort_by: value,
				range_name: screen.range.predefined ? screen.range.name : '',
				start_date: screen.range.start,
				end_date: screen.range.end,
				media_type: mediaType === 'all' ? '' : mediaType
			});
			if (!response.ok) throw new Error(String(response.status));
		} catch {
			failed = true;
			return;
		}
		await load();
	}

	const TALENT_SORTS = ['plays', 'time', 'titles'];
	const BAR_SORTS = ['plays', 'time'];
	const GENRE_SORTS = ['time', 'plays'];
</script>

{#snippet sorts(options: string[], current: string, url: string)}
	<div class="ct-stats-sorts" role="group">
		{#each options as option (option)}
			<button type="button" aria-pressed={current === option} disabled={busy} onclick={() => sort(url, option)}>
				{cs.sortLabels[option]}
			</button>
		{/each}
	</div>
{/snippet}

{#snippet bars(items: Bar[], fallbackColor: string)}
	<ol class="ct-stats-barlist">
		{#each items as item, index (index)}
			<li>
				<span class="ct-stats-ranked__rank">{index + 1}</span>
				<span class="ct-stats-barlist__name">{item.name}</span>
				<span class="ct-stats-barlist__track"><i style:width="{item.pct}%" style:background={item.color || fallbackColor}></i></span>
				<span class="ct-stats-barlist__metric">{item.metric}</span>
				<span class="ct-stats-barlist__pct">{item.pct}%</span>
			</li>
		{/each}
	</ol>
{/snippet}

{#if talent}
	<div class="ct-stats-grid2 is-talent">
		<section class="ct-stats-card">
			<h2 class="ct-stats-card__title">{cs.featured}</h2>
			<p class="ct-stats-card__sub is-spaced">{cs.featuredSub}</p>
			{#if talent.featured}
				{@const person = talent.featured}
				<div class="ct-stats-person">
					{#if person.image}<img src={person.image} alt="" loading="lazy" decoding="async" />{/if}
					<div>
						<p class="ct-stats-person__name">{person.name}</p>
						<p class="ct-stats-person__counts">
							{person.unique_titles} {cs.titles}
							{#if person.unique_movies} · {person.unique_movies} {cs.movies}{/if}
							{#if person.unique_shows} · {person.unique_shows} {cs.shows}{/if}
							{#if person.unique_games} · {person.unique_games} {cs.games}{/if}
						</p>
						<p class="ct-stats-person__pct">{cs.ofLibrary(person.pct_of_library)}</p>
						<p class="ct-stats-person__known">
							<span>{cs.knownFor}</span>
							{#each person.known_for as role, index (index)}<em>{role}</em>{:else}<span>{cs.noRoles}</span>{/each}
						</p>
						{#if person.href}<a {...detailLink(person.href)} class="ct-stats-link">{cs.viewProfile}</a>{/if}
					</div>
				</div>
			{:else}
				<p class="ct-stats-none">{cs.noRepeat}</p>
			{/if}
		</section>
		<section class="ct-stats-card">
			<div class="ct-stats-card__head">
				<div>
					<h2 class="ct-stats-card__title">{cs.roleLeaders}</h2>
					<p class="ct-stats-card__sub">{cs.roleLeadersSub}</p>
				</div>
				{@render sorts(TALENT_SORTS, talent.talent_sort, talent.urls.talent_sort)}
			</div>
			<div class="ct-stats-leaders">
				{#each talent.role_leaders as column (column.bucket)}
					<div>
						<h3>{column.label}</h3>
						<ol>
							{#each column.people as person, index (index)}
								<li>
									<button
										type="button"
										aria-current={talent.featured?.source === person.source && talent.featured?.person_id === person.person_id ? 'true' : undefined}
										onclick={() => (picked = { type: mediaType, source: person.source, id: person.person_id })}
									>
										<span class="ct-stats-ranked__rank">{index + 1}</span>
										<span class="ct-stats-leaders__name">{person.name}</span>
										<span class="ct-stats-leaders__metric">{person.metric}</span>
									</button>
								</li>
							{/each}
						</ol>
					</div>
				{/each}
			</div>
		</section>
	</div>

	{#if talent.strip.items.length}
		<section class="ct-stats-card">
			<h2 class="ct-stats-card__title">{talent.strip.title}</h2>
			<p class="ct-stats-card__sub is-spaced">{talent.strip.summary}</p>
			<div class="ct-stats-posters is-row">
				{#each talent.strip.items as entry, index (index)}
					<a {...detailLink(entry.href)} class="ct-stats-poster">
						{#if entry.image}
						<img src={entry.image} alt={entry.title} loading="lazy" decoding="async" />
					{:else}
						<span class="ct-stats-poster__blank" aria-hidden="true"></span>
					{/if}
						<span class="ct-stats-poster__title">{entry.title}</span>
						<span class="ct-stats-poster__sub">{entry.caption}</span>
					</a>
				{/each}
			</div>
		</section>
	{/if}

	<div class="ct-stats-grid2">
		<section class="ct-stats-card">
			<div class="ct-stats-card__head">
				<div>
					<h2 class="ct-stats-card__title">{cs.studioFootprint}</h2>
					<p class="ct-stats-card__sub">{cs.studioFootprintSub}</p>
				</div>
				{@render sorts(BAR_SORTS, talent.studio_sort, talent.urls.studio_sort)}
			</div>
			<h3 class="ct-stats-subhead">{cs.topStudios}</h3>
			{#if talent.studios.length}{@render bars(talent.studios, '#6366f1')}{:else}<p class="ct-stats-none">{cs.noStudios}</p>{/if}
		</section>
		<section class="ct-stats-card">
			<div class="ct-stats-card__head">
				<div>
					<h2 class="ct-stats-card__title">{cs.tasteSignals}</h2>
					<p class="ct-stats-card__sub">{cs.tasteSignalsSub}</p>
				</div>
				{@render sorts(GENRE_SORTS, talent.genre_sort, talent.urls.genre_sort)}
			</div>
			<h3 class="ct-stats-subhead">{cs.topGenres}</h3>
			{#if talent.genres.length}{@render bars(talent.genres, '#6366f1')}{:else}<p class="ct-stats-none">{cs.noGenres}</p>{/if}
			<h3 class="ct-stats-subhead">{cs.eraSpotlight}</h3>
			{#if talent.eras.length}{@render bars(talent.eras, '#8b5cf6')}{:else}<p class="ct-stats-none">{cs.noEras}</p>{/if}
		</section>
	</div>
{:else if failed}
	<p class="ct-stats-none">{cs.talentFailed}</p>
{/if}
