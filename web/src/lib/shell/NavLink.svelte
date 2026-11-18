<script lang="ts">
	import { page } from '$app/state';
	import { isCurrentHref, reloadFor, type NavItem } from './nav.ts';

	/**
	 * One sidebar link: an icon in the compact rail (md), icon and label in
	 * the attached sidebar (lg). Django pages load in full; this app's screens
	 * navigate in place and mark the current one.
	 */
	let { item, current = false }: { item: NavItem; current?: boolean } = $props();
	const Icon = $derived(item.icon);
	const isCurrent = $derived(current || isCurrentHref(item.href, page.url.pathname));
</script>

<a
	href={item.href}
	data-sveltekit-reload={reloadFor(item.href)}
	title={item.label}
	aria-current={isCurrent ? 'page' : undefined}
	class="ct-focus group flex h-11 w-11 items-center justify-center rounded-full text-muted transition-colors duration-(--motion-short) ease-standard hover:bg-white/6 hover:text-text aria-[current=page]:bg-white/12 aria-[current=page]:text-text lg:h-9 lg:w-full lg:justify-start lg:gap-3 lg:rounded-ct-sm lg:px-3"
>
	<Icon
		class="size-5 shrink-0 group-aria-[current=page]:text-(--poster-accent)"
		aria-hidden="true"
	/>
	<span class="sr-only text-[14px] font-semibold lg:not-sr-only lg:truncate">{item.label}</span>
</a>
