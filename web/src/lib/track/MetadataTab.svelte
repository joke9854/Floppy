<script lang="ts">
	import type { components } from '#lib/api/client.ts';
	import { djangoForm } from '#lib/csrf.ts';
	import { detailHref } from '#lib/shell/nav.ts';
	import PickerSearch from './PickerSearch.svelte';
	import { tt } from './strings.ts';

	type Metadata = components['schemas']['TrackMetadata'];
	type Section = 'provider' | 'remap' | 'language' | 'move' | 'edition' | 'release' | 'custom' | 'image' | 'grouped';

	/**
	 * The Metadata tab (P4-D6a), as the Django dialog's
	 * media_metadata_panel.html: the display provider, the metadata language,
	 * custom metadata and the image URL, each saved on its own. The image is
	 * also part of the General form (`image`/`onimage`), as on the page.
	 * P4-D6b adds the page's searches: remap the display provider's match,
	 * move the title to another library, pick a Hardcover edition or a
	 * MusicBrainz release.
	 */
	let {
		metadata,
		image,
		onimage,
		onsaved
	}: {
		metadata: Metadata;
		image: string;
		onimage: (value: string) => void;
		onsaved: (message: string) => void;
	} = $props();

	// svelte-ignore state_referenced_locally
	let provider = $state(metadata.provider?.value ?? '');
	// svelte-ignore state_referenced_locally
	let language = $state(metadata.language?.value ?? '');
	// svelte-ignore state_referenced_locally
	let custom = $state<Record<string, string>>(
		Object.fromEntries((metadata.custom?.fields ?? []).map((field) => [field.name, field.value]))
	);
	let busy = $state<Section | null>(null);
	let problem = $state<{ section: Section; text: string } | null>(null);
	let errors = $state<Record<string, string[]>>({});

	async function send(section: Section, url: string, fields: Record<string, string>, moved = false) {
		if (busy) return;
		busy = section;
		problem = null;
		errors = {};
		try {
			const response = await djangoForm(url, fields, { json: true });
			const answer = await response.json().catch(() => ({}));
			if (response.ok) {
				// A library move lands on the new title's page, as on the page.
				if (moved && answer.location) window.location.assign(detailHref(answer.location));
				else onsaved(answer.message ?? '');
				return;
			}
			if (answer.errors) errors = answer.errors;
			problem = { section, text: answer.error ?? (answer.errors ? tt.trackFixErrors : tt.trackSaveFailed) };
		} catch {
			problem = { section, text: tt.trackSaveFailed };
		} finally {
			busy = null;
		}
	}
</script>

