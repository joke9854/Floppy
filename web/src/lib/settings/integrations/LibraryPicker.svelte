<script lang="ts">
	/**
	 * A multi-select of Plex libraries in a details dropdown (the Django
	 * plex_library_selector). The caller owns the selection and gets the next
	 * list through `onchange`.
	 */
	let {
		libraries,
		selected,
		onchange,
		label = 'Libraries',
		disabled = false
	}: {
		libraries: { value: string; label: string; server_name: string }[];
		selected: string[];
		onchange: (next: string[]) => void;
		label?: string;
		disabled?: boolean;
	} = $props();

	const allSelected = $derived(libraries.length > 0 && libraries.every((library) => selected.includes(library.value)));
	const summary = $derived(
		libraries.length === 0 ? 'No libraries available' : allSelected ? 'All Libraries' : selected.length === 0 ? 'No Libraries' : `${selected.length} selected`
	);

	function toggle(value: string, on: boolean) {
		onchange(on ? [...selected.filter((item) => item !== value), value] : selected.filter((item) => item !== value));
	}
</script>

<div class="ct-settings-field">
	<span>{label}</span>
	<details class="ct-settings-more">
		<summary aria-label="{label}: {summary}">{summary}</summary>
		<div>
			<div class="ct-settings-actions is-split">
				<strong>Plex Libraries</strong>
				<button
					type="button"
					class="ct-settings-button"
					disabled={disabled || libraries.length === 0}
					onclick={() => onchange(allSelected ? [] : libraries.map((library) => library.value))}>{allSelected ? 'Hide all' : 'Show all'}</button
				>
			</div>
			{#each libraries as library (library.value)}
				<label class="ct-settings-check">
					<input type="checkbox" {disabled} checked={selected.includes(library.value)} onchange={(event) => toggle(library.value, event.currentTarget.checked)} />
					<span>{library.server_name ? `${library.label} (${library.server_name})` : library.label}</span>
				</label>
			{/each}
		</div>
	</details>
</div>
