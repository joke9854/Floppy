<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import { detailLink, genreLink } from '#lib/details/link.ts';
	import MediaHero from '#lib/details/MediaHero.svelte';
	import { playTime, toLocalInput, type AlbumTrack } from '#lib/details/media.ts';
	import { dt } from '#lib/details/strings.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const screen = $derived(data.screen);

	// The Plays dialog loads on the first tap (it is not part of the page's first load).
	let playsOpen = $state(false);
	let selected = $state<number | null>(null);
	const track = $derived(screen.tracks.find((row) => row.track_id === selected) ?? null);
	const suggestion = $derived(
		screen.release_date
			? { label: dt.releaseDate, local: toLocalInput(new Date(`${screen.release_date}T00:00:00`)) }
			: null
	);

	function openPlays(row: AlbumTrack) {
		selected = row.track_id;
		playsOpen = true;
	}

	function sub(row: AlbumTrack): string {
		return [
			row.duration,
			row.play_count ? dt.playsCount(row.play_count) : '',
			row.last_played ? dt.lastPlayed(playTime(row.last_played)) : ''
		]
			.filter(Boolean)
			.join(' · ');
	}
</script>

<svelte:head>
	<title>{screen.album.title} · Floppy</title>
</svelte:head>

<main class="ct-detail">
	<div class="mx-auto max-w-[1400px] px-5 md:px-8">
		<MediaHero
			title={screen.album.title}
			image={screen.album.image}
			kind={screen.details.find((row) => row.label === 'Format')?.value ?? 'Album'}
			backType="music"
			meta={screen.release ? [dt.selectedRelease(screen.release.title)] : []}
			activity={screen.activity}
			status={screen.tracker?.status}
			track={{ mediaType: 'album', source: 'music', mediaId: String(screen.album.id) }}
			historyUrl={screen.history_url}
			syncUrl={screen.sync_url}
			links={screen.links}
		>
			{#if screen.album.artists.length}
				<p class="ct-media-activity ct-media-artists">
					{#each screen.album.artists as artist, index (artist.id)}
						{#if index}, {/if}<a {...detailLink(artist.url)}>{artist.name}</a>
					{/each}
				</p>
			{/if}
		</MediaHero>

		<div class="ct-detail-sections">
			<section aria-labelledby="ct-tracks-title">
				<div class="ct-row-head"><h2 class="ct-row-title" id="ct-tracks-title">{dt.tracks}</h2></div>
				{#if screen.tracks.length}
					<ol class="ct-media-rows ct-episode-list">
						{#each screen.tracks as row (row.track_id ?? row.title)}
							<li>
								<button
									type="button"
									class="ct-media-row"
									aria-label={dt.openPlays(row.title)}
									onclick={() => openPlays(row)}
								>
									<span class="ct-media-row__number">{dt.trackNumber(row.disc, row.number)}</span>
									<span class="ct-media-row__body">
										<span class="ct-media-row__title">{row.title}</span>
										{#if sub(row)}
											<span class={['ct-media-row__sub', row.play_count && 'is-played']}>{sub(row)}</span>
										{/if}
									</span>
								</button>
							</li>
						{/each}
					</ol>
				{:else}
					<p class="ct-detail-note">{dt.noTracks}</p>
				{/if}
			</section>

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
		</div>
	</div>
</main>

{#if track}
	{#await import('#lib/details/PlaysDialog.svelte') then view}
		<view.default
			bind:open={playsOpen}
			title={track.title}
			kind="music"
			plays={track.plays}
			{suggestion}
			body={{
				album_id: screen.album.id,
				track_id: track.track_id,
				recording_id: track.recording_id
			}}
			onchange={() => invalidateAll()}
		/>
	{/await}
{/if}
