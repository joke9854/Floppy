<script lang="ts">
	import { tt } from './strings.ts';

	export type Pick = { key: string; title: string; image: string | null; lines: string[]; selected: boolean };
	type Hit =
		| { media_id: string; title: string; image: string | null; year: string }
		| { value: string; title: string; image: string | null; lines: string[]; selected: boolean };

	/**
	 * The Metadata tab's search pickers (P4-D6b): the page's remap, library
	 * move, Hardcover edition and MusicBrainz release searches, which load
	 * their results as you type (the move, edition and release lists also
	 * on focus, with an empty search listing everything).
	 */
	let {
		url,
		label,
		placeholder,
		onFocus = false,
		busy = false,
		pickLabel,
		onpick
	}: {
		url: string;
		label: string;
		placeholder: string;
		onFocus?: boolean;
		busy?: boolean;
		pickLabel: (title: string) => string;
		onpick: (key: string) => void;
	} = $props();

	let query = $state('');
	let results = $state.raw<Pick[] | null>(null);
	let loading = $state(false);
	let failed = $state(false);
	let timer: ReturnType<typeof setTimeout> | undefined;
	let latest = 0;

	function normalize(hit: Hit): Pick {
		if ('media_id' in hit)
			return { key: hit.media_id, title: hit.title, image: hit.image, lines: hit.year ? [hit.year] : [], selected: false };
		return { key: hit.value, title: hit.title, image: hit.image, lines: hit.lines, selected: hit.selected };
	}

	async function load(q: string) {
		const ticket = ++latest;
		loading = true;
		failed = false;
		try {
			const separator = url.includes('?') ? '&' : '?';
			const response = await fetch(`${url}${separator}q=${encodeURIComponent(q)}`, {
				credentials: 'same-origin',
				headers: { accept: 'application/json' }
			});
			if (!response.ok) throw new Error(String(response.status));
			const body = (await response.json()) as { results: Hit[] };
			if (ticket === latest) results = body.results.map(normalize);
		} catch {
			if (ticket === latest) failed = true;
		} finally {
			if (ticket === latest) loading = false;
		}
	}

	function typed(next: string) {
		query = next;
		clearTimeout(timer);
		if (!onFocus && !next.trim()) {
			results = null;
			return;
		}
		timer = setTimeout(() => load(next.trim()), onFocus ? 250 : 400);
	}
</script>

<div class="ct-picker">
	<div class="ct-picker__field">
		<input
			class="ct-track-input"
			type="search"
			aria-label={label}
			{placeholder}
			autocomplete="off"
			value={query}
			oninput={(e) => typed(e.currentTarget.value)}
			onfocus={() => onFocus && results === null && load(query.trim())}
			onkeydown={(e) => {
				if (e.key === 'Enter') {
					e.preventDefault();
					clearTimeout(timer);
					load(query.trim());
				}
			}}
		/>
	</div>
	{#if loading}
		<p class="ct-track__help" aria-live="polite">…</p>
	{:else if failed}
		<p class="ct-track__problem" role="alert">{tt.searchFailed}</p>
	{:else if results && results.length === 0 && (onFocus || query.trim())}
		<p class="ct-track__help">{tt.noMatches}</p>
	{/if}
	{#if results?.length}
		<ul class="ct-picker__results">
			{#each results as result, i (i)}
				<li>
					<button
						type="button"
						class={['ct-picker__result', result.selected && 'is-selected']}
						aria-label={pickLabel(result.title)}
						aria-current={result.selected ? 'true' : undefined}
						disabled={busy}
						onclick={() => onpick(result.key)}
					>
						{#if result.image}
							<img src={result.image} alt="" loading="lazy" class="ct-picker__image" />
						{:else}
							<span class="ct-picker__image" aria-hidden="true"></span>
						{/if}
						<span class="min-w-0 flex-1">
							<span class="ct-picker__title">{result.title}</span>
							{#each result.lines as line, l (l)}
								<span class="ct-picker__line">{line}</span>
							{/each}
						</span>
					</button>
				</li>
			{/each}
		</ul>
	{/if}
</div>
