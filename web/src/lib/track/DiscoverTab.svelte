<script lang="ts">
	import type { components } from '#lib/api/client.ts';
	import { djangoForm } from '#lib/csrf.ts';
	import { tt } from './strings.ts';

	type Discover = components['schemas']['TrackDiscover'];

	/**
	 * The Discover tab (P4-D4), as the Django dialog's
	 * discover_tab_content.html: whether Discover recommends this title.
	 * Save is off until the choice differs from the saved one.
	 */
	let { discover, onsaved }: { discover: Discover; onsaved: (message: string) => void } = $props();

	// svelte-ignore state_referenced_locally
	let hidden = $state(discover.hidden);
	let busy = $state(false);
	let problem = $state('');

	async function save() {
		if (busy || hidden === discover.hidden) return;
		busy = true;
		problem = '';
		try {
			const response = await djangoForm(
				discover.save_url,
				{ item_id: String(discover.item_id), action: hidden ? 'hide' : 'unhide' },
				{ json: true }
			);
			const body = await response.json().catch(() => ({}));
			if (response.ok) onsaved(body.message ?? '');
			else problem = tt.trackSaveFailed;
		} catch {
			problem = tt.trackSaveFailed;
		} finally {
			busy = false;
		}
	}
</script>

<form
	class="ct-track__form"
	novalidate
	onsubmit={(event) => {
		event.preventDefault();
		save();
	}}
>
	<div>
		<h3 class="ct-discover__title">{tt.discoverVisibility}</h3>
		<p class="ct-track__help">{tt.discoverHelp}</p>
	</div>
	<div class="ct-discover__box">
		<div class="ct-discover__row">
			<label class="ct-track-label" for="track-discover">{tt.status}</label>
			<span class="ct-track__help">{discover.hidden ? tt.currentlyHidden : tt.currentlyVisible}</span>
		</div>
		<select
			id="track-discover"
			class="ct-track-input"
			value={hidden ? 'hidden' : 'visible'}
			onchange={(e) => (hidden = e.currentTarget.value === 'hidden')}
		>
			<option value="visible">{tt.visible}</option>
			<option value="hidden">{tt.hidden}</option>
		</select>
	</div>
	{#if problem}<p class="ct-track__problem" role="alert">{problem}</p>{/if}
	<div class="ct-track__actions">
		<div class="ct-track__actions-end">
			<button type="submit" class="ct-track-btn is-primary" disabled={busy || hidden === discover.hidden}>
				{tt.save}
			</button>
		</div>
	</div>
</form>
