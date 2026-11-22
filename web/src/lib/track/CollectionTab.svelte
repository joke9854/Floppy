<script lang="ts">
	import Minus from '@lucide/svelte/icons/minus';
	import Pencil from '@lucide/svelte/icons/pencil';
	import Plus from '@lucide/svelte/icons/plus';
	import Trash from '@lucide/svelte/icons/trash-2';
	import type { components } from '#lib/api/client.ts';
	import { djangoForm } from '#lib/csrf.ts';
	import FieldsEditor from './FieldsEditor.svelte';
	import { tt } from './strings.ts';

	type Collection = components['schemas']['TrackCollection'];
	type Field = components['schemas']['TrackField'];
	type SavedGroup = components['schemas']['TrackSchemaGroup'];

	/**
	 * The Collection tab (P4-D5), as the Django dialog's collection_modal.html
	 * for one episode: the owned copies, each removable, then the Add Copy
	 * form with the user's custom fields, and (P4-D8) the custom-field editor.
	 */
	let { collection, onsaved }: { collection: Collection; onsaved: (message: string) => void } = $props();

	// svelte-ignore state_referenced_locally
	let customGroups = $state.raw(collection.custom_groups);
	// svelte-ignore state_referenced_locally
	let schema = $state.raw(collection.schema);
	let managing = $state(false);
	const customFields = $derived(customGroups.flatMap((group) => group.fields));

	/** The saved schema's groups for this media type, as the page re-renders them. */
	function fieldsSaved(groups: SavedGroup[]) {
		schema = { ...schema, groups };
		customGroups = groups
			.map((group) => ({
				name: group.name,
				fields: group.fields
					.filter((field) => field.media_types.includes(collection.item_media_type))
					.map((field) => {
						const name = `custom_field_${field.id}`;
						return {
							name,
							label: field.label,
							kind: field.field_type as Field['kind'],
							value: values[name] ?? '',
							choices:
								field.field_type === 'select'
									? [{ value: '', label: tt.select }, ...field.options.map((option) => ({ value: option, label: option }))]
									: [],
							required: false,
							min: null,
							max: null,
							step: field.field_type === 'number' ? 'any' : null,
							placeholder: '',
							help_text: ''
						} satisfies Field;
					})
			}))
			.filter((group) => group.fields.length);
		managing = false;
	}

	// svelte-ignore state_referenced_locally
	let values = $state<Record<string, string>>(
		Object.fromEntries(
			[...collection.fields, ...collection.custom_groups.flatMap((group) => group.fields)].map((field) => [
				field.name,
				field.value
			])
		)
	);
	let errors = $state<Record<string, string[]>>({});
	let busy = $state(false);
	let problem = $state('');

	/** The page's form posts a checkbox only when it is ticked. */
	function body(): Record<string, string> {
		const fields: Record<string, string> = { item_id: String(collection.item_id) };
		for (const field of [...collection.fields, ...customFields]) {
			const value = values[field.name] ?? '';
			if (field.kind === 'checkbox') {
				if (value) fields[field.name] = 'on';
			} else fields[field.name] = value;
		}
		return fields;
	}

	function step(field: Field, direction: 1 | -1) {
		const size = Number(field.step) || 1;
		const current = Number(values[field.name]) || 0;
		let next = Math.round((current + direction * size) / size) * size;
		if (field.min !== null && next < Number(field.min)) next = Number(field.min);
		const decimals = (String(field.step ?? '').split('.')[1] ?? '').length;
		values[field.name] = next.toFixed(decimals);
	}

	async function send(url: string, fields: Record<string, string>) {
		if (busy) return;
		busy = true;
		problem = '';
		errors = {};
		try {
			const response = await djangoForm(url, fields, { json: true });
			const answer = await response.json().catch(() => ({}));
			if (response.ok) onsaved(answer.message ?? '');
			else if (answer.errors) {
				errors = answer.errors;
				problem = tt.trackFixErrors;
			} else problem = tt.trackSaveFailed;
		} catch {
			problem = tt.trackSaveFailed;
		} finally {
			busy = false;
		}
	}
</script>

