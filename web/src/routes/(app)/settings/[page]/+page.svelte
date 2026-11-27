<script lang="ts">
	import '#lib/styles/screen.css';
	import '#lib/settings/settings.css';
	import { goto } from '$app/navigation';
	import { BASE } from '#lib/paths.ts';
	import { st } from '#lib/settings/strings.ts';
	import type { PageProps } from './$types';

	/**
	 * Settings (P4-J), as the Django pages (users/*.html): the settings nav
	 * (a select on phones) and one page, loaded on its own. Pages the web does
	 * not draw yet keep their Django links.
	 */
	let { data }: PageProps = $props();
	const screen = $derived(data.screen);

	const pages = {
		account: () => import('#lib/settings/Account.svelte'),
		appearance: () => import('#lib/settings/Appearance.svelte'),
		notifications: () => import('#lib/settings/Notifications.svelte'),
		sidebar: () => import('#lib/settings/MediaTypes.svelte'),
		about: () => import('#lib/settings/About.svelte')
	} as const;
	const loader = $derived(pages[screen.page as keyof typeof pages]);

	const hrefFor = (item: { slug: string; href: string; web: boolean }) => (item.web ? `${BASE}/settings/${item.slug}` : item.href);

	function pick(event: Event) {
		const slug = (event.currentTarget as HTMLSelectElement).value;
		const item = screen.nav.flatMap((section) => section.items).find((entry) => entry.slug === slug);
		if (!item) return;
		if (item.web) void goto(hrefFor(item));
		else window.location.href = item.href;
	}
</script>

<svelte:head><title>{screen.title} - Floppy</title></svelte:head>

<main class="mx-auto max-w-[1200px] px-5 pt-6 md:px-8 md:pt-8">
	<h1 class="ct-page-title mb-5">{st.settings}</h1>
	<div class="ct-settings">
		<nav class="ct-settings-nav" aria-label={st.sections}>
			{#each screen.nav as section (section.label)}
				<div>
					<h2>{section.label}</h2>
					{#each section.items as item (item.slug)}
						<a
							href={hrefFor(item)}
							aria-current={item.slug === screen.page ? 'page' : undefined}
							data-sveltekit-reload={item.web ? undefined : ''}>{item.label}</a
						>
					{/each}
				</div>
			{/each}
		</nav>
		<select class="ct-settings-picker" aria-label={st.sections} value={screen.page} onchange={pick}>
			{#each screen.nav as section (section.label)}
				<optgroup label={section.label}>
					{#each section.items as item (item.slug)}<option value={item.slug}>{item.label}</option>{/each}
				</optgroup>
			{/each}
		</select>
		<div class="ct-settings-page">
			{#if loader}
				{#await loader() then { default: Page }}
					<Page {screen} />
				{/await}
			{/if}
		</div>
	</div>
</main>
