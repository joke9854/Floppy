<script lang="ts">
	import ArrowDown from '@lucide/svelte/icons/arrow-down';
	import ArrowUp from '@lucide/svelte/icons/arrow-up';
	import Trash from '@lucide/svelte/icons/trash-2';
	import type { components } from '#lib/api/client.ts';
	import { djangoWrite } from '#lib/csrf.ts';
	import { tt } from './strings.ts';

	type Schema = components['schemas']['TrackCollectionSchema'];
	type SavedGroup = components['schemas']['TrackSchemaGroup'];
	type Field = { key: number; id: number | null; label: string; field_type: string; options: string; media_types: string[] };
	type Group = { key: number; id: number | null; name: string; fields: Field[] };

	/**
	 * The custom-field editor (P4-D8), as the page's Manage custom fields
	 * (collection_custom_fields.html, collectionCustomFields.js): groups and
	 * their fields (name, type, media types, a select's options), added,
	 * removed and reordered (up and down for the page's drag handles), saved
	 * as the user's whole schema. Fields made since the dialog opened (an
	 * import, another tab) are left alone, as on the page.
	 */
	let {
		schema,
		itemId,
		itemMediaType,
		onsaved,
		oncancel
	}: {
		schema: Schema;
		itemId: number;
		itemMediaType: string;
		onsaved: (groups: SavedGroup[]) => void;
		oncancel: () => void;
	} = $props();

	let next = 0;
	const hydrate = (groups: SavedGroup[]): Group[] =>
		groups.map((group) => ({
			key: next++,
			id: group.id,
			name: group.name,
			fields: group.fields.map((field) => ({
				key: next++,
				id: field.id,
				label: field.label,
				field_type: field.field_type,
				options: field.options.join('\n'),
				media_types: [...field.media_types]
			}))
		}));

	// svelte-ignore state_referenced_locally
	let groups = $state<Group[]>(hydrate(schema.groups));
	// svelte-ignore state_referenced_locally
	const known = schema.groups.flatMap((group) => group.fields.map((field) => field.id)).filter((id) => id != null);
	let saving = $state(false);
	let error = $state('');

	const payload = () => ({
		item_id: itemId,
		known_field_ids: known,
		groups: groups.map((group) => ({
			id: group.id,
			name: group.name.trim(),
			fields: group.fields.map((field) => ({
				id: field.id,
				label: field.label.trim(),
				field_type: field.field_type,
				media_types: [...field.media_types],
				options:
					field.field_type === 'select'
						? field.options
								.split('\n')
								.map((option) => option.trim())
								.filter(Boolean)
						: []
			}))
		}))
	});
	// svelte-ignore state_referenced_locally
	const saved = JSON.stringify(payload());
	const dirty = $derived(JSON.stringify(payload()) !== saved);

	function move<T>(list: T[], index: number, by: number): T[] {
		const target = index + by;
		if (target < 0 || target >= list.length) return list;
		const copy = [...list];
		[copy[index], copy[target]] = [copy[target], copy[index]];
		return copy;
	}

	function validate(): string {
		for (const group of groups) {
			if (!group.name.trim()) return tt.groupNeedsName;
			for (const field of group.fields) {
				if (!field.label.trim()) return tt.fieldNeedsLabel;
				if (!field.media_types.length) return tt.fieldNeedsMediaType(field.label.trim());
			}
		}
		return '';
	}

	async function save() {
		if (saving) return;
		error = validate();
		if (error) return;
		saving = true;
		try {
			const response = await djangoWrite(schema.save_url, 'POST', payload());
			const answer = await response.json().catch(() => ({}));
			if (!response.ok || !answer.success) {
				error = answer.error || tt.fieldsSaveFailed;
				return;
			}
			onsaved(answer.groups as SavedGroup[]);
		} catch {
			error = tt.fieldsSaveFailed;
		} finally {
			saving = false;
		}
	}
</script>

