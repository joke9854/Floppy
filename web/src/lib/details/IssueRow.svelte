<script lang="ts">
	import Check from '@lucide/svelte/icons/check';
	import Plus from '@lucide/svelte/icons/plus';
	import { fadeIn } from '#lib/media/fade.ts';
	import { openTrack } from '#lib/track/open.svelte.ts';
	import { dt } from '#lib/details/strings.ts';
	import type { DetailIssue } from './api.ts';
	import { detailLink } from './link.ts';

	/**
	 * One issue of a comic volume (issue_row.html): cover, number, title and
	 * cover date, a Read mark, and a Track button (the Track dialog saves it
	 * and the page reloads its data). The row opens the issue's Django page.
	 */
	let { issue }: { issue: DetailIssue } = $props();

	const heading = $derived(issue.title || dt.unknownIssue);
</script>

<article class="ct-ep-row ct-issue-row">
	<div class="ct-issue-cover">
		{#if issue.image}
			<img
				alt=""
				class="ct-fade-img"
				src={issue.image}
				width="342"
				height="513"
				loading="lazy"
				decoding="async"
				use:fadeIn
			/>
		{/if}
	</div>
	<div class="ct-ep-body">
		<div class="ct-ep-heading">
			{#if issue.url}
				<a {...detailLink(issue.url)} class="ct-ep-title">{heading}</a>
			{:else}
				<span class="ct-ep-title">{heading}</span>
			{/if}
		</div>
		<span class="ct-ep-sub ct-issue-sub">
			{dt.issueNumber(issue.number)}{issue.cover_date ? ` · ${issue.cover_date}` : ''}
		</span>
		{#if issue.read}
			<span class="ct-ep-sub is-watched ct-issue-read">
				<Check class="size-3.5" aria-hidden="true" />{dt.issueRead}
			</span>
		{/if}
	</div>
	<button
		type="button"
		class="ct-ep-info"
		title={dt.trackIssue(heading)}
		aria-label={dt.trackIssue(heading)}
		onclick={() =>
			openTrack({ mediaType: issue.media_type, source: issue.source, mediaId: issue.media_id })}
	>
		<Plus class="size-5" aria-hidden="true" />
	</button>
</article>
