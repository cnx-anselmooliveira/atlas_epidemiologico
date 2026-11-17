/* =============================================================================
   Atlas DS · Painel — tema do Apache ECharts gerado a partir dos tokens CSS.
   O tema é lido do CSS em runtime, então claro e escuro saem dos mesmos tokens.

   Uso (Astro, dentro do <script> de um componente):
     import * as echarts from "echarts/core";
     import { LineChart } from "echarts/charts";
     import { GridComponent, TooltipComponent } from "echarts/components";
     import { SVGRenderer } from "echarts/renderers";
     import { mountChart } from "../scripts/ds/echarts-theme.js";
     echarts.use([LineChart, GridComponent, TooltipComponent, SVGRenderer]);
     mountChart(echarts, figureEl.querySelector(".ds-figure__plot"), (t) => ({ ...option }));
   Cópia de frontend/design-system/status_invest/js/echarts-theme.js (cópia local de consulta, fora do Git).
   Para mudar: altere o original e copie de novo.
   ========================================================================== */

import { token } from "./ds.js";

const CAT = Array.from({ length: 8 }, (_, i) => `--viz-cat-${i + 1}`);

/** Lê os tokens do tema ativo e devolve as cores e fontes que os gráficos usam. */
export function readVizTokens() {
  const t = (n) => token(n);
  return {
    surface: t("--viz-surface"),
    ink1: t("--viz-ink-1"),
    ink2: t("--viz-ink-2"),
    muted: t("--viz-muted"),
    grid: t("--viz-grid"),
    axis: t("--viz-axis"),
    nodata: t("--viz-nodata"),
    other: t("--viz-other"),
    categorical: CAT.map(t),
    mapClasses: ["--viz-map-1", "--viz-map-2", "--viz-map-3", "--viz-map-4", "--viz-map-5", "--viz-map-6"].map(t),
    sequential: ["--incid-100", "--incid-200", "--incid-300", "--incid-400", "--incid-500", "--incid-600", "--incid-700", "--incid-800", "--incid-900"].map(t),
    diverging: {
      better: ["--cool-700", "--cool-500", "--cool-300"].map(t),
      mid: t("--viz-diverging-mid"),
      worse: ["--incid-300", "--incid-500", "--incid-700"].map(t),
    },
    status: {
      green: t("--status-good"), yellow: t("--status-warning"), orange: t("--status-serious"),
      red: t("--status-critical"), insufficient_history: t("--status-none"),
    },
    font: t("--font-sans") || "IBM Plex Sans, sans-serif",
    tooltipBg: t("--text-1"),
    tooltipText: t("--surface-card"),
  };
}

