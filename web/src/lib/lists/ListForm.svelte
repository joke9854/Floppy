<script lang="ts">
	import './lists.css';
	import X from '@lucide/svelte/icons/x';
	import { djangoForm } from '#lib/csrf.ts';
	import Dialog from '#lib/ui/Dialog.svelte';
	import { lf, ls } from './strings.ts';
	import { addTag, previewUrl, type ListsScreen } from './types.ts';

	/**
	 * Create or edit a list (the page's list_form.html). An edit loads every
	 * field (list_edit_form, JSON) and posts every field back: the form saves
	 * them all, so a field left out would be cleared. Collaborators go by
	 * username. Errors come back per field, which the page drops on edit.
	 */
	let {
		open = $bindable(false),
		listId = null,
		smart = false,
		screen,
		onsaved
	}: {
		open?: boolean;
		listId?: number | null;
		smart?: boolean;
		screen: ListsScreen;
		onsaved: (location: string | null) => void;
	} = $props();

	interface Values {
		list_id: number | null;
		name: string;
		description: string;
		tags: string[];
		collaborators: string[];
		allow_recommendations: boolean;
		is_smart: boolean;
		is_public: boolean;
		include_notes: boolean;
		public_slug: string;
		can_delete: boolean;
		activity_url: string;
	}

	const blank = (isSmart: boolean): Values => ({
		list_id: null,
		name: '',
		description: '',
		tags: [],
		collaborators: [],
		allow_recommendations: false,
		is_smart: isSmart,
		is_public: false,
		include_notes: false,
		public_slug: '',
		can_delete: false,
		activity_url: ''
	});

	let values = $state<Values>(blank(false));
	let loaded = $state(false);
	let saving = $state(false);
	let errors = $state<Record<string, string[]>>({});
	let tagDraft = $state('');
	let userDraft = $state('');
	let confirming = $state(false);

	$effect(() => {
		if (!open) return;
		errors = {};
		confirming = false;
		tagDraft = '';
		userDraft = '';
		if (listId === null) {
			values = blank(smart);
			loaded = true;
			return;
		}
		loaded = false;
		const url = screen.urls.edit_form.replace('{id}', String(listId));
		fetch(url, { credentials: 'same-origin', headers: { accept: 'application/json' } })
			.then((response) => (response.ok ? response.json() : Promise.reject(response.status)))
			.then((body) => {
				values = { ...body, collaborators: body.collaborators.map((entry: { username: string }) => entry.username) };
				loaded = true;
			})
			.catch(() => (errors = { __all__: [ls.failed] }));
	});

	function fields(): Record<string, string | string[]> {
		const data: Record<string, string | string[]> = {
			name: values.name,
			description: values.description,
			tags: values.tags,
			collaborator_usernames: values.collaborators,
			// Posted even while hidden, as the page's form does, so it is kept.
			public_slug: values.public_slug
		};
		if (values.list_id !== null) data.list_id = String(values.list_id);
		for (const flag of ['allow_recommendations', 'is_smart', 'is_public', 'include_notes'] as const) {
			if (values[flag]) data[flag] = 'on';
		}
		if (values.list_id === null && values.is_smart) data.smart_create_flow = '1';
		return data;
	}

	async function save() {
		saving = true;
		errors = {};
		try {
			const response = await djangoForm(values.list_id === null ? screen.urls.create : screen.urls.edit, fields(), {
				json: true
			});
			const body = await response.json().catch(() => ({}));
			if (!response.ok || !body.saved) {
				errors = body.errors ?? { __all__: [body.error ?? ls.failed] };
			} else {
				open = false;
				// A new smart list opens its rules, as the page does.
				onsaved(values.list_id === null && values.is_smart ? body.location : null);
			}
		} catch {
			errors = { __all__: [ls.failed] };
		}
		saving = false;
	}

	async function remove() {
		if (values.list_id === null) return;
		saving = true;
		try {
			const response = await djangoForm(screen.urls.delete, { list_id: String(values.list_id) }, { json: true });
			const body = await response.json().catch(() => ({}));
			if (!response.ok || !body.deleted) throw new Error(body.error ?? ls.failed);
			open = false;
			onsaved(null);
		} catch (error) {
			errors = { __all__: [error instanceof Error ? error.message : ls.failed] };
		}
		saving = false;
		confirming = false;
	}

	function keyAdd(event: KeyboardEvent, kind: 'tag' | 'user') {
		if (event.key !== 'Enter' && event.key !== ',') return;
		event.preventDefault();
		if (kind === 'tag') {
			values.tags = addTag(values.tags, tagDraft);
			tagDraft = '';
		} else {
			values.collaborators = addTag(values.collaborators, userDraft);
			userDraft = '';
		}
	}

	const reference = $derived(values.list_id === null ? '' : String(values.list_id));
	const tagOptions = $derived(screen.tag_options.filter((tag) => !values.tags.includes(tag)));
</script>

