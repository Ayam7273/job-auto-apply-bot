# Nadios Homes — Modern Scrollbar Prompt

**Purpose:** Paste into your IDE coding assistant, pointed at the current repo, to replace the default browser scrollbar with a slim, branded one. Vanilla CSS (+ a few lines of JS only if adding the optional scroll-progress variant below). No frameworks.

---

## 1. What "default" looks like vs. what to build

Right now the scrollbar is whatever the OS/browser renders by default — thick, grey, disconnected from the brand. Replace it with a slim custom track/thumb styled using the site's own color tokens, consistent across Chrome/Edge/Safari (WebKit) and Firefox.

## 2. Core CSS (cross-browser)

```css
/* Firefox */
html {
  scrollbar-width: thin;
  scrollbar-color: var(--nadios-scroll-thumb, currentColor) transparent;
}

/* WebKit: Chrome, Edge, Safari */
::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background-color: var(--nadios-scroll-thumb, rgba(0, 0, 0, 0.3));
  border-radius: 999px;
  border: 2px solid var(--nadios-scroll-track, transparent);
  background-clip: padding-box;
}

::-webkit-scrollbar-thumb:hover {
  background-color: var(--nadios-scroll-thumb-hover, rgba(0, 0, 0, 0.5));
}
```

- Use the site's **existing** brand/accent CSS variables for `--nadios-scroll-thumb` (don't hardcode a new color) — pull from whatever the current accent variable is named in the stylesheet.
- Keep the track transparent so it just shows the page background underneath rather than adding a visible boxed channel — that's what reads as "modern" vs. the default chunky grey groove.
- `border: 2px solid transparent` + `background-clip: padding-box` gives the thumb a bit of inset padding so it doesn't touch the very edge of the viewport — a small detail that makes it look designed rather than default-but-recolored.

## 3. Dark/light section awareness (optional but recommended)

Since the homepage already alternates dark (`--nadios-ink`) and light (`--nadios-paper`) full-bleed sections, the scrollbar thumb color should have enough contrast against whichever section is currently in view. Two ways to handle it, pick one:

- **Simple:** pick a single mid-tone accent color (e.g. the brass/gold accent) that reads fine against both dark and light backgrounds, and use it everywhere — least code, still looks intentional.
- **Adaptive:** use an IntersectionObserver on your dark-background sections to toggle a `data-scroll-theme="dark"` attribute on `<html>`, then swap `--nadios-scroll-thumb` between two values via a CSS attribute selector. Only worth doing if the flat single-accent version genuinely looks wrong against one of the two backgrounds when you check it live.

## 4. Optional: scroll-progress indicator instead of / in addition to a styled thumb

If you want something more distinctive than just a recolored native scrollbar, add a **slim fixed progress bar** at the very top (or one edge) of the viewport that fills left-to-right as the visitor scrolls down the page — common on editorial/portfolio sites and reads as more custom than a styled native bar.

```html
<div id="scroll-progress" class="scroll-progress"></div>
```

```css
.scroll-progress {
  position: fixed;
  top: 0;
  left: 0;
  height: 3px;
  width: 0%;
  background: var(--nadios-brass, currentColor);
  z-index: 10000;
  transition: width 0.1s linear;
}
```

```js
(function () {
  const bar = document.getElementById('scroll-progress');
  function updateProgress() {
    const scrollTop = window.scrollY;
    const docHeight = document.documentElement.scrollHeight - window.innerHeight;
    const percent = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;
    bar.style.width = percent + '%';
  }
  window.addEventListener('scroll', updateProgress, { passive: true });
  updateProgress();
})();
```

- If you add this, you can either keep the styled native scrollbar alongside it (belt-and-braces, both look intentional) or hide the native scrollbar entirely (`::-webkit-scrollbar { display: none; }` + `scrollbar-width: none;` on Firefox) and let this top bar be the only scroll indicator — pick whichever matches how minimal you want the chrome to feel.

## 5. Accessibility notes

- Don't drop the scrollbar below a usable click/drag width on desktop — 8–10px is the sweet spot; thinner than that becomes hard to grab with a mouse.
- If hiding the native scrollbar in favor of the progress bar (section 4), make sure keyboard scrolling (Page Down, arrow keys, spacebar) and screen-reader navigation still work normally — this CSS only affects the visual scrollbar, not actual scroll functionality, so this should hold true by default, but worth a quick check.
- Test on an actual trackpad/touch device too — mobile browsers already hide scrollbars by default, so this change is primarily a desktop-facing detail.

---

**How to use this:** Paste this file into your coding assistant along with your main stylesheet, and ask it to wire in section 2 using your actual existing CSS variable names, then decide together whether to add the optional progress bar from section 4.
