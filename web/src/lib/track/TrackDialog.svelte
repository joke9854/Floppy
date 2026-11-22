<script lang="ts">
	import Minus from '@lucide/svelte/icons/minus';
	import Plus from '@lucide/svelte/icons/plus';
	import X from '@lucide/svelte/icons/x';
	import { Dialog } from 'bits-ui';
	import type { components } from '#lib/api/client.ts';
	import { djangoForm } from '#lib/csrf.ts';
	import { t } from '#lib/strings.ts';
	import { tt } from './strings.ts';
	import DateField, { type DateAction } from './DateField.svelte';
	import CollectionTab from './CollectionTab.svelte';
	import DiscoverTab from './DiscoverTab.svelte';
	import MetadataTab from './MetadataTab.svelte';
	import PlaysTab from './PlaysTab.svelte';
	import type { TrackTarget } from './open.svelte.ts';
	import {
		changeStatus,
		clearDate,
		copyFromOther,
		formatValue,
		initialState,
		justFinished,
		releaseDate,
		setDate,
		settle,
		startNow,
		type DateField as DateName,
		type TrackState
	} from './rules.ts';
	import './track.css';

	type Screen = components['schemas']['TrackScreen'];
	type Field = components['schemas']['TrackField'];

	/**
	 * The track dialog's General tab (P4-D1), the Django dialog's form: the
	 * fields in the page's order, the dates with their shortcuts, notes, then
	 * Delete, Rewatch, Save as another play and Update / Add. It posts the
	 * page's own endpoints and shows the form's errors.
	 */
	let {
		target,
		onclose,
		onsaved
	}: {
		target: TrackTarget;
		onclose: () => void;
		onsaved: (message: string) => void;
	} = $props();

	let screen = $state.raw<Screen | null>(null);
	let form = $state.raw<TrackState | null>(null);
	let loadError = $state('');
	let busy = $state(false);
	let errors = $state.raw<Record<string, string[]>>({});
	let problem = $state('');
	let rewatchSince = $state('');
	/** The Django dialog's tabs: General, then Metadata, Collection, Episode Plays and Discover where the page has them. */
	let tab = $state<'general' | 'metadata' | 'plays' | 'collection' | 'discover'>('general');

	function apiPath(): string {
		const query = new URLSearchParams();
		if (target.season != null) query.set('season_number', String(target.season));
		if (target.episode != null) query.set('episode_number', String(target.episode));
		if (target.instanceId != null) query.set('instance_id', String(target.instanceId));
		const path = [target.mediaType, target.source, target.mediaId].map(encodeURIComponent).join('/');
		return `/api/v1/track/${path}/${query.size ? `?${query}` : ''}`;
	}

	$effect(() => {
		const path = apiPath();
		let live = true;
		fetch(path, { credentials: 'same-origin' })
			.then(async (response) => {
				if (!response.ok) throw new Error(String(response.status));
				const body = (await response.json()) as Screen;
				if (!live) return;
				screen = body;
				// The image URL is part of the General form, as on the page, though the Metadata tab shows it.
				const image = body.metadata?.image ? [body.metadata.image.field] : [];
				const all = [...body.hidden, ...body.fields, ...(body.notes ? [body.notes] : []), ...image];
				form = initialState(all, body.track_time, new Date(), !body.tracked);
				if (body.koreader) form = { ...form, values: { ...form.values, koreader_document_id: body.koreader.value } };
			})
			.catch((error: Error) => {
				if (live) loadError = error.message === '503' ? tt.trackProviderDown : tt.trackLoadFailed;
			});
		return () => {
			live = false;
		};
	});

	const runtime = $derived(screen?.date_suggestion.runtime_minutes ?? null);
	const value = (name: string) => form?.values[name] ?? '';

	function set(name: string, next: string) {
		if (!form) return;
		const before = form;
		if (name === 'status') form = settle(before, changeStatus(before, next, new Date()));
		else form = settle(before, { ...before, values: { ...before.values, [name]: next } });
	}

	function step(field: Field, by: number) {
		const current = Number(value(field.name) || 0);
		const size = Number(field.step || 1);
		let next = Math.round((current + by * size) * 1000) / 1000;
		if (field.min != null) next = Math.max(Number(field.min), next);
		if (field.max != null) next = Math.min(Number(field.max), next);
		set(field.name, String(next));
	}

	function dateAction(name: DateName, action: DateAction) {
		if (!form || !screen) return;
		const now = new Date();
		const before = form;
		let next: TrackState;
		if (action === 'start-now') next = startNow(before, name, runtime, now);
		else if (action === 'just-finished') next = justFinished(before, name, runtime, now);
		else if (action === 'release-date') next = releaseDate(before, name, screen.date_suggestion.date, runtime, now);
		else if (action === 'now') next = setDate(before, name, formatValue(now, before.trackTime));
		else if (action === 'copy') next = copyFromOther(before, name);
		else next = clearDate(before, name);
		form = settle(before, next);
	}

	async function post(url: string, extra: Record<string, string> = {}, kind: 'save' | 'delete' | 'rewatch' = 'save') {
		if (!form || busy) return;
		busy = true;
		problem = '';
		errors = {};
		try {
			const response = await djangoForm(url, { ...form.values, ...extra }, { json: true });
			const body = await response.json().catch(() => ({}));
			if (response.ok) {
				const warnings: string[] = body.warnings ?? [];
				const message = kind === 'delete' ? tt.trackDeleted : kind === 'rewatch' ? '' : (body.message ?? '');
				onsaved([message, ...warnings].filter(Boolean).join(' '));
				return;
			}
			if (body.errors) errors = body.errors;
			problem = body.error ?? (body.errors ? tt.trackFixErrors : tt.trackSaveFailed);
		} catch {
			problem = tt.trackSaveFailed;
		} finally {
			busy = false;
		}
	}
