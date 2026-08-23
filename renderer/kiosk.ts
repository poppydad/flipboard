/**
 * Fullscreen and cursor-hiding for the kiosk display. Cursor hiding is pure
 * CSS (see display.html); fullscreen needs a user gesture per browser
 * autoplay/fullscreen policy, so it rides the same first-interaction hook
 * as the audio context unlock.
 */
export function enableKiosk(): void {
  const goFullscreen = () => {
    document.documentElement.requestFullscreen?.().catch(() => {
      // Kiosk Chromium is typically launched with --kiosk already, making
      // this a no-op there; failures elsewhere just mean windowed mode.
    });
    window.removeEventListener("pointerdown", goFullscreen);
    window.removeEventListener("keydown", goFullscreen);
  };
  window.addEventListener("pointerdown", goFullscreen);
  window.addEventListener("keydown", goFullscreen);
}