{#snippet outcome(section: Section)}
	{#if problem?.section === section}<p class="ct-track__problem" role="alert">{problem.text}</p>{/if}
{/snippet}

{#snippet saveButton(label: string)}
	<div class="ct-track__actions-end">
		<button type="submit" class="ct-track-btn is-primary" disabled={busy !== null}>{label}</button>
	</div>
{/snippet}

<div class="ct-track__form">
	{#if metadata.provider}
		{@const p = metadata.provider}
		<section class="ct-metadata__section">
		<form
			class="ct-metadata__form"
			novalidate
			onsubmit={(event) => {
				event.preventDefault();
				send('provider', p.save_url, { provider });
			}}
		>
			<div>
				<h3 class="ct-discover__title">{tt.metadataProvider}</h3>
				<p class="ct-track__help">{tt.metadataProviderHelp(p.identity_label)}</p>
			</div>
			<div class="ct-discover__row">
				<div>
					<p class="ct-metadata__text">{tt.displayProvider(p.display_label)}</p>
					<p class="ct-track__help">{tt.trackingProvider(p.identity_label)}</p>
				</div>
				{#if p.mapping_status === 'missing'}
					<span class="ct-metadata__badge is-warning">{tt.mappingNeeded}</span>
				{:else if p.mapping_status === 'mapped'}
					<span class="ct-metadata__badge is-ok">{tt.mapped}</span>
				{/if}
			</div>
			<div class="ct-metadata__row">
				<select class="ct-track-input" aria-label={tt.metadataProvider} bind:value={provider}>
					{#each p.options as option (option.value)}
						<option value={option.value}>{option.label}</option>
					{/each}
				</select>
				{@render saveButton(tt.saveProvider)}
			</div>
			{@render outcome('provider')}
		</form>
		{#if p.remap}
			{@const r = p.remap}
			<div class="ct-metadata__form">
				<p class="ct-track__help">{r.prompt}</p>
				<PickerSearch
					url={r.search_url}
					label={r.placeholder}
					placeholder={r.placeholder}
					busy={busy !== null}
					pickLabel={tt.useMatch}
					onpick={(id) => send('remap', r.save_url, { provider: r.provider, provider_media_id: id })}
				/>
				{@render outcome('remap')}
			</div>
		{/if}
		</section>
	{/if}

	{#if metadata.language}
		{@const l = metadata.language}
		<form
			class="ct-metadata__section"
			novalidate
			onsubmit={(event) => {
				event.preventDefault();
				send('language', l.save_url, { language });
			}}
		>
			<div>
				<h3 class="ct-discover__title">{tt.metadataLanguage}</h3>
				<p class="ct-track__help">{tt.metadataLanguageHelp}</p>
			</div>
			<div class="ct-metadata__row">
				<select class="ct-track-input" aria-label={tt.metadataLanguage} bind:value={language}>
					{#each l.options as option (option.value)}
						<option value={option.value}>{option.label}</option>
					{/each}
				</select>
				{@render saveButton(tt.saveLanguage)}
			</div>
			{@render outcome('language')}
		</form>
	{/if}

	{#if metadata.move}
		{@const m = metadata.move}
		<section class="ct-metadata__section">
			<div>
				<h3 class="ct-discover__title">{tt.moveTo(m.target_label)}</h3>
				<p class="ct-track__help">{tt.moveHelp(m.target_source_label)}</p>
			</div>
			<PickerSearch
				url={m.search_url}
				label={tt.searchIn(m.target_label)}
				placeholder={tt.searchIn(m.target_label)}
				onFocus
				busy={busy !== null}
				pickLabel={tt.moveToTitle}
				onpick={(id) =>
					send(
						'move',
						m.save_url,
						{ target_media_type: m.target_media_type, target_source: m.target_source, target_media_id: id },
						true
					)}
			/>
			{@render outcome('move')}
		</section>
	{/if}

	{#each [{ section: 'edition' as const, picker: metadata.edition }, { section: 'release' as const, picker: metadata.release }] as entry (entry.section)}
		{#if entry.picker}
			{@const e = entry.picker}
			{@const isRelease = entry.section === 'release'}
			<section class="ct-metadata__section">
				<div>
					<h3 class="ct-discover__title">{isRelease ? tt.specificRelease : tt.edition}</h3>
					<p class="ct-track__help">{isRelease ? tt.releaseHelp : tt.editionHelp}</p>
				</div>
				{#if e.selected}
					<div>
						<p class="ct-track-label">{isRelease ? tt.selectedRelease : tt.selectedEdition}</p>
						<div class="ct-picker__result is-selected">
							{#if e.selected.image}<img src={e.selected.image} alt="" class="ct-picker__image" />{/if}
							<span class="min-w-0 flex-1">
								<span class="ct-picker__title">{e.selected.title}</span>
								{#each e.selected.lines as line, l (l)}<span class="ct-picker__line">{line}</span>{/each}
							</span>
						</div>
					</div>
				{/if}
				{#if e.save_url}
					<PickerSearch
						url={e.search_url}
						label={isRelease ? tt.searchReleases : tt.searchEditions}
						placeholder={isRelease ? tt.searchReleases : tt.searchEditions}
						onFocus
						busy={busy !== null}
						pickLabel={isRelease ? tt.useRelease : tt.useEdition}
						onpick={(id) => send(entry.section, e.save_url, isRelease ? { release_id: id } : { edition_id: id })}
					/>
				{/if}
				{@render outcome(entry.section)}
			</section>
		{/if}
	{/each}

	{#if metadata.custom}
		{@const c = metadata.custom}
		<form
			class="ct-metadata__section"
			novalidate
			onsubmit={(event) => {
				event.preventDefault();
				send('custom', c.save_url, { ...custom });
			}}
		>
			<div>
				<h3 class="ct-discover__title">{tt.customMetadata}</h3>
				<p class="ct-track__help">{tt.customMetadataHelp}</p>
			</div>
			<div class="ct-track__grid ct-collection__grid">
				{#each c.fields as field (field.name)}
					{@const id = `track-${field.name}`}
					<div class={['ct-track__field', c.wide.includes(field.name) && 'is-first']}>
						<label class="ct-track-label" for={id}>{field.label}</label>
						{#if field.kind === 'textarea'}
							<textarea {id} class="ct-track-input" rows="4" placeholder={field.placeholder} bind:value={custom[field.name]}></textarea>
						{:else if field.kind === 'number'}
							<input
								{id}
								class="ct-track-input"
								type="number"
								inputmode="numeric"
								min={field.min ?? undefined}
								bind:value={custom[field.name]}
							/>
						{:else}
							<input
								{id}
								class="ct-track-input"
								type={field.kind === 'date' ? 'date' : 'text'}
								placeholder={field.placeholder}
								bind:value={custom[field.name]}
							/>
						{/if}
						{#if field.help_text}<p class="ct-track__help">{field.help_text}</p>{/if}
						{#each errors[field.name] ?? [] as error (error)}
							<p class="ct-track__error">{error}</p>
						{/each}
					</div>
				{/each}
			</div>
			<div class="ct-track__actions">{@render saveButton(tt.saveMetadata)}</div>
			{@render outcome('custom')}
		</form>
	{/if}

	{#if metadata.image}
		{@const i = metadata.image}
		<form
			class="ct-metadata__section"
			novalidate
			onsubmit={(event) => {
				event.preventDefault();
				if (i.save_url) send('image', i.save_url, { image_url: image });
			}}
		>
			<label class="ct-track-label" for="track-image_url">{i.field.label}</label>
			<div class="ct-metadata__row">
				<input
					id="track-image_url"
					class="ct-track-input"
					type="url"
					placeholder={i.field.placeholder}
					value={image}
					oninput={(e) => onimage(e.currentTarget.value)}
				/>
				{#if i.save_url}{@render saveButton(tt.saveImage)}{/if}
			</div>
			{#each errors.image_url ?? [] as error (error)}
				<p class="ct-track__error">{error}</p>
			{/each}
			{#if !i.save_url}<p class="ct-track__help">{tt.imageWithGeneral}</p>{/if}
			{@render outcome('image')}
		</form>
	{/if}

	{#if metadata.grouped}
		{@const g = metadata.grouped}
		<form
			class="ct-metadata__section"
			novalidate
			onsubmit={(event) => {
				event.preventDefault();
				send('grouped', g.save_url, { provider: g.provider }, true);
			}}
		>
			<div>
				<h3 class="ct-discover__title">{tt.convertGrouped}</h3>
				{#each g.lines as line, l (l)}
					<p class={l === 0 ? 'ct-track__help' : 'ct-metadata__text'}>{line}</p>
				{/each}
			</div>
			{#if g.seasons.length}
				<ul class="ct-picker__results">
					{#each g.seasons as season, s (s)}
						<li class={['ct-picker__result', season.target && 'is-selected']}>
							<span class="min-w-0 flex-1">
								<span class="ct-picker__title">
									{season.label}{#if season.target}<span class="ct-metadata__badge is-ok ml-2">{tt.conversionTarget}</span>{/if}
								</span>
								{#if season.date}<span class="ct-picker__line">{season.date}</span>{/if}
								{#if season.mapped}<span class="ct-picker__line">{season.mapped}</span>{/if}
							</span>
							<span class="ct-picker__line">{season.episodes}</span>
						</li>
					{/each}
				</ul>
			{/if}
			<div class="ct-track__actions">{@render saveButton(tt.convertGrouped)}</div>
			{@render outcome('grouped')}
		</form>
	{/if}
</div>