</script>

<Dialog.Root open onOpenChange={(open) => !open && onclose()}>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/70" />
		<Dialog.Content class="ct-track outline-none" aria-describedby={undefined}>
			<header class="ct-track__head">
				<div class="min-w-0">
					<Dialog.Title class="ct-track__title">{screen?.title ?? t.track}</Dialog.Title>
					{#if screen?.subtitle}<p class="ct-track__subtitle">{screen.subtitle}</p>{/if}
				</div>
				<Dialog.Close class="ct-track-icon" aria-label={t.close}>
					<X class="size-5" aria-hidden="true" />
				</Dialog.Close>
			</header>

			{#if (screen?.metadata || screen?.plays || screen?.collection || screen?.discover) && form && !loadError}
				<div class="ct-track__tabs" role="tablist">
					<button
						type="button"
						role="tab"
						class="ct-track__tab"
						aria-selected={tab === 'general'}
						onclick={() => (tab = 'general')}>{tt.general}</button
					>
					{#if screen.metadata}
						<button
							type="button"
							role="tab"
							class="ct-track__tab"
							aria-selected={tab === 'metadata'}
							onclick={() => (tab = 'metadata')}>{tt.metadata}</button
						>
					{/if}
					{#if screen.collection}
						<button
							type="button"
							role="tab"
							class="ct-track__tab"
							aria-selected={tab === 'collection'}
							onclick={() => (tab = 'collection')}>{tt.collection}</button
						>
					{/if}
					{#if screen.plays}
						<button
							type="button"
							role="tab"
							class="ct-track__tab"
							aria-selected={tab === 'plays'}
							onclick={() => (tab = 'plays')}>{screen.plays.tab_label}</button
						>
					{/if}
					{#if screen.discover}
						<button
							type="button"
							role="tab"
							class="ct-track__tab"
							aria-selected={tab === 'discover'}
							onclick={() => (tab = 'discover')}>{tt.discover}</button
						>
					{/if}
				</div>
			{/if}

			{#if loadError}
				<p class="ct-track__problem" role="alert">{loadError}</p>
			{:else if !screen || !form}
				<div class="ct-track__loading" aria-busy="true">{tt.loading}</div>
			{:else if tab === 'plays' && screen.plays}
				<PlaysTab plays={screen.plays} trackTime={screen.track_time} {onsaved} />
			{:else if tab === 'metadata' && screen.metadata}
				<MetadataTab metadata={screen.metadata} image={value('image_url')} onimage={(next) => set('image_url', next)} {onsaved} />
			{:else if tab === 'collection' && screen.collection}
				<CollectionTab collection={screen.collection} {onsaved} />
			{:else if tab === 'discover' && screen.discover}
				<DiscoverTab discover={screen.discover} {onsaved} />
			{:else}
				<form
					class="ct-track__form"
					novalidate
					onsubmit={(event) => {
						event.preventDefault();
						post(screen!.save_url);
					}}
				>
					<div class="ct-track__grid">
						{#each screen.fields as field (field.name)}
							{@const id = `track-${field.name}`}
							<div class={['ct-track__field', (field.kind === 'datetime' || field.kind === 'date' || field.name === 'progress') && 'is-wide']}>
								{#if field.kind === 'datetime' || field.kind === 'date'}
									{@const name = field.name as DateName}
									<DateField
										{id}
										label={field.label}
										value={value(field.name)}
										trackTime={field.kind === 'datetime'}
										releaseLabel={screen.date_suggestion.label}
										copyLabel={name === 'start_date' ? tt.end : tt.start}
										oninput={(next) => (form = settle(form!, setDate(form!, name, next)))}
										onaction={(action) => dateAction(name, action)}
									/>
								{:else}
									<label class="ct-track-label" for={id}>{field.label}</label>
									{#if field.kind === 'select'}
										<select {id} class="ct-track-input" value={value(field.name)} onchange={(e) => set(field.name, e.currentTarget.value)}>
											{#each field.choices as choice (choice.value)}
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
												max={field.max ?? undefined}
												step={field.step ?? undefined}
												placeholder={field.placeholder}
												value={value(field.name)}
												oninput={(e) => set(field.name, e.currentTarget.value)}
											/>
											<button type="button" class="ct-track-icon" aria-label={tt.decrease(field.label)} onclick={() => step(field, -1)}>
												<Minus class="size-4" aria-hidden="true" />
											</button>
											<button type="button" class="ct-track-icon" aria-label={tt.increase(field.label)} onclick={() => step(field, 1)}>
												<Plus class="size-4" aria-hidden="true" />
											</button>
										</div>
									{:else}
										<input {id} class="ct-track-input" type="text" placeholder={field.placeholder} value={value(field.name)} oninput={(e) => set(field.name, e.currentTarget.value)} />
									{/if}
								{/if}
								{#each errors[field.name] ?? [] as error (error)}
									<p class="ct-track__error">{error}</p>
								{/each}
							</div>
						{/each}
					</div>

					{#if screen.koreader}
						<div class="ct-track__field">
							<label class="ct-track-label" for="track-koreader">{tt.koreaderId}</label>
							<input
								id="track-koreader"
								class="ct-track-input font-mono"
								maxlength="32"
								autocapitalize="off"
								spellcheck="false"
								placeholder={tt.koreaderPlaceholder}
								value={value('koreader_document_id')}
								oninput={(e) => set('koreader_document_id', e.currentTarget.value)}
							/>
							<p class="ct-track__help">{tt.koreaderHelp}</p>
						</div>
					{/if}

					{#if screen.notes}
						<div class="ct-track__field">
							<label class="ct-track-label" for="track-notes">{tt.notes}</label>
							<textarea
								id="track-notes"
								class="ct-track-input"
								rows="4"
								placeholder={screen.notes.placeholder}
								value={value('notes')}
								oninput={(e) => set('notes', e.currentTarget.value)}
							></textarea>
						</div>
					{/if}

					{#each errors.__all__ ?? [] as error (error)}
						<p class="ct-track__error">{error}</p>
					{/each}
					{#if problem}<p class="ct-track__problem" role="alert">{problem}</p>{/if}

					<footer class="ct-track__actions">
						<div class="ct-track__actions-start">
							{#if screen.delete_url}
								<button type="button" class="ct-track-btn is-danger" disabled={busy} onclick={() => post(screen!.delete_url, {}, 'delete')}>{tt.delete}</button>
							{/if}
							{#if screen.rewatch}
								<button
									type="button"
									class="ct-track-btn"
									disabled={busy}
									onclick={() => post(screen!.rewatch!.url, { rewatch_started_at: rewatchSince }, 'rewatch')}
									>{screen.rewatch.label}</button
								>
								{#if screen.rewatch.action === 'start'}
									<label class="ct-track__since">
										{tt.since}
										<input type="date" class="ct-track-input" title={tt.sinceHelp} bind:value={rewatchSince} />
									</label>
								{:else if screen.rewatch.started_at}
									<span class="ct-track__since">{tt.rewatchingSince(new Date(screen.rewatch.started_at).toLocaleDateString())}</span>
								{/if}
							{/if}
						</div>
						<div class="ct-track__actions-end">
							{#if screen.save_as_new}
								<button type="button" class="ct-track-btn is-primary" disabled={busy} onclick={() => post(screen!.save_url, { save_as_new_entry: '1' })}>{screen.save_as_new}</button>
							{/if}
							<button type="submit" class="ct-track-btn is-primary" disabled={busy}>
								{screen.tracked ? tt.update : t.add}
							</button>
						</div>
					</footer>
				</form>
			{/if}
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
