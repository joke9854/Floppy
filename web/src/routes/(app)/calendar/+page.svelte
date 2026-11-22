<script lang="ts">
	import '#lib/styles/screen.css';
	import '#lib/calendar/calendar.css';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import Funnel from '@lucide/svelte/icons/list-filter';
	import Grid from '@lucide/svelte/icons/calendar-days';
	import ListIcon from '@lucide/svelte/icons/list';
	import Settings from '@lucide/svelte/icons/cog';
	import {
		allOn,
		exportUrl,
		filterLabel,
		loadFilter,
		partialStatus,
		shows,
		storageKey,
		type CalendarFilter,
		type CalendarRelease
	} from '#lib/calendar/filter.ts';
	import { ct } from '#lib/calendar/strings.ts';
	import { djangoForm } from '#lib/csrf.ts';
	import { BASE } from '#lib/paths.ts';
	import { detailHref, reloadFor } from '#lib/shell/nav.ts';
	import type { PageProps } from './$types';

	/**
	 * Calendar (P4-F), as the Django page (events/calendar.html): the month
	 * with its releases as a grid (on phones Agenda or Month) or a list, the
	 * type and status filter kept in the browser under the page's own key,
	 * Fetch New Releases, Download Calendar and the iCal export link.
	 */
	let { data }: PageProps = $props();
	const screen = $derived(data.screen);

	// Everything on (the page's default) until the browser's saved filter loads.
	let filter = $derived<CalendarFilter>(allOn(screen.filter_types));
	let statusMenu = $state<string | null>(null);
	let mode = $state<'agenda' | 'month'>('agenda');
	// A tapped day in the phone's Month picker; back to the default on another month.
	let picked = $derived.by((): number | null => {
		void screen.days;
		return null;
	});
	let notice = $state('');
	let exportTypes = $derived(screen.export.types.filter((type) => type.enabled).map((type) => type.value));
	let exportStatuses = $derived(screen.export.statuses.map((status) => status.value));

	$effect(() => {
		// The saved filter and phone mode live in this browser, as on the page.
		filter = loadFilter(localStorage.getItem(storageKey(screen.user_id)), screen.filter_types);
		mode = localStorage.getItem('ct-calendar-mode') === 'month' ? 'month' : 'agenda';
	});

	function setFilter(next: CalendarFilter) {
		filter = next;
		try {
			localStorage.setItem(storageKey(screen.user_id), JSON.stringify(next));
		} catch {
			// Private mode: the filter still applies on this visit.
		}
	}

	function toggleType(value: string) {
		const on = filter.selectedMediaTypes.includes(value);
		setFilter({
			...filter,
			selectedMediaTypes: on ? filter.selectedMediaTypes.filter((type) => type !== value) : [...filter.selectedMediaTypes, value]
		});
	}

	function toggleStatus(type: string, status: string) {
		const current = filter.selectedStatusesByType[type] ?? [];
		setFilter({
			...filter,
			selectedStatusesByType: {
				...filter.selectedStatusesByType,
				[type]: current.includes(status) ? current.filter((value) => value !== status) : [...current, status]
			}
		});
	}

	function setMode(next: 'agenda' | 'month') {
		mode = next;
		try {
			localStorage.setItem('ct-calendar-mode', next);
		} catch {
			// Kept for this visit only.
		}
	}

	const visible = (releases: CalendarRelease[]) => releases.filter((release) => shows(release, filter));
	const byDay = $derived(new Map(screen.days.map((day) => [day.day, visible(day.releases)])));
	const isThisMonth = $derived(screen.year === screen.today.year && screen.month === screen.today.month);
	const isToday = (day: number) => isThisMonth && day === screen.today.day;
	const isPast = (day: number) =>
		screen.year < screen.today.year ||
		(screen.year === screen.today.year &&
			(screen.month < screen.today.month || (screen.month === screen.today.month && day < screen.today.day)));
	const agendaDays = $derived(
		screen.days.filter((day) => !isThisMonth || day.day >= screen.today.day).map((day) => day.day)
	);
	const listDays = $derived(screen.days.filter((day) => (byDay.get(day.day) ?? []).length));
	const selectedDay = $derived(picked ?? screen.selected_day);
	const typeLabel = $derived(filterLabel(screen.filter_types, filter));
	const submenu = $derived(screen.filter_types.find((type) => type.value === statusMenu));

	const monthHref = (year: number, month: number, view = screen.view) =>
		`${BASE}/calendar?month=${month}&year=${year}&view=${view}`;
	const weekday = (day: number) =>
		new Date(screen.year, screen.month - 1, day).toLocaleDateString('en-US', { weekday: 'long' });
	const shortMonth = $derived(
		new Date(screen.today.year, screen.today.month - 1, 1).toLocaleDateString('en-US', { month: 'short' })
	);

	async function fetchReleases(event: Event) {
		(event.currentTarget as HTMLElement).closest('details')?.removeAttribute('open');
		try {
			const response = await djangoForm(screen.reload_url, {}, { json: true });
			const body = await response.json();
			notice = response.ok ? body.message : ct.fetchFailed;
		} catch {
			notice = ct.fetchFailed;
		}
		setTimeout(() => (notice = ''), 4000);
	}
