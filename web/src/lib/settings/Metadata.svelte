<script lang="ts">
	import { invalidate } from '$app/navigation';
	import { djangoForm } from '#lib/csrf.ts';
	import { st } from './strings.ts';
	import { readAnswer, type SettingsProvider, type SettingsScreen } from './types.ts';

	/**
	 * Metadata (metadata.html): which provider each library uses, and the
	 * provider keys. Instance keys are for superusers; anyone can add a
	 * personal key. Stored keys show only as the masked preview the Django
	 * page shows, and typed keys go straight to the form post.
	 */
	let { screen }: { screen: SettingsScreen } = $props();
	const metadata = $derived(screen.metadata!);

	const local = {
		readOnly: 'Instance keys are read-only: you are not a superuser. Personal keys still work.',
		howTo: 'How to become one',
		askAdmin: 'Ask an administrator, or promote your own account.',
		noSuperuser: 'This instance has no superuser yet.',
		promoteRun: 'Floppy does not make anyone a superuser during setup, so a fresh install has none. Run this',
		onHost: 'on the host running the container',
		whereInstalled: 'where Floppy is installed',
		promoteAfter: 'Then sign out and back in. Add --list to see every account first.',
		providers: 'Metadata Providers',
		providersNote: 'Which provider supplies metadata for each library.',
		provider: 'Provider',
		animeLibrary: 'Anime Library',
		notConfigured: 'Not configured',
		noSwitch: "This library doesn't have a switchable default yet — configure a provider below to make it available.",
		save: 'Save',
		saved: 'Saved.',
		managed: 'Managed by an administrator. Only a superuser can change instance-wide credentials, so these fields are read-only.',
		envSet: 'Set in the environment. This provider is configured by',
		envRemove: 'Remove it there to manage it here.',
		optional: '(optional)',
		notSet: 'Not set',
		blankKeeps: 'A field left blank removes its stored value, so the provider falls back to the environment or the shared default.',
		removeStored: 'Remove stored credentials',
		personal: 'Your personal key is used for your own requests instead of the instance key. Background jobs keep using the instance key.',
		your: 'Your',
		savedReplace: 'Saved — enter a new value to replace',
		savePersonal: 'Save personal key',
		removePersonal: 'Remove personal key',
		makeDefault: 'Make this the default provider for',
		setDefault: 'Set as default for',
		getKey: 'Get a key from',
		convertTitle: 'Convert your existing anime?',
		convertBody:
			'New shows will use your new Anime Provider straight away. Converting rebuilds the shows already tracked in the other format. Moving to MyAnimeList drops per-episode history, and titles that cannot be converted safely are left exactly as they are.',
		convertCount: (count: number) => `You have ${count} ${count === 1 ? 'show' : 'shows'} already tracked in the other format.`,
		keep: 'Keep my library as it is',
		convert: 'Convert my existing anime'
	};
	const statusLabel: Record<string, string> = {
		user: 'Personal key',
		env: 'Environment',
		db: 'Instance key',
		default: 'Shared default'
	};

	let busy = $state('');
	let notice = $state<{ key: string; text: string; failed: boolean } | null>(null);
	let animePrompt = $state(0);

	// What each library's form holds.
	// svelte-ignore state_referenced_locally
	let picked = $state<Record<string, string>>(
		Object.fromEntries(screen.metadata!.libraries.map((library) => [library.media_type, library.current_provider]))
	);
	// svelte-ignore state_referenced_locally
	let animeMode = $state(screen.metadata!.anime_library_mode);
	// Typed keys, per provider and form ("instance" or "personal").
	// svelte-ignore state_referenced_locally
	let typed = $state<Record<string, Record<string, string>>>(
		Object.fromEntries(
			screen.metadata!.groups.flatMap((group) =>
				group.providers.flatMap((provider) => [
					[`${provider.slug}:instance`, {}],
					[`${provider.slug}:personal`, {}]
				])
			)
		)
	);

	async function post(key: string, url: string, fields: Record<string, string>, after?: () => void) {
		busy = key;
		notice = null;
		try {
			const answer = await readAnswer(await djangoForm(url, fields, { json: true }));
			notice = { key, text: answer.saved ? answer.message || local.saved : (answer.message ?? st.failed), failed: !answer.saved };
			if (answer.saved) {
				after?.();
				if (answer.anime_shape_prompt_count) animePrompt = answer.anime_shape_prompt_count;
				await invalidate('floppy:settings');
			}
		} catch {
			notice = { key, text: st.failed, failed: true };
		} finally {
			busy = '';
		}
	}

	function saveKeys(provider: SettingsProvider, form: 'instance' | 'personal') {
		const fields = provider.fields.filter((field) => (form === 'personal' ? field.personal : !field.locked));
		const values = typed[`${provider.slug}:${form}`] ?? {};
		const body = Object.fromEntries(fields.map((field) => [field.name, (values[field.name] ?? '').trim()]));
		const url = form === 'personal' ? provider.urls.personal : provider.urls.save;
		void post(`${provider.slug}:${form}`, url, body, () => (typed[`${provider.slug}:${form}`] = {}));
	}

	function removePersonal(provider: SettingsProvider) {
		const body = Object.fromEntries(provider.fields.filter((field) => field.personal).map((field) => [field.name, '']));
		void post(`${provider.slug}:personal`, provider.urls.personal, body);
	}

	const hasTyped = (provider: SettingsProvider, form: 'instance' | 'personal') =>
		Object.values(typed[`${provider.slug}:${form}`] ?? {}).some((value) => value.trim());