<Dialog bind:open title={listId === null ? lf.createTitle : lf.editTitle} sheet>
	{#if loaded}
		<form
			class="ct-list-form"
			onsubmit={(event) => {
				event.preventDefault();
				save();
			}}
		>
			{#if errors.__all__}<p class="ct-list-form__error" role="alert">{errors.__all__.join(' ')}</p>{/if}
			<label>
				<span>{lf.name}</span>
				<input bind:value={values.name} required maxlength="255" />
				{#if errors.name}<small class="ct-list-form__error">{errors.name.join(' ')}</small>{/if}
			</label>
			<label>
				<span>{lf.description}</span>
				<textarea bind:value={values.description} rows="4"></textarea>
			</label>
			<div class="ct-list-form__field">
				<span>{lf.tags}</span>
				<div class="ct-chips">
					{#each values.tags as tag (tag)}
						<span class="ct-chip">
							{tag}
							<button type="button" aria-label={lf.remove(tag)} onclick={() => (values.tags = values.tags.filter((t) => t !== tag))}>
								<X class="size-3" aria-hidden="true" />
							</button>
						</span>
					{/each}
					<input
						bind:value={tagDraft}
						list="ct-list-tag-options"
						placeholder={lf.tagsPlaceholder}
						onkeydown={(event) => keyAdd(event, 'tag')}
						onblur={() => {
							values.tags = addTag(values.tags, tagDraft);
							tagDraft = '';
						}}
					/>
					<datalist id="ct-list-tag-options">
						{#each tagOptions as tag (tag)}<option value={tag}></option>{/each}
					</datalist>
				</div>
				<small>{lf.tagsHelp}</small>
			</div>
			<div class="ct-list-form__field">
				<span>{lf.collaborators}</span>
				<div class="ct-chips">
					{#each values.collaborators as name (name)}
						<span class="ct-chip">
							{name}
							<button
								type="button"
								aria-label={lf.remove(name)}
								onclick={() => (values.collaborators = values.collaborators.filter((n) => n !== name))}
							>
								<X class="size-3" aria-hidden="true" />
							</button>
						</span>
					{/each}
					<input
						bind:value={userDraft}
						placeholder={lf.collaboratorsPlaceholder}
						autocomplete="off"
						onkeydown={(event) => keyAdd(event, 'user')}
						onblur={() => {
							values.collaborators = addTag(values.collaborators, userDraft);
							userDraft = '';
						}}
					/>
				</div>
				{#if errors.collaborators}
					<small class="ct-list-form__error">{errors.collaborators.join(' ')}</small>
				{:else}
					<small>{lf.collaboratorsHelp}</small>
				{/if}
			</div>
			<label class="ct-list-form__check">
				<input type="checkbox" bind:checked={values.is_smart} />
				<span>{lf.smart}<small>{lf.smartHelp}</small></span>
			</label>
			<label class="ct-list-form__check">
				<input type="checkbox" bind:checked={values.is_public} />
				<span>{lf.public}<small>{lf.publicHelp}</small></span>
			</label>
			<label class="ct-list-form__check">
				<input type="checkbox" bind:checked={values.allow_recommendations} disabled={!values.is_public} />
				<span>{lf.recommendations}<small>{lf.recommendationsHelp}</small></span>
			</label>
			<label class="ct-list-form__check">
				<input type="checkbox" bind:checked={values.include_notes} disabled={!values.is_public} />
				<span>{lf.notes}<small>{lf.notesHelp}</small></span>
			</label>
			{#if values.is_public}
				<label>
					<span>{lf.slug}</span>
					<input bind:value={values.public_slug} maxlength="255" />
					{#if errors.public_slug}
						<small class="ct-list-form__error">{errors.public_slug.join(' ')}</small>
					{:else}
						<small>{lf.slugHelp}</small>
					{/if}
					{#if values.public_slug || reference}
						<small>{lf.currentUrl} {previewUrl(screen.urls.url_template, values.public_slug, reference)}</small>
					{/if}
				</label>
			{:else}
				<small class="ct-list-form__note">{lf.slugPrivate}</small>
			{/if}

			{#if confirming}
				<div class="ct-list-form__confirm" role="alertdialog">
					<p>{lf.confirmDelete(values.name)}</p>
					<div class="ct-list-form__actions">
						<button type="button" class="ct-lists-button" onclick={() => (confirming = false)}>{lf.cancel}</button>
						<button type="button" class="ct-lists-button is-danger" disabled={saving} onclick={remove}>
							{lf.confirmDeleteButton}
						</button>
					</div>
				</div>
			{:else}
				<div class="ct-list-form__actions">
					{#if values.list_id !== null}
						{#if values.activity_url}
							<a class="ct-lists-link" href={values.activity_url} data-sveltekit-reload>{lf.activity}</a>
						{/if}
						<button
							type="button"
							class="ct-lists-button is-danger"
							disabled={!values.can_delete || saving}
							onclick={() => (confirming = true)}
						>
							{lf.delete}
						</button>
					{/if}
					<button type="submit" class="ct-lists-button is-primary" disabled={saving}>
						{saving ? lf.saving : values.list_id === null ? lf.create : lf.save}
					</button>
				</div>
			{/if}
		</form>
	{:else if errors.__all__}
		<p class="ct-list-form__error" role="alert">{errors.__all__.join(' ')}</p>
	{:else}
		<p class="ct-list-form__note">{lf.loading}</p>
	{/if}
</Dialog>
