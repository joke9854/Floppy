<script lang="ts">
	import { onMount } from 'svelte';
	import { t } from '#lib/strings.ts';
	import { playbackClock, playbackLeft, playbackPosition, type NowPlaying } from './playback.ts';

	/**
	 * Now Playing in the Home header (Penpot P3a), as the Django pill: a 16:9
	 * still, a live dot with the state, the title, the episode, time left and
	 * position/runtime, and a progress line. It asks Django again every 10 s
	 * while the page is visible and ticks the clock each second in between.
	 * When playback stops or moves to another title, that title's progress is
	 * saved, so `onchange` lets Home reload In Progress.
	 */
	let { initial, onchange }: { initial: NowPlaying; onchange?: () => void } = $props();

	// svelte-ignore state_referenced_locally
	let playing = $state<NowPlaying>(initial);
	let now = $state(Date.now());

	const active = $derived(playing.active && !!playing.title);
	const { position, duration } = $derived(playbackPosition(playing, now));
	const left = $derived(playbackLeft(position, duration));
	const percent = $derived(duration > 0 ? Math.min(100, (position / duration) * 100) : 0);
	const isPlaying = $derived(playing.status === 'playing');

	async function refresh() {
		try {
			const response = await fetch('/api/v1/playback/now-playing/', { credentials: 'same-origin' });
			if (!response.ok) return;
			const next = (await response.json()) as NowPlaying;
			const before = playing.active ? (playing.url ?? '') : '';
			const after = next.active ? (next.url ?? '') : '';
			playing = next;
			if (before && before !== after) onchange?.();
		} catch {
			// Offline or Django restarting: keep what is shown and try again later.
		}
	}

	onMount(() => {
		const tick = setInterval(() => (now = Date.now()), 1000);
		const poll = setInterval(() => {
			if (document.visibilityState === 'visible') refresh();
		}, 10_000);
		const visible = () => {
			if (document.visibilityState === 'visible') refresh();
		};
		document.addEventListener('visibilitychange', visible);
		return () => {
			clearInterval(tick);
			clearInterval(poll);
			document.removeEventListener('visibilitychange', visible);
		};
	});
</script>

{#if active}
	<div class="ct-now-playing-slot">
		<a
			href={playing.url ?? undefined}
			class={['ct-now-playing', !isPlaying && 'is-paused']}
			aria-label="{t.nowPlaying}: {playing.title}{playing.episode_code ? ` ${playing.episode_code}` : ''}"
		>
			<span class="ct-now-playing__still">
				{#if playing.display_image}
					<img alt="" src={playing.display_image} width="100" height="56" decoding="async" />
				{/if}
			</span>
			<span class="ct-now-playing__text">
				<span class="ct-now-playing__state">
					<span class="ct-now-playing__dot" aria-hidden="true"></span>
					{isPlaying ? t.nowPlaying : t.paused}
				</span>
				<span class="ct-now-playing__title">{playing.title}</span>
				<span class="ct-now-playing__episode">
					{#if playing.episode_code}
						{playing.episode_code}{#if playing.episode_title}&nbsp;· {playing.episode_title}{/if}
					{:else}
						{playing.subtitle ?? ''}
					{/if}
				</span>
			</span>
			<span class="ct-now-playing__time">
				{#if left}<span class="ct-now-playing__left">{t.timeLeft(left)}</span>{/if}
				<span class="ct-now-playing__clock">
					{duration > 0
						? `${playbackClock(position)} / ${playbackClock(duration)}`
						: playbackClock(position)}
				</span>
			</span>
			<span class="ct-now-playing__line" aria-hidden="true"><span style:width="{percent}%"></span></span>
		</a>
	</div>
{/if}
