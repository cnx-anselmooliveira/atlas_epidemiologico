/* =============================================================================
   Atlas DS · Painel — comportamentos (ES module, sem dependências)
   Tudo é melhoria progressiva: o HTML funciona sem este arquivo.
   Ativação por atributos data-ds-*; chame initDesignSystem() uma vez por página.

     data-ds-tooltip="texto"        tooltip acessível (hover, foco, toque)
     data-ds-sortable               tabela ordenável (no <table>)
     data-ds-autosubmit             envia o <form> ao mudar um campo
     data-ds-theme-toggle           botão que alterna claro/escuro
     data-ds-menu-toggle="#id"      abre/fecha o menu móvel
     data-ds-reveal-after="#id"     .ds-stickybar aparece quando #id sai da tela
     .ds-btn                        ondulação ao clicar (Painel)
   Cópia de frontend/design-system/status_invest/js/ds.js (cópia local de consulta, fora do Git).
   Para mudar: altere o original e copie de novo.
   ========================================================================== */

const THEME_KEY = "atlas-painel-theme";

/* ------------------------------------------------------------ Tema */
function safeGet(key) { try { return localStorage.getItem(key); } catch { return null; } }
function safeSet(key, value) { try { localStorage.setItem(key, value); } catch { /* sem storage: só não lembra */ } }

/** Aplica o tema salvo antes da primeira pintura. Chame inline no <head> para evitar flash. */
export function applySavedTheme() {
  const saved = safeGet(THEME_KEY);
  if (saved === "light" || saved === "dark") document.documentElement.dataset.theme = saved;
}

function currentTheme() {
  const explicit = document.documentElement.dataset.theme;
  if (explicit === "light" || explicit === "dark") return explicit;
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function initThemeToggle(root) {
  root.querySelectorAll("[data-ds-theme-toggle]").forEach((btn) => {
    const sync = () => {
      const dark = currentTheme() === "dark";
      btn.setAttribute("aria-pressed", String(dark));
      btn.setAttribute("aria-label", dark ? "Usar tema claro" : "Usar tema escuro");
    };
    sync();
    btn.addEventListener("click", () => {
      const next = currentTheme() === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      safeSet(THEME_KEY, next);
      sync();
      document.dispatchEvent(new CustomEvent("ds:themechange", { detail: { theme: next } }));
    });
  });
}

/* ------------------------------------------------------------ Tooltip */
let tooltipEl;
function ensureTooltip() {
  if (tooltipEl) return tooltipEl;
  tooltipEl = document.createElement("div");
  tooltipEl.className = "ds-tooltip";
  tooltipEl.id = "ds-tooltip";
  tooltipEl.setAttribute("role", "tooltip");
  document.body.appendChild(tooltipEl);
  return tooltipEl;
}

function placeTooltip(trigger) {
  const tip = ensureTooltip();
  const r = trigger.getBoundingClientRect();
  const t = tip.getBoundingClientRect();
  const margin = 8;
  let top = r.top - t.height - margin;
  if (top < margin) top = r.bottom + margin;               // sem espaço acima → abaixo
  let left = r.left + r.width / 2 - t.width / 2;
  left = Math.max(margin, Math.min(left, innerWidth - t.width - margin));
  tip.style.top = `${Math.round(top)}px`;
  tip.style.left = `${Math.round(left)}px`;
}

function showTooltip(trigger) {
  const tip = ensureTooltip();
  tip.textContent = trigger.getAttribute("data-ds-tooltip");
  trigger.setAttribute("aria-describedby", tip.id);
  tip.dataset.open = "true";
  placeTooltip(trigger);
}
function hideTooltip(trigger) {
  if (!tooltipEl) return;
  tooltipEl.dataset.open = "false";
  trigger?.removeAttribute("aria-describedby");
}

function initTooltips(root) {
  root.querySelectorAll("[data-ds-tooltip]").forEach((el) => {
    if (!el.hasAttribute("tabindex") && !/^(A|BUTTON|INPUT|SELECT)$/.test(el.tagName)) el.tabIndex = 0;
    el.addEventListener("mouseenter", () => showTooltip(el));
    el.addEventListener("mouseleave", () => hideTooltip(el));
    el.addEventListener("focus", () => showTooltip(el));
    el.addEventListener("blur", () => hideTooltip(el));
    el.addEventListener("keydown", (e) => { if (e.key === "Escape") hideTooltip(el); });
    el.addEventListener("click", (e) => {                   // toque em celular
      if (el.tagName !== "A") { e.preventDefault(); tooltipEl?.dataset.open === "true" ? hideTooltip(el) : showTooltip(el); }
    });
  });
  addEventListener("scroll", () => hideTooltip(), { passive: true });
}

/* ------------------------------------------------------------ Tabela ordenável */
const collator = new Intl.Collator("pt-BR", { numeric: true, sensitivity: "base" });

function cellValue(cell) {
  const raw = cell?.dataset.value ?? cell?.textContent.trim() ?? "";
  // Números pt-BR: "1.234,5" → 1234.5 ; "-12,3%" → -12.3
  const normalized = raw.replace(/\./g, "").replace(",", ".").replace(/[^\d.+-]/g, "");
  const n = Number(normalized);
  return raw !== "" && normalized !== "" && Number.isFinite(n) ? n : raw;
}

function initSortableTables(root) {
  root.querySelectorAll("table[data-ds-sortable]").forEach((table) => {
    const headers = [...table.tHead.rows[0].cells];
    headers.forEach((th, index) => {
      const btn = th.querySelector(".ds-table__sort");
      if (!btn) return;
      btn.addEventListener("click", () => {
        const dir = th.getAttribute("aria-sort") === "descending" ? "ascending" : "descending";
        headers.forEach((h) => h.removeAttribute("aria-sort"));
        th.setAttribute("aria-sort", dir);
        const body = table.tBodies[0];
        const rows = [...body.rows];
        rows.sort((a, b) => {
          const va = cellValue(a.cells[index]), vb = cellValue(b.cells[index]);
          const cmp = typeof va === "number" && typeof vb === "number" ? va - vb : collator.compare(String(va), String(vb));
          return dir === "ascending" ? cmp : -cmp;
        });
        body.append(...rows);
      });
    });
  });
}

/* ------------------------------------------------------------ Formulários */
function initAutosubmit(root) {
  root.querySelectorAll("form[data-ds-autosubmit]").forEach((form) => {
    form.addEventListener("change", () => form.requestSubmit());
    form.querySelectorAll("[data-ds-hide-when-enhanced]").forEach((el) => (el.hidden = true));
  });
}

/* ------------------------------------------------------------ Menu móvel */
function initMenuToggle(root) {
  root.querySelectorAll("[data-ds-menu-toggle]").forEach((btn) => {
    const menu = document.querySelector(btn.getAttribute("data-ds-menu-toggle"));
    if (!menu) return;
    btn.setAttribute("aria-controls", menu.id);
    btn.setAttribute("aria-expanded", "false");
    const set = (open) => { menu.hidden = !open; btn.setAttribute("aria-expanded", String(open)); };
    btn.addEventListener("click", () => set(menu.hidden));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !menu.hidden) { set(false); btn.focus(); } });
    matchMedia("(min-width: 900px)").addEventListener("change", (e) => e.matches && set(false));
  });
}

