<script lang="ts">
	import X from '@lucide/svelte/icons/x';
	import { t } from '#lib/strings.ts';
	import { tt } from './strings.ts';

	export type DateAction = 'start-now' | 'just-finished' | 'release-date' | 'now' | 'copy' | 'clear';

	/**
	 * A play date (the Django dialog's date_time_picker.html): the native date
	 * and time input, the quick actions (Start Now, Just Finished, Release
	 * Date) and Now, Copy from the other date, None. The value is the page's;
	 * a stored fraction of a second stays in it until the user edits the date.
	 */
	let {
		id,
		label,
		value,
		trackTime,
		releaseLabel,
		copyLabel,
		oninput,
		onaction
	}: {
		id: string;
		label: string;
		value: string;
		trackTime: boolean;
		releaseLabel: string;
		copyLabel: string;
		oninput: (value: string) => void;
		onaction: (action: DateAction) => void;
	} = $props();

	// The native input shows seconds at most; the posted value keeps the rest.
	const shown = $derived(trackTime ? value.replace(/\.\d+$/, '') : value.slice(0, 10));
</script>

<div class="ct-track-date">
	<label class="ct-track-label" for={id}>{label}</label>
	<div class="ct-track-date__row">
		<input
			{id}
			class="ct-track-input"
			type={trackTime ? 'datetime-local' : 'date'}
			step={trackTime ? 1 : undefined}
			value={shown}
			onchange={(event) => oninput(event.currentTarget.value)}
		/>
		{#if value}
			<button type="button" class="ct-track-icon" aria-label={tt.clearDate} title={tt.clearDate} onclick={() => onaction('clear')}>
				<X class="size-4" aria-hidden="true" />
			</button>
		{/if}
	</div>
	<div class="ct-track-chips" role="group" aria-label={tt.dateQuickActions(label)}>
		<button type="button" onclick={() => onaction('start-now')}>{tt.startNow}</button>
		<button type="button" onclick={() => onaction('just-finished')}>{tt.justFinished}</button>
		<button
			type="button"
			disabled={!releaseLabel}
			title={releaseLabel ? undefined : tt.releaseDateUnavailable}
			onclick={() => onaction('release-date')}>{t.releaseDate}</button
		>
		<button type="button" onclick={() => onaction('now')}>{tt.now}</button>
		<button type="button" onclick={() => onaction('copy')}>{tt.copyFrom(copyLabel)}</button>
	</div>
</div>
