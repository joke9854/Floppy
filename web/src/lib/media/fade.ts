/** Fade a poster in once it has decoded (M7); load and error both reveal it. */
export function fadeIn(img: HTMLImageElement) {
	const reveal = () => img.classList.add('is-loaded');
	if (img.complete) {
		reveal();
		return;
	}
	img.addEventListener('load', reveal, { once: true });
	img.addEventListener('error', reveal, { once: true });
	return {
		destroy() {
			img.removeEventListener('load', reveal);
			img.removeEventListener('error', reveal);
		}
	};
}
