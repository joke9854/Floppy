<script lang="ts">
	import type { HTMLInputAttributes } from 'svelte/elements';

	let {
		label,
		error = '',
		value = $bindable(''),
		id = `field-${Math.random().toString(36).slice(2, 9)}`,
		...rest
	}: HTMLInputAttributes & { label: string; error?: string; value?: string } = $props();
</script>

<label class="flex flex-col gap-1.5" for={id}>
	<span class="text-sm font-semibold text-text-secondary">{label}</span>
	<input
		{id}
		class="ct-focus h-11 rounded-ct-sm border border-surface-border bg-surface-dim px-3.5 text-[15px] text-text placeholder:text-muted/70 transition-colors duration-(--motion-short) ease-standard focus:border-accent"
		aria-invalid={error ? 'true' : undefined}
		bind:value
		{...rest}
	/>
	{#if error}
		<span class="text-sm text-error">{error}</span>
	{/if}
</label>
