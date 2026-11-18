<script lang="ts">
	import type { Snippet } from 'svelte';
	import Ellipsis from '@lucide/svelte/icons/ellipsis';
	import LogOut from '@lucide/svelte/icons/log-out';
	import Palette from '@lucide/svelte/icons/palette';
	import Bell from '@lucide/svelte/icons/bell';
	import Search from '@lucide/svelte/icons/search';
	import Settings from '@lucide/svelte/icons/settings';
	import { DropdownMenu } from 'bits-ui';
	import { page } from '$app/state';
	import { BASE } from '#lib/paths.ts';
	import Dialog from '#lib/ui/Dialog.svelte';
	import { signOut } from '#lib/session-client.ts';
	import { t } from '#lib/strings.ts';
	import LinkMenu from './LinkMenu.svelte';
	import NavLink from './NavLink.svelte';
	import {
		LIBRARY_ICON,
		LIBRARY_MORE,
		PRIMARY,
		YOU,
		isCurrentHref,
		libraryItems,
		reloadFor,
		type LibraryType,
		type NavItem
	} from './nav.ts';
	import logo from '#lib/assets/floppy-logo.png';

	/**
	 * The signed-in shell, as the Django web's CineTrack shell: from md a
	 * floating icon rail, from lg the attached labelled sidebar (the default
	 * sidebar style); below md the glass bottom bar with Library and More
	 * sheets. Glass only on the navigation, never over content.
	 */
	let {
		username,
		library,
		children
	}: { username: string; library: LibraryType[]; children: Snippet } = $props();

	const libraryLinks = $derived(libraryItems(library));
	const settingsLinks: NavItem[] = [
		{ label: t.settings, href: '/settings/account', icon: Settings },
		{ label: t.appearance, href: '/settings/appearance', icon: Palette },
		{ label: t.notifications, href: '/settings/notifications', icon: Bell }
	];
	const initials = $derived(username.slice(0, 2).toUpperCase());

	let librarySheet = $state(false);
	let moreSheet = $state(false);

	const railButton =
		'ct-focus flex h-11 w-11 items-center justify-center rounded-full text-muted transition-colors duration-(--motion-short) ease-standard hover:bg-white/6 hover:text-text data-[state=open]:bg-white/12 data-[state=open]:text-text lg:h-9 lg:w-full lg:justify-start lg:gap-3 lg:rounded-ct-sm lg:px-3';
	const tab =
		'ct-focus group flex min-h-[52px] flex-1 flex-col items-center gap-0.5 rounded-ct-md py-1 text-[11px] font-semibold text-muted aria-[current=page]:text-text';
	const tabIcon =
		'flex h-[30px] w-[52px] items-center justify-center rounded-full group-aria-[current=page]:bg-white/12';
	const sheetLink =
		'ct-focus flex h-12 items-center gap-3 rounded-ct-sm px-3 text-[15px] font-semibold text-text-secondary hover:bg-white/6';
</script>

