<script lang="ts">
	import ArrowDown from '@lucide/svelte/icons/arrow-down';
	import ArrowUp from '@lucide/svelte/icons/arrow-up';
	import { invalidateAll } from '$app/navigation';
	import { djangoForm } from '#lib/csrf.ts';
	import { st } from './strings.ts';
	import { mediaTypesForm, moveEntry, readAnswer, type SettingsMediaType, type SettingsScreen } from './types.ts';

	/**
	 * Media types (sidebar.html): the touch overlay setting, and which types
	 * show and in what order. The page posts every type; saving refreshes the
	 * shell, whose Library follows these types.
	 */
	let { screen }: { screen: SettingsScreen } = $props();
	const sidebar = $derived(screen.sidebar!);

	// svelte-ignore state_referenced_locally
	let types = $state<SettingsMediaType[]>(screen.sidebar!.media_types.map((type) => ({ ...type })));
	// svelte-ignore state_referenced_locally
	let clickable = $state(screen.sidebar!.clickable_media_cards);
	let status = $state('');
	let failed = $state(false);
	let busy = $state(false);

	async function save(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		status = '';
		try {
			const answer = await readAnswer(await djangoForm(sidebar.save_url, mediaTypesForm(types, clickable), { json: true }));
			failed = !answer.saved;
			status = answer.saved ? (answer.changed === false ? st.noChanges : st.mediaTypesSaved) : (answer.message ?? st.failed);
			if (answer.saved) await invalidateAll();
		} catch {
			failed = true;
			status = st.failed;
		} finally {
			busy = false;
		}
	}
</script>

<form class="ct-settings-rows" onsubmit={save}>
	<section class="ct-settings-section">
		<p class="ct-settings-note">{st.mediaTypesNote}</p>
		<label class="ct-settings-check">
			<input type="checkbox" bind:checked={clickable} />
			<span>{st.hideOverlay}<small>{st.hideOverlayNote}</small></span>
		</label>
	</section>
	<section class="ct-settings-section">
		<div>
			<h2>{st.mediaTypes}</h2>
			<p class="ct-settings-note">{st.mediaTypesHelp}</p>
		</div>
		<ul class="ct-settings-rows">
			{#each types as type, index (type.value)}
				<li class={['ct-settings-row', !type.enabled && 'is-off']}>
					<label class="ct-settings-check" style="flex: 1">
						<input type="checkbox" bind:checked={type.enabled} />
						<span>{type.label}</span>
					</label>
					<button type="button" class="is-icon" aria-label="{st.moveUp}: {type.label}" disabled={index === 0} onclick={() => (types = moveEntry(types, index, -1))}>
						<ArrowUp class="size-4" aria-hidden="true" />
					</button>
					<button
						type="button"
						class="is-icon"
						aria-label="{st.moveDown}: {type.label}"
						disabled={index === types.length - 1}
						onclick={() => (types = moveEntry(types, index, 1))}
					>
						<ArrowDown class="size-4" aria-hidden="true" />
					</button>
				</li>
			{/each}
		</ul>
	</section>
	<div class="ct-settings-actions">
		{#if status}<span class={['ct-settings-status', failed && 'is-error']} role="status">{status}</span>{/if}
		<button type="submit" class="ct-settings-button is-primary" disabled={busy}>{st.savePreferences}</button>
	</div>
</form>