/* ------------------------------------------------------------ Barra fixa ao rolar */
function initStickyReveal(root) {
  root.querySelectorAll("[data-ds-reveal-after]").forEach((bar) => {
    const target = document.querySelector(bar.getAttribute("data-ds-reveal-after"));
    if (!target || !("IntersectionObserver" in window)) return;
    const io = new IntersectionObserver(([entry]) => {
      const revealed = !entry.isIntersecting && entry.boundingClientRect.top < 0;
      bar.dataset.revealed = String(revealed);
      bar.inert = !revealed;
    }, { rootMargin: `-${getComputedStyle(document.documentElement).getPropertyValue("--header-height").trim() || "64px"} 0px 0px 0px` });
    io.observe(target);
  });
}

/* ------------------------------------------------------------ Ondulação (Material) */
function initRipple(root) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  root.querySelectorAll(".ds-btn").forEach((btn) => {
    btn.addEventListener("pointerdown", (e) => {
      const r = btn.getBoundingClientRect();
      const size = Math.max(r.width, r.height);
      const wave = document.createElement("span");
      wave.className = "ds-ripple";
      wave.style.cssText = `width:${size}px;height:${size}px;left:${e.clientX - r.left - size / 2}px;top:${e.clientY - r.top - size / 2}px`;
      btn.appendChild(wave);
      wave.addEventListener("animationend", () => wave.remove());
    });
  });
}

/* ------------------------------------------------------------ Tokens para JS */
/** Lê um token CSS resolvido no tema atual, ex.: token("--viz-cat-1"). */
export function token(name, el = document.documentElement) {
  return getComputedStyle(el).getPropertyValue(name).trim();
}

/** Formatadores pt-BR usados em KPIs, tabelas e tooltips. */
export const fmt = {
  int: (n) => (n == null ? "—" : new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 }).format(n)),
  dec: (n, d = 1) => (n == null ? "—" : new Intl.NumberFormat("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d }).format(n)),
  compact: (n) => (n == null ? "—" : new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 }).format(n)),
  pct: (n, d = 1) => (n == null ? "—" : `${n > 0 ? "+" : ""}${new Intl.NumberFormat("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d }).format(n)}%`),
  rate: (n) => (n == null ? "—" : `${new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(n)} /100 mil`),
};

/** Classe de variação epidemiológica: subir casos é pior. */
export function deltaClass(pct, flatBand = 2) {
  if (pct == null || Math.abs(pct) < flatBand) return "ds-delta--flat";
  return pct > 0 ? "ds-delta--worse" : "ds-delta--better";
}

/* ------------------------------------------------------------ Init */
export function initDesignSystem(root = document) {
  initThemeToggle(root);
  initTooltips(root);
  initSortableTables(root);
  initAutosubmit(root);
  initMenuToggle(root);
  initStickyReveal(root);
  initRipple(root);
}