{#snippet input(field: Field, id: string)}
	{#if field.kind === 'checkbox'}
		<label class="ct-track-label" for={id}>{field.label}</label>
		<label class="ct-collection__check">
			<input
				{id}
				type="checkbox"
				checked={values[field.name] === 'on'}
				onchange={(e) => (values[field.name] = e.currentTarget.checked ? 'on' : '')}
			/>
			<span>{tt.yes}</span>
		</label>
	{:else}
		<label class="ct-track-label" for={id}>{field.label}</label>
		{#if field.kind === 'select'}
			<select {id} class="ct-track-input" bind:value={values[field.name]}>
				{#each field.choices as choice, i (i)}
					<option value={choice.value}>{choice.label}</option>
				{/each}
			</select>
		{:else if field.kind === 'number'}
			<div class="ct-track-number">
				<input
					{id}
					class="ct-track-input"
					type="number"
					inputmode="decimal"
					min={field.min ?? undefined}
					step={field.step ?? undefined}
					placeholder={field.placeholder}
					bind:value={values[field.name]}
				/>
				<button type="button" class="ct-track-icon" aria-label={tt.decrease(field.label)} onclick={() => step(field, -1)}>
					<Minus class="size-4" aria-hidden="true" />
				</button>
				<button type="button" class="ct-track-icon" aria-label={tt.increase(field.label)} onclick={() => step(field, 1)}>
					<Plus class="size-4" aria-hidden="true" />
				</button>
			</div>
		{:else if field.kind === 'datetime' || field.kind === 'date'}
			<input
				{id}
				class="ct-track-input"
				type={field.kind === 'datetime' ? 'datetime-local' : 'date'}
				step={field.kind === 'datetime' ? '1' : undefined}
				bind:value={values[field.name]}
			/>
		{:else}
			<input {id} class="ct-track-input" type="text" placeholder={field.placeholder} bind:value={values[field.name]} />
		{/if}
	{/if}
	{#each errors[field.name] ?? [] as error (error)}
		<p class="ct-track__error">{error}</p>
	{/each}
{/snippet}

<div class="ct-track__form">
	{#if collection.entries.length}
		<section>
			<h3 class="ct-collection__heading">{tt.existingEntries}</h3>
			<ul class="ct-collection__entries">
				{#each collection.entries as entry (entry.id)}
					<li class="ct-collection__entry">
						<div class="min-w-0">
							{#each entry.lines as line, index (index)}
								<p class={index === 0 ? 'ct-collection__format' : 'ct-track__help'}>{line}</p>
							{/each}
						</div>
						<button
							type="button"
							class="ct-track-icon is-danger"
							aria-label={tt.removeCopy}
							title={tt.removeCopy}
							disabled={busy}
							onclick={() => send(entry.remove_url, {})}
						>
							<Trash class="size-4" aria-hidden="true" />
						</button>
					</li>
				{/each}
			</ul>
		</section>
	{/if}

	<form
		class="ct-collection__add"
		novalidate
		onsubmit={(event) => {
			event.preventDefault();
			send(collection.save_url, body());
		}}
	>
		<h3 class="ct-collection__heading">{collection.add_label}</h3>
		<div class="ct-track__grid ct-collection__grid">
			{#each collection.fields as field, index (field.name)}
				<div class={['ct-track__field', index === 0 && 'is-first']}>
					{@render input(field, `collection-${field.name}`)}
				</div>
			{/each}
		</div>

		<section>
			<div class="ct-discover__row">
				<h3 class="ct-collection__heading">{tt.customFields}</h3>
				<button
					type="button"
					class="ct-track-icon"
					title={tt.manageFields}
					aria-label={tt.manageFields}
					aria-pressed={managing}
					onclick={() => (managing = !managing)}
				>
					<Pencil class="size-4" aria-hidden="true" />
				</button>
			</div>
			{#if managing}
				<FieldsEditor
					{schema}
					itemId={collection.item_id}
					itemMediaType={collection.item_media_type}
					onsaved={fieldsSaved}
					oncancel={() => (managing = false)}
				/>
			{:else}
			{#each customGroups as group, g (g)}
				<h4 class="ct-collection__group">{group.name}</h4>
				<div class="ct-track__grid ct-collection__grid">
					{#each group.fields as field (field.name)}
						<div class="ct-track__field">
							{@render input(field, field.name)}
						</div>
					{/each}
				</div>
			{:else}
				<p class="ct-track__help">{tt.noCustomFields}</p>
			{/each}
			{/if}
		</section>

		{#each errors.__all__ ?? [] as error (error)}
			<p class="ct-track__error">{error}</p>
		{/each}
		{#if problem}<p class="ct-track__problem" role="alert">{problem}</p>{/if}
		<div class="ct-track__actions">
			<div class="ct-track__actions-end">
				<button type="submit" class="ct-track-btn is-primary" disabled={busy}>{tt.addCopy}</button>
			</div>
		</div>
	</form>
</div>
