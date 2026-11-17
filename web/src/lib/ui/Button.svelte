<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLButtonAttributes } from 'svelte/elements';

	type Variant = 'primary' | 'secondary' | 'ghost';
	type Size = 'md' | 'sm';

	let {
		variant = 'secondary',
		size = 'md',
		class: extra = '',
		children,
		...rest
	}: HTMLButtonAttributes & { variant?: Variant; size?: Size; children: Snippet } = $props();

	const VARIANTS: Record<Variant, string> = {
		primary: 'bg-accent text-accent-contrast hover:brightness-110',
		secondary: 'ct-glass-control text-text hover:bg-white/10',
		ghost: 'text-muted hover:bg-white/6 hover:text-text'
	};
	const SIZES: Record<Size, string> = {
		md: 'h-11 px-5 text-[15px]',
		sm: 'h-9 px-4 text-sm'
	};
</script>

<button
	type="button"
	class="ct-focus inline-flex items-center justify-center gap-2 rounded-full font-semibold transition-[background-color,filter,color] duration-(--motion-short) ease-standard disabled:cursor-default disabled:opacity-50 {VARIANTS[
		variant
	]} {SIZES[size]} {extra}"
	{...rest}
>
	{@render children()}
</button>