</script>

<svelte:head>
	<title>{ct.title} · Floppy</title>
</svelte:head>

{#snippet row(release: CalendarRelease)}
	{@const href = detailHref(release.href)}
	<a class="ct-agenda-row" {href} data-sveltekit-reload={reloadFor(href) || undefined}>
		<img class="ct-agenda-poster" src={release.poster} alt="" width="40" height="60" loading="lazy" decoding="async" />
		<span class="ct-agenda-text">
			<span class="ct-agenda-title">{release.title}</span>
			<span class="ct-agenda-sub">
				{#if release.code}<span class="ct-agenda-code">{release.code}</span>{/if}
				<span>{release.type_label}</span>
			</span>
		</span>
		{#if release.time}<span class="ct-agenda-time">{release.time}</span>{/if}
	</a>
{/snippet}

{#snippet today()}
	<a class="ct-cal-today" href={monthHref(screen.today.year, screen.today.month)} title={ct.goToToday} aria-label={ct.goToToday}>
		<span class="ct-cal-today__day">{screen.today.day}</span>
		<span class="ct-cal-today__month">{shortMonth}</span>
	</a>
{/snippet}

<main class="ct-cal-page mx-auto px-5 pt-6 md:px-8 md:pt-8">
	<div class="ct-cal-head">
		<h1 class="ct-page-title">{ct.title}</h1>
		<p class="ct-page-sub">{ct.subtitle}</p>
	</div>

	<section class="ct-cal-bar">
		<div class="ct-cal-bar__month">
			<span class="ct-cal-wide">{@render today()}</span>
			<a class="ct-cal-icon" href={monthHref(screen.prev.year, screen.prev.month)} aria-label={ct.previousMonth}>
				<ChevronLeft class="size-5" aria-hidden="true" />
			</a>
			<h2 class="ct-cal-bar__title">{screen.month_name} {screen.year}</h2>
			<a class="ct-cal-icon" href={monthHref(screen.next.year, screen.next.month)} aria-label={ct.nextMonth}>
				<ChevronRight class="size-5" aria-hidden="true" />
			</a>
		</div>
		<div class="ct-cal-bar__tools">
			<details class="ct-cal-menu" ontoggle={() => (statusMenu = null)}>
				<summary class="ct-cal-pill"><Funnel class="size-4" aria-hidden="true" />{typeLabel}</summary>
				<div class="ct-cal-menu__panel">
					{#if submenu}
						<button type="button" class="ct-cal-menu__back" onclick={() => (statusMenu = null)}>
							<ChevronLeft class="size-4" aria-hidden="true" />{ct.backToTypes}
						</button>
						<div class="ct-cal-menu__head">
							<span>{ct.statusOf(submenu.label)}</span>
							<button
								type="button"
								onclick={() =>
									setFilter({
										...filter,
										selectedStatusesByType: {
											...filter.selectedStatusesByType,
											[submenu.value]: partialStatus(submenu, filter) ? submenu.statuses.map((status) => status.value) : []
										}
									})}>{partialStatus(submenu, filter) ? ct.showAll : ct.hideAll}</button
							>
						</div>
						{#each submenu.statuses as status (status.value)}
							<label class={['ct-cal-check', !submenu.month_statuses.includes(status.value) && 'is-dim']}>
								<input
									type="checkbox"
									checked={(filter.selectedStatusesByType[submenu.value] ?? []).includes(status.value)}
									onchange={() => toggleStatus(submenu.value, status.value)}
								/>
								{status.label}
							</label>
						{/each}
					{:else}
						<div class="ct-cal-menu__head">
							<span>{ct.mediaTypes}</span>
							<button
								type="button"
								onclick={() =>
									setFilter(
										filter.selectedMediaTypes.length === screen.filter_types.length
											? { ...filter, selectedMediaTypes: [] }
											: { ...filter, selectedMediaTypes: allOn(screen.filter_types).selectedMediaTypes }
									)}
								>{filter.selectedMediaTypes.length === screen.filter_types.length ? ct.hideAll : ct.showAll}</button
							>
						</div>
						{#each screen.filter_types as type (type.value)}
							<div class={['ct-cal-check', !type.in_month && 'is-dim']}>
								<label>
									<input type="checkbox" checked={filter.selectedMediaTypes.includes(type.value)} onchange={() => toggleType(type.value)} />
									{type.label}{partialStatus(type, filter) ? ' ·' : ''}
								</label>
								{#if type.statuses.length}
									<button type="button" class="ct-cal-icon is-small" aria-label={ct.statusOf(type.label)} onclick={() => (statusMenu = type.value)}>
										<ChevronRight class="size-4" aria-hidden="true" />
									</button>
								{/if}
							</div>
						{/each}
					{/if}
				</div>
			</details>
			<details class="ct-cal-menu">
				<summary class="ct-cal-icon" aria-label={ct.calendarActions} title={ct.calendarActions}>
					<Settings class="size-5" aria-hidden="true" />
				</summary>
				<div class="ct-cal-menu__panel is-end">
					<button type="button" class="ct-cal-menu__item" onclick={fetchReleases}>{ct.fetchNewReleases}</button>
					<a class="ct-cal-menu__item" href={screen.export.url} data-sveltekit-reload>{ct.downloadCalendar}</a>
				</div>
			</details>
			<nav class="ct-cal-views" aria-label={ct.title}>
				<a href={monthHref(screen.year, screen.month, 'grid')} aria-current={screen.view === 'grid' ? 'page' : undefined} aria-label={ct.gridView} title={ct.gridView}>
					<Grid class="size-5" aria-hidden="true" />
				</a>
				<a href={monthHref(screen.year, screen.month, 'list')} aria-current={screen.view === 'list' ? 'page' : undefined} aria-label={ct.listView} title={ct.listView}>
					<ListIcon class="size-5" aria-hidden="true" />
				</a>
			</nav>
			<span class="ct-cal-narrow">{@render today()}</span>
		</div>
	</section>

	{#if screen.view === 'grid'}
		<div class="ct-cal-phone">
			<div class="ct-cal-mode" role="group" aria-label={ct.title}>
				<button type="button" aria-pressed={mode === 'agenda'} onclick={() => setMode('agenda')}>{ct.agenda}</button>
				<button type="button" aria-pressed={mode === 'month'} onclick={() => setMode('month')}>{ct.month}</button>
			</div>
			{#if mode === 'agenda'}
				{@const shown = agendaDays.filter((day) => (byDay.get(day) ?? []).length)}
				{#each shown as day (day)}
					<section class="ct-agenda-day">
						<h3 class="ct-agenda-head">
							<span class="ct-agenda-weekday">{weekday(day)}</span>
							<span class="ct-agenda-date">{screen.month_name} {day}</span>
							{#if isToday(day)}<span class="ct-agenda-today">{ct.today}</span>{/if}
						</h3>
						<div class="ct-agenda-rows">
							{#each byDay.get(day) ?? [] as release (release.id)}{@render row(release)}{/each}
						</div>
					</section>
				{:else}
					<p class="ct-agenda-empty">{ct.noUpcoming}</p>
				{/each}
			{:else}
				<div class="ct-cal-mini">
					{#each screen.weekdays as name (name)}<span class="ct-cal-mini__head">{name}</span>{/each}
					{#each screen.weeks.flat() as day, i (i)}
						{#if day}
							{@const count = (byDay.get(day) ?? []).length}
							<button
								type="button"
								class={['ct-cal-mini__day', isToday(day) && 'is-today', day === selectedDay && 'is-picked']}
								aria-pressed={day === selectedDay}
								aria-label="{screen.month_name} {day}, {ct.releases(count)}"
								onclick={() => (picked = day)}
							>
								{day}
								<span class="ct-cal-mini__dots" aria-hidden="true">
									{#each Array.from({ length: Math.min(count, 3) }) as _, d (d)}<span></span>{/each}
								</span>
							</button>
						{:else}
							<span></span>
						{/if}
					{/each}
				</div>
				{@const picks = byDay.get(selectedDay) ?? []}
				<section class="ct-agenda-day">
					<h3 class="ct-agenda-head">
						<span class="ct-agenda-weekday">{screen.month_name} {selectedDay}</span>
						<span class="ct-agenda-date">{ct.releases(picks.length)}</span>
					</h3>
					<div class="ct-agenda-rows">
						{#each picks as release (release.id)}{@render row(release)}{:else}<p class="ct-agenda-empty">{ct.noReleasesDay}</p>{/each}
					</div>
				</section>
			{/if}
		</div>

		<div class="ct-cal-grid" role="grid" aria-label="{screen.month_name} {screen.year}">
			{#each screen.weekdays as name (name)}<div class="ct-cal-grid__head" role="columnheader">{name}</div>{/each}
			{#each screen.weeks.flat() as day, i (i)}
				<div class={['ct-cal-cell', !day && 'is-pad', day && isPast(day) && 'is-past', day && isToday(day) && 'is-today']} role="gridcell">
					{#if day}
						<span class="ct-cal-cell__day">{day}</span>
						{#each byDay.get(day) ?? [] as release (release.id)}
							{@const href = detailHref(release.href)}
							<a class="ct-cal-cell__release" {href} data-sveltekit-reload={reloadFor(href) || undefined} title="{release.label} {release.time}">
								<span class="ct-cal-cell__dot" aria-hidden="true"></span>
								<span class="ct-cal-cell__text">{release.label} {release.time}</span>
							</a>
						{/each}
					{/if}
				</div>
			{/each}
		</div>
	{:else}
		<div class="ct-cal-list">
			{#each listDays as day (day.day)}
				<section class="ct-agenda-day">
					<h3 class={['ct-agenda-head', isToday(day.day) && 'is-today']}>
						<span class="ct-agenda-weekday">{weekday(day.day)}, {screen.month_name} {day.day}</span>
						{#if isToday(day.day)}<span class="ct-agenda-today">{ct.today}</span>{/if}
					</h3>
					<div class="ct-agenda-rows">
						{#each byDay.get(day.day) ?? [] as release (release.id)}{@render row(release)}{/each}
					</div>
				</section>
			{:else}
				<p class="ct-agenda-empty">{ct.noReleasesFiltered}</p>
			{/each}
		</div>
	{/if}

	<section class="ct-cal-export">
		<h3 class="ct-cal-export__title">{ct.exportLink}</h3>
		<p class="ct-cal-export__help">{ct.exportHelp}</p>
		<h4 class="ct-cal-export__sub">{ct.mediaTypes}</h4>
		<p class="ct-cal-export__help">{ct.exportTypesHelp}</p>
		<div class="ct-cal-export__toggles">
			{#each screen.export.types as type (type.value)}
				<label class="ct-cal-toggle">
					<span>{type.label}</span>
					<input
						type="checkbox"
						role="switch"
						checked={exportTypes.includes(type.value)}
						onchange={(e) =>
							(exportTypes = e.currentTarget.checked ? [...exportTypes, type.value] : exportTypes.filter((value) => value !== type.value))}
					/>
				</label>
			{/each}
		</div>
		<h4 class="ct-cal-export__sub">{ct.status}</h4>
		<p class="ct-cal-export__help">{ct.exportStatusHelp}</p>
		<div class="ct-cal-export__toggles">
			{#each screen.export.statuses as status (status.value)}
				<label class="ct-cal-toggle">
					<span>{status.label}</span>
					<input
						type="checkbox"
						role="switch"
						checked={exportStatuses.includes(status.value)}
						onchange={(e) =>
							(exportStatuses = e.currentTarget.checked
								? [...exportStatuses, status.value]
								: exportStatuses.filter((value) => value !== status.value))}
					/>
				</label>
			{/each}
		</div>
		<input
			class="ct-cal-export__url"
			readonly
			aria-label={ct.calendarUrl}
			value={exportUrl(screen.export.url, exportTypes, exportStatuses)}
			onfocus={(e) => e.currentTarget.select()}
		/>
	</section>
</main>
{#if notice}<p class="ct-cal-notice" role="status">{notice}</p>{/if}
