<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';

	/** The plain card material: no blur, so long lists stay cheap. */
	let {
		class: extra = '',
		children,
		...rest
	}: HTMLAttributes<HTMLDivElement> & { children: Snippet } = $props();
</script>

<div class="ct-card rounded-ct-md p-5 {extra}" {...rest}>
	{@render children()}
</div>
