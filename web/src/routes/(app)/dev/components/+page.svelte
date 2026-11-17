<script lang="ts">
	import Button from '#lib/ui/Button.svelte';
	import Card from '#lib/ui/Card.svelte';
	import Dialog from '#lib/ui/Dialog.svelte';
	import Skeleton from '#lib/ui/Skeleton.svelte';
	import TextField from '#lib/ui/TextField.svelte';

	let dialog = $state(false);
	let sheet = $state(false);
	let text = $state('');
</script>

<main class="mx-auto flex max-w-3xl flex-col gap-8 px-5 pt-8 md:px-8">
	<h1 class="text-3xl font-bold tracking-tight">Components</h1>

	<section class="flex flex-wrap items-center gap-3">
		<Button variant="primary">Primary</Button>
		<Button>Secondary</Button>
		<Button variant="ghost">Ghost</Button>
		<Button size="sm">Small</Button>
		<Button disabled>Disabled</Button>
	</section>

	<Card class="flex flex-col gap-4">
		<h2 class="text-lg font-bold">Card</h2>
		<TextField label="Text field" placeholder="Type here" bind:value={text} />
		<TextField label="With an error" value="wrong" error="That is not right." />
	</Card>

	<section class="flex flex-col gap-3">
		<h2 class="text-lg font-bold">Loading</h2>
		<Skeleton class="h-5 w-2/3" />
		<Skeleton class="h-5 w-1/2" />
	</section>

	<section class="flex gap-3">
		<Button onclick={() => (dialog = true)}>Open dialog</Button>
		<Button onclick={() => (sheet = true)}>Open sheet</Button>
	</section>

	<div class="flex flex-wrap gap-2">
		{#each [['Watching', 'bg-ct-watching'], ['Planned', 'bg-ct-planned'], ['Paused', 'bg-ct-paused'], ['Completed', 'bg-ct-completed'], ['Dropped', 'bg-ct-dropped'], ['Accent', 'bg-accent']] as [label, color] (label)}
			<span class="rounded-full px-3 py-1 text-xs font-bold text-white {color}">{label}</span>
		{/each}
	</div>
</main>

<Dialog bind:open={dialog} title="A dialog" description="Escape or the backdrop closes it.">
	<div class="flex justify-end gap-3">
		<Button variant="ghost" onclick={() => (dialog = false)}>Cancel</Button>
		<Button variant="primary" onclick={() => (dialog = false)}>Done</Button>
	</div>
</Dialog>

<Dialog bind:open={sheet} title="A sheet" description="A bottom sheet on phones, a dialog from md." sheet>
	<Button variant="primary" onclick={() => (sheet = false)}>Close</Button>
</Dialog>
