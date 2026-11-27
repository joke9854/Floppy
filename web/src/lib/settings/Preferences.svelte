<script lang="ts">
	import { invalidate } from '$app/navigation';
	import { djangoForm } from '#lib/csrf.ts';
	import { st } from './strings.ts';
	import { preferencesForm, readAnswer, type SettingsAutoPauseRule, type SettingsScreen } from './types.ts';

	/**
	 * Preferences (preferences.html): the display, language and tracking
	 * preferences and the auto-pause rules. The labels and options come from
	 * the server; every value posts back, as on the Django page.
	 */
	let { screen }: { screen: SettingsScreen } = $props();
	const preferences = $derived(screen.preferences!);

	const local = {
		automation: 'Automation',
		automationNote: 'Manage automated rules.',
		autoPause: 'Library Management',
		autoPauseNote: 'Pause in-progress items.',
		noRules: 'No auto-pause rules yet. Add one to get started.',
		enabledAdd: 'Enabled. Add another rule',
		disabledAdd: 'Disabled. Add a rule',
		library: 'Library',
		weeks: 'weeks',
		remove: 'Remove',
		save: 'Save Preferences',
		saved: 'Preferences updated successfully.',
		tmdbDown: 'TMDB did not answer, so the region and language lists are incomplete; saving keeps your current ones.'
	};

	// svelte-ignore state_referenced_locally
	let values = $state<Record<string, string>>({ ...screen.preferences!.values });
	// svelte-ignore state_referenced_locally
	let rules = $state<SettingsAutoPauseRule[]>(screen.preferences!.auto_pause_rules.map((rule) => ({ ...rule })));
	let status = $state('');
	let failed = $state(false);
	let busy = $state(false);

	const usedLibraries = $derived(new Set(rules.map((rule) => rule.library)));

	function addRule() {
		const free = preferences.auto_pause_libraries.find((library) => !usedLibraries.has(library.value));
		rules.push({ library: free?.value ?? 'all', weeks: 16 });
	}

	async function save(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		status = '';
		try {
			const answer = await readAnswer(await djangoForm(preferences.save_url, preferencesForm(values, rules), { json: true }));
			failed = !answer.saved;
			status = answer.saved ? local.saved : (answer.message ?? st.failed);
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
	{#each preferences.sections as section (section.title)}
		<section class="ct-settings-section">
			<div>
				<h2>{section.title}</h2>
				<p class="ct-settings-note">{section.note}</p>
			</div>
			<div class="ct-settings-rows">
				{#each section.fields as field (field.name)}
					<div class="ct-settings-pref">
						<span><label for="pref-{field.name}">{field.label}</label><small>{field.note}</small></span>
						{#if field.kind === 'switch'}
							<input
								id="pref-{field.name}"
								class="ct-settings-switch"
								type="checkbox"
								role="switch"
								checked={values[field.name] === '1'}
								onchange={(event) => (values[field.name] = event.currentTarget.checked ? '1' : '0')}
							/>
						{:else}
							<select id="pref-{field.name}" class="ct-settings-select" bind:value={values[field.name]}>
								{#each field.choices as choice (choice.value)}
									<option value={choice.value}>{choice.label}{choice.hint ? ` — ${choice.hint}` : ''}</option>
								{/each}
							</select>
						{/if}
					</div>
				{/each}
			</div>
			{#if section.fields.some((field) => field.name === 'watch_provider_region') && !preferences.tmdb_lists_loaded}
				<p class="ct-settings-note">{local.tmdbDown}</p>
			{/if}
		</section>
	{/each}

	<section class="ct-settings-section">
		<div>
			<h2>{local.automation}</h2>
			<p class="ct-settings-note">{local.automationNote}</p>
		</div>
		<div class="ct-settings-pref">
			<span>{local.autoPause}<small>{local.autoPauseNote}</small></span>
			<button type="button" class="ct-settings-button" onclick={addRule}>{rules.length ? local.enabledAdd : local.disabledAdd}</button>
		</div>
		{#if rules.length}
			<ul class="ct-settings-rows">
				{#each rules as rule, index (index)}
					<li class="ct-settings-row">
						<select class="ct-settings-select" aria-label={local.library} bind:value={rule.library}>
							{#each preferences.auto_pause_libraries as library (library.value)}
								<option value={library.value}>{library.label}</option>
							{/each}
						</select>
						<label class="ct-settings-weeks">
							<input type="number" min="1" bind:value={rule.weeks} aria-label={local.weeks} />
							{local.weeks}
						</label>
						<button type="button" class="ct-settings-button" onclick={() => rules.splice(index, 1)}>{local.remove}</button>
					</li>
				{/each}
			</ul>
		{:else}
			<p class="ct-settings-note">{local.noRules}</p>
		{/if}
	</section>

	<div class="ct-settings-section">
		<div class="ct-settings-actions is-split">
			<p class="ct-settings-note">{preferences.is_demo ? st.demo : st.changesAfterSaving}</p>
			<div class="ct-settings-actions">
				{#if status}<span class={['ct-settings-status', failed && 'is-error']} role="status">{status}</span>{/if}
				<button type="submit" class="ct-settings-button is-primary" disabled={busy || preferences.is_demo}>{local.save}</button>
			</div>
		</div>
	</div>
</form>
