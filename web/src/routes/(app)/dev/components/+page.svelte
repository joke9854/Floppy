<script lang="ts">
	import Button from '#lib/ui/Button.svelte';
	import Card from '#lib/ui/Card.svelte';
	import Dialog from '#lib/ui/Dialog.svelte';
	import Skeleton from '#lib/ui/Skeleton.svelte';
	import TextField from '#lib/ui/TextField.svelte';

	import '#lib/details/details.css';
	import Sections from '#lib/details/Sections.svelte';
	import type { DetailIssue, DetailSections } from '#lib/details/api.ts';

	// Detail sections (P4-L1): fixtures for a game, a comic and a book, so the
	// blocks can be seen without provider data.
	const empty: DetailSections = {
		backdrop: null,
		watch_on: null,
		sections: [],
		seasons: [],
		season: null,
		plays: [],
		history_url: '/history',
		related: [],
		cast: [],
		crew: [],
		cast_view_all_url: null,
		recommendations: [],
		info: [],
		issues: [],
		issues_more: null,
		game_lengths: null,
		authors: [],
		studios: [],
		genres: [],
		fanart_poster: null,
		logo: null
	};
	const noSeason = { season: null, selected: null, loading: false, failed: false };
	const issue = (number: number, read: boolean): DetailIssue => ({
		number: String(number),
		title: `The Long Road, part ${number}`,
		image: null,
		cover_date: `2021-0${number}-14`,
		read,
		url: `/details/comicvine/comicissue/4000-${number}/part-${number}`,
		media_type: 'comicissue',
		source: 'comicvine',
		media_id: `4000-${number}`
	});
	const game: DetailSections = {
		...empty,
		sections: ['game_lengths'],
		game_lengths: {
			available: true,
			pending: false,
			source_label: 'How Long to Beat',
			source_url: 'https://howlongtobeat.com/game/1',
			cards: [
				{ label: 'Main Story', value: '12h 30m', count: 1840 },
				{ label: 'Main + Extras', value: '21h', count: 1204 },
				{ label: 'Completionist', value: '48h', count: 532 }
			]
		}
	};
	const comic: DetailSections = {
		...empty,
		sections: ['episodes'],
		issues: [issue(1, true), issue(2, false), issue(3, false)],
		issues_more: { page: 2, label: 'Issues 4 to 6' }
	};
	const book: DetailSections = {
		...empty,
		sections: ['details', 'genres', 'studios'],
		info: [
			{ label: 'Format', value: 'Hardcover' },
			{ label: 'Number Of Pages', value: '412' },
			{ label: 'Publish Date', value: 'March 3, 2015' }
		],
		authors: [
			{ name: 'N. K. Jemisin', url: '/person/hardcover/12/n-k-jemisin' },
			{ name: 'A. Co-Author', url: '/person/hardcover/13/a-co-author' }
		],
		genres: [
			{ name: 'Fantasy', url: '/medialist/book?genre=Fantasy' },
			{ name: 'Adventure', url: '/medialist/book?genre=Adventure' }
		],
		studios: [{ name: 'Orbit Books', url: '/details/hardcover/company/5/orbit-books' }]
	};

	let dialog = $state(false);
	let sheet = $state(false);
	let text = $state('');
</script>

<main class="mx-auto flex max-w-3xl flex-col gap-8 px-5 pt-8 md:px-8">
	<h1 class="text-3xl font-bold tracking-tight">Components</h1>

	<section class="flex flex-wrap items-center gap-3">
		<Button variant="primary">Primary</Button>
		<Button>Secondary</Button>
		<Button variant="ghost">Ghost</Button>
		<Button size="sm">Small</Button>
		<Button disabled>Disabled</Button>
	</section>

	<Card class="flex flex-col gap-4">
		<h2 class="text-lg font-bold">Card</h2>
		<TextField label="Text field" placeholder="Type here" bind:value={text} />
		<TextField label="With an error" value="wrong" error="That is not right." />
	</Card>

	<section class="flex flex-col gap-3">
		<h2 class="text-lg font-bold">Loading</h2>
		<Skeleton class="h-5 w-2/3" />
		<Skeleton class="h-5 w-1/2" />
	</section>

	<section class="flex gap-3">
		<Button onclick={() => (dialog = true)}>Open dialog</Button>
		<Button onclick={() => (sheet = true)}>Open sheet</Button>
	</section>

	<section class="flex flex-col gap-3">
		<h2 class="text-lg font-bold">Detail sections (P4-L1)</h2>
		{#each [['game', 'Game', game], ['comic', 'Comic', comic], ['book', 'Book', book]] as const as [type, label, data] (type)}
			<h3 class="text-sm font-semibold text-muted">{label}</h3>
			<Sections
				sections={data}
				mediaType={type}
				source="fixture"
				mediaId="1"
				current={noSeason}
				trailers={[]}
				trackTime={false}
				onpick={() => {}}
				onmore={() => {}}
				onsaved={() => {}}
				oninfo={() => {}}
				onplay={() => {}}
			/>
		{/each}
	</section>

	<div class="flex flex-wrap gap-2">
		{#each [['Watching', 'bg-ct-watching'], ['Planned', 'bg-ct-planned'], ['Paused', 'bg-ct-paused'], ['Completed', 'bg-ct-completed'], ['Dropped', 'bg-ct-dropped'], ['Accent', 'bg-accent']] as [label, color] (label)}
			<span class="rounded-full px-3 py-1 text-xs font-bold text-white {color}">{label}</span>
		{/each}
	</div>
</main>

<Dialog bind:open={dialog} title="A dialog" description="Escape or the backdrop closes it.">
	<div class="flex justify-end gap-3">
		<Button variant="ghost" onclick={() => (dialog = false)}>Cancel</Button>
		<Button variant="primary" onclick={() => (dialog = false)}>Done</Button>
	</div>
</Dialog>

<Dialog bind:open={sheet} title="A sheet" description="A bottom sheet on phones, a dialog from md." sheet>
	<Button variant="primary" onclick={() => (sheet = false)}>Close</Button>
</Dialog>