<div class="ct-fields">
	{#each groups as group, g (group.key)}
		<section class="ct-fields__group" aria-label={group.name || tt.groupName}>
			<div class="ct-metadata__row">
				<input class="ct-track-input" aria-label={tt.groupName} placeholder={tt.groupName} bind:value={group.name} />
				<button type="button" class="ct-track-icon" aria-label={tt.moveUp(group.name || tt.groupName)} disabled={g === 0} onclick={() => (groups = move(groups, g, -1))}>
					<ArrowUp class="size-4" aria-hidden="true" />
				</button>
				<button type="button" class="ct-track-icon" aria-label={tt.moveDown(group.name || tt.groupName)} disabled={g === groups.length - 1} onclick={() => (groups = move(groups, g, 1))}>
					<ArrowDown class="size-4" aria-hidden="true" />
				</button>
				<button type="button" class="ct-track-icon is-danger" aria-label={tt.removeGroup(group.name || tt.groupName)} onclick={() => (groups = groups.filter((other) => other !== group))}>
					<Trash class="size-4" aria-hidden="true" />
				</button>
			</div>
			{#each group.fields as field, f (field.key)}
				<div class="ct-fields__field">
					<div class="ct-metadata__row">
						<input class="ct-track-input" aria-label={tt.fieldName} placeholder={tt.fieldName} bind:value={field.label} />
						<select class="ct-track-input ct-fields__type" aria-label={tt.fieldType(field.label || tt.fieldName)} bind:value={field.field_type}>
							{#each schema.field_types as choice (choice.value)}
								<option value={choice.value}>{choice.label}</option>
							{/each}
						</select>
					</div>
					<details class="ct-fields__types">
						<summary>
							{field.media_types.length === 0
								? tt.mediaTypes
								: field.media_types.length === 1
									? (schema.media_types.find((choice) => choice.value === field.media_types[0])?.label ?? field.media_types[0])
									: tt.selectedCount(field.media_types.length)}
						</summary>
						<div class="ct-fields__checks">
							{#each schema.media_types as choice (choice.value)}
								<label class="ct-collection__check">
									<input
										type="checkbox"
										checked={field.media_types.includes(choice.value)}
										onchange={(e) =>
											(field.media_types = e.currentTarget.checked
												? [...field.media_types, choice.value]
												: field.media_types.filter((value) => value !== choice.value))}
									/>
									<span>{choice.label}</span>
								</label>
							{/each}
						</div>
					</details>
					{#if field.field_type === 'select'}
						<textarea class="ct-track-input" rows="2" aria-label={tt.optionsFor(field.label || tt.fieldName)} placeholder={tt.onePerLine} bind:value={field.options}></textarea>
					{/if}
					<div class="ct-fields__field-actions">
						<button type="button" class="ct-track-icon" aria-label={tt.moveUp(field.label || tt.fieldName)} disabled={f === 0} onclick={() => (group.fields = move(group.fields, f, -1))}>
							<ArrowUp class="size-4" aria-hidden="true" />
						</button>
						<button type="button" class="ct-track-icon" aria-label={tt.moveDown(field.label || tt.fieldName)} disabled={f === group.fields.length - 1} onclick={() => (group.fields = move(group.fields, f, 1))}>
							<ArrowDown class="size-4" aria-hidden="true" />
						</button>
						<button type="button" class="ct-track-icon is-danger" aria-label={tt.removeField(field.label || tt.fieldName)} onclick={() => (group.fields = group.fields.filter((other) => other !== field))}>
							<Trash class="size-4" aria-hidden="true" />
						</button>
					</div>
				</div>
			{/each}
			<button
				type="button"
				class="ct-track-btn"
				onclick={() =>
					(group.fields = [
						...group.fields,
						{ key: next++, id: null, label: '', field_type: 'text', options: '', media_types: itemMediaType ? [itemMediaType] : [] }
					])}>{tt.addField}</button
			>
		</section>
	{/each}
	<button type="button" class="ct-track-btn" onclick={() => (groups = [...groups, { key: next++, id: null, name: '', fields: [] }])}
		>{tt.addGroup}</button
	>
	{#if error}<p class="ct-track__problem" role="alert">{error}</p>{/if}
	<div class="ct-track__actions">
		<div class="ct-track__actions-start">
			{#if dirty}<span class="ct-track__help">{tt.unsavedChanges}</span>{/if}
		</div>
		<div class="ct-track__actions-end">
			<button type="button" class="ct-track-btn" onclick={oncancel}>{tt.discard}</button>
			<button type="button" class="ct-track-btn is-primary" disabled={saving} onclick={save}>{saving ? tt.saving : tt.saveFields}</button>
		</div>
	</div>
</div>