/** Objeto de tema do ECharts (registerTheme). Marcas finas, grade recessiva, sem eixo duplo. */
export function buildTheme(v = readVizTokens()) {
  const axisCommon = {
    axisLine: { show: true, lineStyle: { color: v.axis, width: 1 } },
    axisTick: { show: false },
    axisLabel: { color: v.muted, fontSize: 11, fontFamily: v.font },
    splitLine: { show: true, lineStyle: { color: v.grid, width: 1 } },
    nameTextStyle: { color: v.muted, fontSize: 11 },
  };
  return {
    color: v.categorical,
    backgroundColor: "transparent",
    textStyle: { fontFamily: v.font, color: v.ink2, fontSize: 12 },
    title: { textStyle: { color: v.ink1, fontWeight: 600, fontSize: 14 }, subtextStyle: { color: v.muted } },
    grid: { left: 8, right: 16, top: 24, bottom: 8, containLabel: true },
    categoryAxis: { ...axisCommon, splitLine: { show: false } },
    valueAxis: { ...axisCommon, axisLine: { show: false } },
    timeAxis: { ...axisCommon, splitLine: { show: false } },
    line: { lineStyle: { width: 2 }, symbol: "circle", symbolSize: 8, showSymbol: false, smooth: false, emphasis: { focus: "series", lineStyle: { width: 2.5 } } },
    bar: { itemStyle: { borderRadius: [4, 4, 0, 0] }, barMaxWidth: 28, barCategoryGap: "30%" },
    legend: { show: false }, /* a legenda é HTML (.ds-legend), fora do canvas */
    tooltip: {
      trigger: "axis",
      backgroundColor: v.tooltipBg,
      borderWidth: 0,
      padding: [8, 12],
      textStyle: { color: v.tooltipText, fontFamily: v.font, fontSize: 12 },
      extraCssText: "border-radius:6px;box-shadow:0 12px 32px rgb(22 29 39 / .16);",
      axisPointer: { type: "line", lineStyle: { color: v.axis, width: 1, type: "dashed" } },
    },
    /* Coroplético: use visualMap "piecewise" com as 6 classes fixas (DATAVIZ.md §2). */
    visualMap: { inRange: { color: v.mapClasses }, outOfRange: { color: v.nodata }, textStyle: { color: v.muted }, itemWidth: 10, itemHeight: 120 },
    geo: {
      itemStyle: { areaColor: v.nodata, borderColor: v.surface, borderWidth: 1 },
      emphasis: { itemStyle: { areaColor: v.nodata, borderColor: v.ink1, borderWidth: 1.5 }, label: { show: false } },
      select: { disabled: true },
    },
    map: {
      itemStyle: { areaColor: v.nodata, borderColor: v.surface, borderWidth: 1 },
      emphasis: { itemStyle: { borderColor: v.ink1, borderWidth: 1.5 }, label: { show: false } },
      select: { disabled: true },
    },
  };
}

/** Linhas do tooltip no padrão .ds-chart-tooltip (marcador + rótulo + valor tabular). */
export function tooltipHTML(title, rows) {
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  return `<div class="ds-chart-tooltip"><div class="ds-chart-tooltip__title">${esc(title)}</div>${rows
    .map((r) => `<div class="ds-chart-tooltip__row"><span style="width:10px;height:${r.line ? 2 : 10}px;border-radius:2px;background:${r.color}"></span><span>${esc(r.label)}</span><b>${esc(r.value)}</b></div>`)
    .join("")}</div>`;
}

/** Com o gráfico montado, a tabela-fallback vira um <details> "Ver dados" (continua acessível). */
function moveFallbackToDetails(figure) {
  const fallback = figure?.querySelector(".ds-figure__fallback");
  if (!fallback || fallback.dataset.moved) return;
  const details = document.createElement("details");
  details.className = "ds-figure__data";
  details.innerHTML = '<summary>Ver dados em tabela</summary>';
  details.append(...fallback.childNodes);
  fallback.dataset.moved = "true";
  fallback.after(details);
}

/**
 * Monta um gráfico ligado ao tema: re-renderiza na troca claro/escuro e
 * redimensiona com o contêiner. Marca a <figure> como data-enhanced para
 * esconder a tabela-fallback. Devolve a instância (ou null se falhar).
 */
export function mountChart(echarts, el, buildOption, { renderer = "svg" } = {}) {
  if (!el) return null;
  const figure = el.closest(".ds-figure");
  let chart;
  const render = () => {
    const v = readVizTokens();
    const themeName = `atlas-${document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")}`;
    echarts.registerTheme(themeName, buildTheme(v));
    chart?.dispose();
    chart = echarts.init(el, themeName, { renderer, locale: "PT" in (echarts.locales ?? {}) ? "PT" : undefined });
    chart.setOption(buildOption(v));
  };
  try {
    if (figure) figure.dataset.enhanced = "true"; // mostra o plot antes de medir
    render();
    moveFallbackToDetails(figure);
  } catch (err) {
    if (figure) figure.dataset.enhanced = "false"; // volta para a tabela
    console.error("[atlas-ds] gráfico não montado", err);
    return null;
  }
  new ResizeObserver(() => chart?.resize()).observe(el);
  document.addEventListener("ds:themechange", render);
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", render);
  return { get instance() { return chart; } };
}
