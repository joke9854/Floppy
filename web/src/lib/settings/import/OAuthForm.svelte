<script lang="ts">
	import { csrfToken } from '#lib/csrf.ts';
	import { BASE } from '#lib/paths.ts';
	import { st } from '../strings.ts';

	/**
	 * A real form submit that leaves for a provider's sign-in (Simkl, Trakt and
	 * AniList OAuth). The page's Import Settings travel as hidden fields and
	 * `next` brings the user back to the web Import page.
	 */
	let {
		action,
		button,
		disabled = false,
		note = '',
		frequency,
		time,
		mode
	}: { action: string; button: string; disabled?: boolean; note?: string; frequency: string; time: string; mode: string } = $props();

	let form = $state<HTMLFormElement>();
	let token = $state('');
	let busy = $state(false);
	let failed = $state(false);

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		if (busy) return;
		busy = true;
		failed = false;
		try {
			token = await csrfToken();
			form?.submit();
		} catch {
			failed = true;
			busy = false;
		}
	}
</script>

<form bind:this={form} method="post" {action} onsubmit={submit}>
	<input type="hidden" name="frequency" value={frequency} />
	<input type="hidden" name="time" value={time} />
	<input type="hidden" name="mode" value={mode} />
	<input type="hidden" name="next" value={`${BASE}/settings/import`} />
	<input type="hidden" name="csrfmiddlewaretoken" value={token} />
	<button type="submit" class="ct-settings-button is-primary" disabled={busy || disabled}>{button}</button>
	{#if note}<p class="ct-settings-note">{note}</p>{/if}
	{#if failed}<p class="ct-settings-status is-error" role="status">{st.failed}</p>{/if}
</form>
