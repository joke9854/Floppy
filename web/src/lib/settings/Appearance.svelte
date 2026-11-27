<script lang="ts">
	import { invalidate } from '$app/navigation';
	import { djangoForm } from '#lib/csrf.ts';
	import { st } from './strings.ts';
	import { readAnswer, type SettingsScreen } from './types.ts';

	/**
	 * Appearance (appearance.html): the desktop sidebar style and, when
	 * floating, how it shows its labels. The page's detail-layout editor is
	 * hidden there too; its saved layouts post back unchanged.
	 */
	let { screen }: { screen: SettingsScreen } = $props();
	const appearance = $derived(screen.appearance!);

	// svelte-ignore state_referenced_locally
	let style = $state(screen.appearance!.sidebar_style);
	// svelte-ignore state_referenced_locally
	let floating = $state(screen.appearance!.floating_sidebar);
	let status = $state('');
	let failed = $state(false);
	let busy = $state(false);

	const floatingHint = $derived(appearance.floating_choices.find((choice) => choice.value === floating)?.hint ?? '');

	async function save(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		status = '';
		try {
			const answer = await readAnswer(
				await djangoForm(
					appearance.save_url,
					{ sidebar_style: style, floating_sidebar: floating, detail_layouts: JSON.stringify(appearance.detail_layouts) },
					{ json: true }
				)
			);
			failed = !answer.saved;
			status = answer.saved ? st.appearanceSaved : (answer.message ?? st.failed);
			if (answer.saved) await invalidate('floppy:settings');
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
		<div>
			<h2>{st.sidebar}</h2>
			<p class="ct-settings-note">{st.sidebarNote}</p>
		</div>
		<div class="ct-settings-options" role="radiogroup" aria-label={st.sidebar}>
			{#each appearance.sidebar_styles as option (option.value)}
				<label class="ct-settings-option">
					<input type="radio" name="sidebar_style" value={option.value} bind:group={style} />
					<span class="ct-settings-check"><span>{option.label}<small>{option.hint}</small></span></span>
				</label>
			{/each}
		</div>
		{#if style === 'floating'}
			<fieldset class="ct-settings-rows">
				<legend class="ct-settings-field">{st.floating}</legend>
				<div class="ct-settings-segments">
					{#each appearance.floating_choices as option (option.value)}
						<label><input type="radio" name="floating_sidebar" value={option.value} bind:group={floating} />{option.label}</label>
					{/each}
				</div>
				<p class="ct-settings-note">{floatingHint}</p>
			</fieldset>
		{/if}
	</section>
	<div class="ct-settings-section">
		<div class="ct-settings-actions is-split">
			<div>
				<p class="ct-settings-field">{st.appearance}</p>
				<p class="ct-settings-note">{appearance.is_demo ? st.demo : st.changesAfterSaving}</p>
			</div>
			<div class="ct-settings-actions">
				{#if status}<span class={['ct-settings-status', failed && 'is-error']} role="status">{status}</span>{/if}
				<button type="submit" class="ct-settings-button is-primary" disabled={busy || appearance.is_demo}>{st.saveAppearance}</button>
			</div>
		</div>
	</div>
</form>