{#snippet sheetLinks(items: NavItem[])}
	<ul class="flex flex-col">
		{#each items as item (item.href)}
			{@const Icon = item.icon}
			<li>
				<a href={item.href} data-sveltekit-reload={reloadFor(item.href)} class={sheetLink}>
					<Icon class="size-5 text-muted" aria-hidden="true" />
					{item.label}
				</a>
			</li>
		{/each}
	</ul>
{/snippet}

<div class="min-h-dvh">
	<!-- md: floating icon rail. lg: attached labelled sidebar. -->
	<nav
		aria-label={t.mainNav}
		class="ct-glass fixed top-3 left-3 z-40 hidden max-h-[calc(100dvh-24px)] w-16 flex-col items-center gap-3 rounded-ct-lg py-3 md:flex lg:inset-y-0 lg:left-0 lg:top-0 lg:max-h-none lg:w-[248px] lg:items-stretch lg:gap-2 lg:rounded-none lg:border-0 lg:border-r lg:border-white/6 lg:bg-sidebar lg:px-4 lg:pt-5 lg:pb-4 lg:shadow-none lg:backdrop-blur-none"
	>
		<a
			href="{BASE}/"
			data-sveltekit-reload={reloadFor(`${BASE}/`)}
			class="ct-focus flex items-center gap-3 rounded-ct-sm lg:px-1 lg:pb-1"
			title={t.appName}
		>
			<img src={logo} alt="" width="36" height="36" class="size-9 rounded-ct-sm" />
			<span class="sr-only text-[17px] font-bold lg:not-sr-only">{t.appName}</span>
		</a>

		<NavLink item={{ label: t.search, href: '/search', icon: Search }} />

		<!-- Many media types outgrow short screens: the list scrolls in the room left. -->
		<ul
			class="flex min-h-0 flex-1 flex-col items-center gap-1 overflow-y-auto [scrollbar-color:rgb(255_255_255/18%)_transparent] [scrollbar-width:thin] lg:items-stretch lg:gap-0.5"
		>
			{#each PRIMARY as item (item.href)}
				<li><NavLink {item} /></li>
			{/each}
			<li
				class="hidden pt-2.5 pb-1 text-xs font-bold tracking-wide text-muted uppercase lg:block lg:px-3"
			>
				{t.library}
			</li>
			{#each libraryLinks as item (item.href)}
				<li><NavLink {item} /></li>
			{/each}
			<li><NavLink item={LIBRARY_MORE[0]} /></li>
			<li>
				<LinkMenu items={LIBRARY_MORE.slice(1)} triggerClass={railButton} triggerLabel={t.more}>
					{#snippet trigger()}
						<Ellipsis class="size-5 shrink-0" aria-hidden="true" />
						<span class="sr-only text-[14px] font-semibold lg:not-sr-only">{t.more}</span>
					{/snippet}
				</LinkMenu>
			</li>
			<li
				class="hidden pt-2.5 pb-1 text-xs font-bold tracking-wide text-muted uppercase lg:block lg:px-3"
			>
				{t.you}
			</li>
			{#each YOU as item (item.href)}
				<li><NavLink {item} /></li>
			{/each}
		</ul>

		<div class="flex shrink-0 flex-col items-center lg:items-stretch">
			<LinkMenu
				items={settingsLinks}
				heading={username}
				side="right"
				align="end"
				triggerClass={railButton}
				triggerLabel={t.settings}
			>
				{#snippet trigger()}
					<span
						class="flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-strong text-xs font-bold text-text"
						aria-hidden="true">{initials}</span
					>
					<span class="sr-only flex-col items-start lg:not-sr-only lg:flex">
						<span class="text-[14px] font-semibold text-text" data-testid="username">{username}</span>
						<span class="text-xs text-muted">{t.settings}</span>
					</span>
				{/snippet}
				{#snippet footer()}
					<DropdownMenu.Item
						onSelect={signOut}
						class="flex h-10 cursor-pointer items-center gap-3 rounded-ct-xs px-3 text-[14px] font-semibold text-text-secondary outline-none data-highlighted:bg-white/8 data-highlighted:text-text"
					>
						<LogOut class="size-5 text-muted" aria-hidden="true" />
						{t.signOut}
					</DropdownMenu.Item>
				{/snippet}
			</LinkMenu>
		</div>
	</nav>

	<div class="pb-[calc(96px+env(safe-area-inset-bottom))] md:pb-0 md:pl-[88px] lg:pl-[248px]">
		{@render children()}
	</div>

	<!-- Phone: the glass bottom bar, as CineTrack's bottom navigation. -->
	<nav
		aria-label={t.mainNav}
		class="ct-glass fixed inset-x-3 bottom-[calc(10px+env(safe-area-inset-bottom))] z-40 flex rounded-ct-lg p-1.5 md:hidden"
	>
		{#each PRIMARY.slice(0, 2) as item (item.href)}
			{@const Icon = item.icon}
			<a
				href={item.href}
				data-sveltekit-reload={reloadFor(item.href)}
				aria-current={isCurrentHref(item.href, page.url.pathname) ? 'page' : undefined}
				class={tab}
			>
				<span class={tabIcon}><Icon class="size-5" aria-hidden="true" /></span>
				{item.label}
			</a>
		{/each}
		<button
			type="button"
			class={tab}
			aria-current={page.url.pathname.startsWith(`${BASE}/library/`) ? 'page' : undefined}
			onclick={() => (librarySheet = true)}
		>
			<span class={tabIcon}><LIBRARY_ICON class="size-5" aria-hidden="true" /></span>
			{t.library}
		</button>
		{#each PRIMARY.slice(2) as item (item.href)}
			{@const Icon = item.icon}
			<a
				href={item.href}
				data-sveltekit-reload={reloadFor(item.href)}
				aria-current={isCurrentHref(item.href, page.url.pathname) ? 'page' : undefined}
				class={tab}
			>
				<span class={tabIcon}><Icon class="size-5" aria-hidden="true" /></span>
				{item.label}
			</a>
		{/each}
		<button type="button" class={tab} onclick={() => (moreSheet = true)}>
			<span class={tabIcon}><Ellipsis class="size-5" aria-hidden="true" /></span>
			{t.more}
		</button>
	</nav>

	<Dialog bind:open={librarySheet} title={t.library} sheet>
		{#if libraryLinks.length}
			{@render sheetLinks(libraryLinks)}
		{:else}
			<p class="text-sm text-muted">{t.libraryEmpty}</p>
		{/if}
	</Dialog>

	<Dialog bind:open={moreSheet} title={t.more} sheet>
		<p class="px-3 text-xs font-bold tracking-wide text-muted uppercase">{t.library}</p>
		{@render sheetLinks(LIBRARY_MORE)}
		<p class="px-3 text-xs font-bold tracking-wide text-muted uppercase">{t.you}</p>
		{@render sheetLinks(YOU)}
		<p class="px-3 text-xs font-bold tracking-wide text-muted uppercase">{username}</p>
		{@render sheetLinks(settingsLinks)}
		<button type="button" class="{sheetLink} w-full" onclick={signOut}>
			<LogOut class="size-5 text-muted" aria-hidden="true" />
			{t.signOut}
		</button>
	</Dialog>
</div>
