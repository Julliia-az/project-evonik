document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-copy-target]");
  if (!b) return;
  const el = document.getElementById(b.dataset.copyTarget);
  if (!el) return;
  try {
    await navigator.clipboard.writeText(el.value);
    b.textContent = "Copiado";
    setTimeout(() => (b.textContent = "Copiar"), 1600);
  } catch {
    el.select();
    document.execCommand("copy");
    b.textContent = "Copiado";
  }
});
