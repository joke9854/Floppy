<script lang="ts">
	import Check from '@lucide/svelte/icons/check';
	import Copy from '@lucide/svelte/icons/copy';

	/**
	 * A read-only value with a Copy button (webhook URLs, keys, templates).
	 * Clicking the field selects it, as on the Django page.
	 */
	let { value, label, multiline = false, rows = 6 }: { value: string; label: string; multiline?: boolean; rows?: number } = $props();
	let copied = $state(false);
	let timer: ReturnType<typeof setTimeout> | undefined;

	async function copy() {
		try {
			await navigator.clipboard.writeText(value);
			copied = true;
			clearTimeout(timer);
			timer = setTimeout(() => (copied = false), 3000);
		} catch {
			alert('Could not copy to clipboard. Please select the text and press Ctrl+C/Cmd+C to copy.');
		}
	}

	const select = (event: Event) => (event.currentTarget as HTMLInputElement | HTMLTextAreaElement).select();
</script>

<div class="ct-settings-copy">
	{#if multiline}
		<textarea readonly {rows} aria-label={label} spellcheck="false" onclick={select}>{value}</textarea>
	{:else}
		<input type="text" readonly {value} aria-label={label} spellcheck="false" onclick={select} />
	{/if}
	<button type="button" class="is-icon" aria-label="Copy {label}" title="Copy" onclick={copy}>
		{#if copied}<Check class="size-4 text-emerald-300" aria-hidden="true" />{:else}<Copy class="size-4" aria-hidden="true" />{/if}
	</button>
</div>
