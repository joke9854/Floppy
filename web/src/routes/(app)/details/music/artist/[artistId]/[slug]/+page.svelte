<script lang="ts">
	import { detailLink, genreLink } from '#lib/details/link.ts';
	import MediaHero from '#lib/details/MediaHero.svelte';
	import type { ArtistScreen } from '#lib/details/media.ts';
	import { fadeIn } from '#lib/media/fade.ts';
	import { dt } from '#lib/details/strings.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const screen = $derived(data.screen);

	let bioOpen = $state(false);
	const longBio = $derived(screen.artist.bio.length > 280);
	const kind = $derived(screen.details.find((row) => row.label === 'Type')?.value ?? 'Artist');
	const rating = $derived(
		screen.rating.rating === null ? '' : `MusicBrainz ${screen.rating.rating.toFixed(1)}`
	);
</script>

<svelte:head>
	<title>{screen.artist.name} · Floppy</title>
</svelte:head>

<main class="ct-detail">
	<div class="mx-auto max-w-[1400px] px-5 md:px-8">
		<MediaHero
			title={screen.artist.name}
			image={screen.artist.image}
			{kind}
			backType="music"
			meta={rating ? [rating] : []}
			activity={screen.activity}
			status={screen.tracker?.status}
			track={{ mediaType: 'artist', source: 'music', mediaId: String(screen.artist.id) }}
			historyUrl={screen.history_url}
			syncUrl={screen.sync_url}
			links={screen.links}
		>
			{#if screen.artist.bio}
				<p class={['ct-media-bio', longBio && !bioOpen && 'is-clamped']}>{screen.artist.bio}</p>
				{#if longBio}
					<button type="button" class="ct-detail-more" onclick={() => (bioOpen = !bioOpen)}>
						{bioOpen ? dt.showLess : dt.readMore}
					</button>
				{/if}
			{/if}
		</MediaHero>

		<div class="ct-detail-sections">
			{#if screen.details.length}
				<section aria-labelledby="ct-details-title">
					<div class="ct-row-head"><h2 class="ct-row-title" id="ct-details-title">{dt.details}</h2></div>
					<dl class="ct-info-grid">
						{#each screen.details as row (row.label)}
							<div><dt>{row.label}</dt><dd>{row.value}</dd></div>
						{/each}
					</dl>
				</section>
			{/if}

			{#if screen.genres.length}
				<section aria-labelledby="ct-genres-title">
					<div class="ct-row-head"><h2 class="ct-row-title" id="ct-genres-title">{dt.genres}</h2></div>
					<div class="ct-chip-list">
						{#each screen.genres as genre (genre.name)}
							{#if genre.url}
								<a class="ct-genre-chip" {...genreLink(genre.url)}>{genre.name}</a>
							{:else}
								<span class="ct-genre-chip">{genre.name}</span>
							{/if}
						{/each}
					</div>
				</section>
			{/if}

			{#each [{ key: 'members', title: dt.members, rows: screen.members }, { key: 'member_of', title: dt.alsoIn, rows: screen.member_of }] as group (group.key)}
				{#if group.rows.length}
					<section aria-label={group.title}>
						<div class="ct-row-head"><h2 class="ct-row-title">{group.title}</h2></div>
						<div class="ct-media-people">
							{#each group.rows as person (person.id)}
								<a class="ct-media-person" {...detailLink(person.url)}>
									<img src={person.image} alt="" width="40" height="40" loading="lazy" decoding="async" />
									<span class="min-w-0">
										<span class="block truncate">{person.name}</span>
										{#if person.role || person.is_current}
											<span class="ct-media-person__sub">
												{[person.role, person.is_current ? dt.currentMember : ''].filter(Boolean).join(' · ')}
											</span>
										{/if}
									</span>
								</a>
							{/each}
						</div>
					</section>
				{/if}
			{/each}

			{#each screen.discography as group (group.label)}
				<section aria-label={group.label}>
					<div class="ct-row-head">
						<h2 class="ct-row-title">{group.label}</h2>
						<span class="ct-media-card__sub">{dt.releasesCount(group.albums.length)}</span>
					</div>
					<div class="ct-media-grid">
						{#each group.albums as album (album.id)}
							{@render cover(album)}
						{/each}
					</div>
				</section>
			{/each}
		</div>
	</div>
</main>

{#snippet cover(album: ArtistScreen['discography'][number]['albums'][number])}
	<a class="ct-media-card" {...detailLink(album.url)}>
		<img
			alt=""
			class="ct-fade-img"
			src={album.image}
			width="300"
			height="300"
			loading="lazy"
			decoding="async"
			use:fadeIn
		/>
		<span class="ct-media-card__title">{album.title}</span>
		<span class="ct-media-card__sub">
			{[
				album.release_date?.slice(0, 4),
				album.play_count ? dt.playsCount(album.play_count) : '',
				album.score !== null ? `★ ${album.score}` : ''
			]
				.filter(Boolean)
				.join(' · ')}
		</span>
	</a>
{/snippet}
