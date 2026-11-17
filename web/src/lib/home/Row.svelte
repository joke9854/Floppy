<script lang="ts">
	import type { Snippet } from 'svelte';

	/**
	 * A horizontal row of cards. Touch and trackpads scroll it natively, a
	 * mouse drags it (a drag never opens the card under the pointer), and once
	 * focused the arrow keys scroll it.
	 */
	let {
		labelledby,
		progress = false,
		children
	}: { labelledby: string; progress?: boolean; children: Snippet } = $props();

	let row: HTMLDivElement;
	let dragging = $state(false);
	let start: { x: number; scroll: number; id: number } | null = null;

	function down(event: PointerEvent) {
		if (event.pointerType !== 'mouse' || event.button !== 0) return;
		start = { x: event.clientX, scroll: row.scrollLeft, id: event.pointerId };
	}

	function move(event: PointerEvent) {
		if (!start || event.pointerId !== start.id) return;
		const dx = event.clientX - start.x;
		if (!dragging) {
			if (Math.abs(dx) < 6) return;
			// Capture only once it is a drag: capturing on press would send
			// every click to the row instead of the card's link or check.
			dragging = true;
			row.setPointerCapture(event.pointerId);
		}
		row.scrollLeft = start.scroll - dx;
	}

	function up(event: PointerEvent) {
		if (!start || event.pointerId !== start.id) return;
		start = null;
		if (row.hasPointerCapture(event.pointerId)) row.releasePointerCapture(event.pointerId);
		// Let the click that ends a drag land on nothing.
		if (dragging) requestAnimationFrame(() => (dragging = false));
	}
</script>

<!-- A scrollable region takes focus so keyboards can scroll it (WCAG 2.1.1). -->
<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div
	bind:this={row}
	class={['ct-row', progress && 'has-progress', dragging && 'is-dragging']}
	role="region"
	aria-labelledby={labelledby}
	tabindex="0"
	onpointerdown={down}
	onpointermove={move}
	onpointerup={up}
	onpointercancel={up}
>
	{@render children()}
</div>
