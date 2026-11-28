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
	import './shell.css';
	import logo from '#lib/assets/floppy-logo.png';

	/**
	 * The signed-in shell, as the Django web's CineTrack shell: from md a
	 * floating icon rail, from lg the sidebar style the user chose: the attached
	 * labelled sidebar (the default) or the floating one (expanded, on hover or icons); below md the glass bottom bar with Library and More
	 * sheets. Glass only on the navigation, never over content.
	 */
	let {
		username,
		library,
		sidebarStyle = 'attached',
		floatingSidebar = 'hover',
		children
	}: {
		username: string;
		library: LibraryType[];
		sidebarStyle?: string;
		floatingSidebar?: string;
		children: Snippet;
	} = $props();

	const libraryLinks = $derived(libraryItems(library));
	const settingsLinks: NavItem[] = [
		{ label: t.settings, href: `${BASE}/settings/account`, icon: Settings },
		{ label: t.appearance, href: `${BASE}/settings/appearance`, icon: Palette },
		{ label: t.notifications, href: `${BASE}/settings/notifications`, icon: Bell }
	];
	const initials = $derived(username.slice(0, 2).toUpperCase());

	let librarySheet = $state(false);
	let moreSheet = $state(false);

	const railButton =
		'ct-rail-link ct-focus flex h-11 w-11 items-center justify-center rounded-full text-muted transition-colors duration-(--motion-short) ease-standard hover:bg-white/6 hover:text-text data-[state=open]:bg-white/12 data-[state=open]:text-text';
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
	<!-- md: floating icon rail. lg: the chosen sidebar style (shell.css). -->
	<nav
		aria-label={t.mainNav}
		data-ct-sidebar={sidebarStyle}
		data-ct-floating={floatingSidebar}
		class="ct-rail ct-glass fixed top-3 left-3 z-40 hidden max-h-[calc(100dvh-24px)] w-16 flex-col items-center gap-3 rounded-ct-lg py-3 md:flex"
	>
		<a
			href="{BASE}/"
			data-sveltekit-reload={reloadFor(`${BASE}/`)}
			class="ct-focus flex items-center gap-3 rounded-ct-sm ct-rail-brand"
			title={t.appName}
		>
			<img src={logo} alt="" width="36" height="36" class="size-9 rounded-ct-sm" />
			<span class="ct-rail-label sr-only text-[17px] font-bold">{t.appName}</span>
		</a>

		<NavLink item={{ label: t.search, href: '/search', icon: Search }} />

		<!-- Many media types outgrow short screens: the list scrolls in the room left. -->
		<ul
			class="ct-rail-list flex min-h-0 flex-1 flex-col items-center gap-1 overflow-y-auto [scrollbar-color:rgb(255_255_255/18%)_transparent] [scrollbar-width:thin]"
		>
			{#each PRIMARY as item (item.href)}
				<li><NavLink {item} /></li>
			{/each}
			<li
				class="hidden pt-2.5 pb-1 text-xs font-bold tracking-wide text-muted uppercase ct-rail-section"
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
						<span class="ct-rail-label sr-only text-[14px] font-semibold">{t.more}</span>
					{/snippet}
				</LinkMenu>
			</li>
			<li
				class="hidden pt-2.5 pb-1 text-xs font-bold tracking-wide text-muted uppercase ct-rail-section"
			>
				{t.you}
			</li>
			{#each YOU as item (item.href)}
				<li><NavLink {item} /></li>
			{/each}
		</ul>

		<div class="ct-rail-foot flex shrink-0 flex-col items-center">
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
					<span class="ct-rail-label ct-rail-account sr-only flex-col items-start">
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

	<div class="ct-shell-content pb-[calc(96px+env(safe-area-inset-bottom))] md:pb-0 md:pl-[88px]">
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