</script>

{#snippet status(key: string)}
	{#if notice?.key === key}<span class={['ct-settings-status', notice.failed && 'is-error']} role="status">{notice.text}</span>{/if}
{/snippet}

{#if metadata.promote}
	<details class="ct-settings-more">
		<summary><span>{local.readOnly}</span><span class="ct-settings-link">{local.howTo}</span></summary>
		<div>
			<p class="ct-settings-note">
				{metadata.promote.instance_has_superuser ? local.askAdmin : local.noSuperuser}
				{local.promoteRun}
				{metadata.promote.in_container ? local.onHost : local.whereInstalled}:
			</p>
			<code class="ct-settings-code">{metadata.promote.command}</code>
			<p class="ct-settings-note">{local.promoteAfter}</p>
		</div>
	</details>
{/if}

{#if animePrompt}
	<section class="ct-settings-section" aria-live="polite">
		<h2>{local.convertTitle}</h2>
		<p class="ct-settings-note">{local.convertCount(animePrompt)} {local.convertBody}</p>
		<div class="ct-settings-actions">
			{@render status('convert')}
			<button type="button" class="ct-settings-button" onclick={() => (animePrompt = 0)}>{local.keep}</button>
			<button
				type="button"
				class="ct-settings-button is-primary"
				disabled={busy !== ''}
				onclick={() => post('convert', metadata.convert_anime_url, {}, () => (animePrompt = 0))}>{local.convert}</button
			>
		</div>
	</section>
{/if}

{#if metadata.libraries.length}
	<section class="ct-settings-section">
		<div>
			<h2>{local.providers}</h2>
			<p class="ct-settings-note">{local.providersNote}</p>
		</div>
		<div class="ct-settings-rows">
			{#each metadata.libraries as library (library.media_type)}
				<details class="ct-settings-more">
					<summary>
						<span>{library.label}</span>
						<span class="ct-settings-badge">{library.current_label}</span>
					</summary>
					<div>
						{#if library.configurable}
							<label class="ct-settings-field">
								{local.provider}
								<select bind:value={picked[library.media_type]}>
									{#each library.choices as choice (choice.value)}
										<option value={choice.value} disabled={!choice.configured}
											>{choice.label}{choice.configured ? '' : ` (${local.notConfigured})`}</option
										>
									{/each}
								</select>
							</label>
							{#if library.media_type === 'anime'}
								<label class="ct-settings-field">
									{local.animeLibrary}
									<select bind:value={animeMode}>
										{#each metadata.anime_library_modes as mode (mode.value)}<option value={mode.value}>{mode.label}</option>{/each}
									</select>
								</label>
							{/if}
							<div class="ct-settings-actions">
								{@render status(`library:${library.media_type}`)}
								<button
									type="button"
									class="ct-settings-button is-primary"
									disabled={busy !== '' || metadata.is_demo}
									onclick={() =>
										post(`library:${library.media_type}`, library.url, {
											source: picked[library.media_type],
											...(library.media_type === 'anime' ? { anime_library_mode: animeMode } : {})
										})}>{local.save}</button
								>
							</div>
						{:else}
							<ul class="ct-settings-rows">
								{#each library.choices as choice (choice.value)}
									<li class="ct-settings-row">
										<span>{choice.label}</span>
										<span class={['ct-settings-badge', choice.configured && 'is-on']}>{choice.configured ? 'Configured' : local.notConfigured}</span>
									</li>
								{/each}
							</ul>
							<p class="ct-settings-note">{local.noSwitch}</p>
						{/if}
					</div>
				</details>
			{/each}
		</div>
	</section>
{/if}

{#each metadata.groups as group (group.key)}
	<section class="ct-settings-section">
		<div>
			<h2>{group.label}</h2>
			<p class="ct-settings-note">{group.description}</p>
		</div>
		<div class="ct-settings-rows">
			{#each group.providers as provider (provider.slug)}
				{@const instance = typed[`${provider.slug}:instance`]}
				{@const personal = typed[`${provider.slug}:personal`]}
				<details class="ct-settings-more">
					<summary>
						<span>{provider.label}<small>{provider.description}</small></span>
						<span class={['ct-settings-badge', provider.status && 'is-on']}>{statusLabel[provider.status] ?? local.notConfigured}</span>
					</summary>
					<div>
						{#if !metadata.can_edit_instance}<p class="ct-settings-note">{local.managed}</p>{/if}
						{#if provider.locked}
							<p class="ct-settings-note">
								{local.envSet}
								{#each provider.fields as field, index (field.name)}<code class="ct-settings-code">{field.setting}</code>{index < provider.fields.length - 1 ? ' and ' : ''}{/each}.
								{local.envRemove}
							</p>
						{/if}
						{#each provider.fields as field (field.name)}
							<label class="ct-settings-field">
								<span>{field.label} {field.required ? '' : local.optional}</span>
								{#if field.locked || !metadata.can_edit_instance}
									<input type="text" readonly value={field.preview || local.notSet} />
								{:else}
									<input
										type={field.secret ? 'password' : 'text'}
										autocomplete="off"
										spellcheck="false"
										placeholder={field.has_instance_value ? field.preview : field.placeholder}
										bind:value={instance[field.name]}
									/>
								{/if}
							</label>
						{/each}
						{#if metadata.can_edit_instance && !provider.locked}
							<p class="ct-settings-note">{local.blankKeeps}</p>
							<div class="ct-settings-actions">
								{@render status(`${provider.slug}:instance`)}
								{#if provider.has_instance_value}
									<button
										type="button"
										class="ct-settings-button"
										disabled={busy !== ''}
										onclick={() => post(`${provider.slug}:instance`, provider.urls.clear, {})}>{local.removeStored}</button
									>
								{/if}
								<button
									type="button"
									class="ct-settings-button is-primary"
									disabled={busy !== '' || !hasTyped(provider, 'instance')}
									onclick={() => saveKeys(provider, 'instance')}>{local.save}</button
								>
							</div>
						{/if}

						{#if provider.user_scope}
							<p class="ct-settings-note">{local.personal}</p>
							{#each provider.fields.filter((field) => field.personal) as field (field.name)}
								<label class="ct-settings-field">
									{local.your}
									{field.label}
									<input
										type={field.secret ? 'password' : 'text'}
										autocomplete="off"
										spellcheck="false"
										placeholder={field.has_personal_value ? local.savedReplace : field.placeholder}
										bind:value={personal[field.name]}
									/>
								</label>
							{/each}
							<div class="ct-settings-actions">
								{@render status(`${provider.slug}:personal`)}
								{#if provider.fields.some((field) => field.personal && field.has_personal_value)}
									<button type="button" class="ct-settings-button" disabled={busy !== ''} onclick={() => removePersonal(provider)}
										>{local.removePersonal}</button
									>
								{/if}
								<button
									type="button"
									class="ct-settings-button is-primary"
									disabled={busy !== '' || !hasTyped(provider, 'personal')}
									onclick={() => saveKeys(provider, 'personal')}>{local.savePersonal}</button
								>
							</div>
						{/if}

						{#if provider.settable_media_types.length}
							<p class="ct-settings-note">{local.makeDefault}</p>
							<div class="ct-settings-actions">
								{@render status(`${provider.slug}:default`)}
								{#each provider.settable_media_types as type (type.value)}
									<button
										type="button"
										class="ct-settings-button"
										disabled={busy !== '' || !provider.configured}
										onclick={() => post(`${provider.slug}:default`, type.url, { source: provider.slug })}>{local.setDefault} {type.label}</button
									>
								{/each}
							</div>
						{/if}
						{#if provider.docs_url}
							<p class="ct-settings-note">
								{local.getKey}
								<a class="ct-settings-link" href={provider.docs_url} target="_blank" rel="noopener noreferrer">{provider.label}<span class="sr-only">{st.newTab}</span></a>
							</p>
						{/if}
					</div>
				</details>
			{/each}
		</div>
	</section>
{/each}
