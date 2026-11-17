<script lang="ts">
	/** A placeholder block while data loads; still under reduced motion. */
	let { class: extra = '' }: { class?: string } = $props();
</script>

<div
	class="rounded-ct-sm bg-surface motion-safe:animate-pulse {extra}"
	aria-hidden="true"
></div>
