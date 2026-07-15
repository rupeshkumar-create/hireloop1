(() => {
  const slides = [...document.querySelectorAll(".slide")];
  if (!slides.length) return;

  let i = Math.max(
    0,
    Math.min(slides.length - 1, Number(location.hash.replace("#", "")) - 1 || 0)
  );

  const counter = document.getElementById("slide-counter");
  const bar = document.getElementById("progress-bar");
  const titleEl = document.getElementById("deck-title");

  function show(n) {
    i = Math.max(0, Math.min(slides.length - 1, n));
    slides.forEach((s, idx) => s.classList.toggle("active", idx === i));
    if (counter) counter.textContent = `${i + 1} / ${slides.length}`;
    if (bar) bar.style.width = `${((i + 1) / slides.length) * 100}%`;
    history.replaceState(null, "", `#${i + 1}`);
    document.title = titleEl
      ? `${titleEl.textContent} · ${i + 1}/${slides.length}`
      : document.title;
  }

  document.getElementById("prev")?.addEventListener("click", () => show(i - 1));
  document.getElementById("next")?.addEventListener("click", () => show(i + 1));

  window.addEventListener("keydown", (e) => {
    if (["ArrowRight", "PageDown", " ", "Enter"].includes(e.key)) {
      e.preventDefault();
      show(i + 1);
    } else if (["ArrowLeft", "PageUp", "Backspace"].includes(e.key)) {
      e.preventDefault();
      show(i - 1);
    } else if (e.key === "Home") {
      show(0);
    } else if (e.key === "End") {
      show(slides.length - 1);
    } else if (e.key === "f" || e.key === "F") {
      if (!document.fullscreenElement) document.documentElement.requestFullscreen?.();
      else document.exitFullscreen?.();
    }
  });

  let touchX = null;
  window.addEventListener(
    "touchstart",
    (e) => {
      touchX = e.changedTouches[0].clientX;
    },
    { passive: true }
  );
  window.addEventListener(
    "touchend",
    (e) => {
      if (touchX == null) return;
      const dx = e.changedTouches[0].clientX - touchX;
      if (Math.abs(dx) > 50) show(i + (dx < 0 ? 1 : -1));
      touchX = null;
    },
    { passive: true }
  );

  show(i);
})();
