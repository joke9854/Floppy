# Floppy web (v2)

The SvelteKit app that replaces Floppy's Django pages, one screen at a time
(`docs/plans/floppy-v2.md`, `docs/plans/p3-sveltekit-foundation.md`).

It runs its own Node server (adapter-node) inside the Floppy container,
listening on 127.0.0.1 only; nginx serves it under `/next/` until the cutover.
Django stays the only API.

```sh
npm ci
npm run dev      # http://localhost:5173/next
npm run check    # svelte-check
npm run test:unit -- --run
npm run build    # output in build/, started with: node build
```
