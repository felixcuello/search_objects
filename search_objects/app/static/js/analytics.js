// Analytics dashboard: polls /analytics/data and redraws only when the numbers change.
(() => {
  const POLL_MS = 2000;
  const COLORS = {
    text: "#e8e9f1",
    muted: "#8d90a6",
    grid: "rgba(141, 144, 166, 0.15)",
    purple: "#a78bfa",
    blue: "#60a5fa",
    teal: "#2dd4bf",
    amber: "#fbbf24",
  };

  Chart.defaults.color = COLORS.muted;
  Chart.defaults.font.family = "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
  Chart.defaults.borderColor = COLORS.grid;

  const live = document.querySelector("[data-live]");
  const liveText = document.querySelector("[data-live-text]");

  // Draws the count at the end of each horizontal bar, so the exact number is always visible.
  const valueLabels = {
    id: "valueLabels",
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      ctx.save();
      ctx.fillStyle = COLORS.text;
      ctx.font = "600 12px " + Chart.defaults.font.family;
      ctx.textBaseline = "middle";
      chart.getDatasetMeta(0).data.forEach((bar, index) => {
        ctx.fillText(String(chart.data.datasets[0].data[index]), bar.x + 8, bar.y);
      });
      ctx.restore();
    },
  };

  // Chart.js gives the label axis at most half of the chart, so the longest label depends on width.
  const PIXELS_PER_LABEL_CHARACTER = 17;
  const MIN_LABEL_LENGTH = 10;
  function shortLabel(value) {
    const label = this.getLabelForValue(value);
    const maxLength = Math.max(MIN_LABEL_LENGTH, Math.floor(this.chart.width / PIXELS_PER_LABEL_CHARACTER));
    return label.length > maxLength ? label.slice(0, maxLength - 1) + "…" : label;
  }

  function buildRankingChart(name, color) {
    return new Chart(document.querySelector(`[data-chart="${name}"]`), {
      type: "bar",
      data: { labels: [], datasets: [{ data: [], backgroundColor: color, borderRadius: 4, maxBarThickness: 22 }] },
      options: {
        indexAxis: "y",
        maintainAspectRatio: false,
        layout: { padding: { right: 34 } },
        plugins: { legend: { display: false } },
        scales: {
          x: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: COLORS.grid } },
          // Long product names are cut at the end here; the tooltip still shows the full name.
          y: { grid: { display: false }, ticks: { color: COLORS.text, callback: shortLabel } },
        },
      },
      plugins: [valueLabels],
    });
  }

  function formatMinute(isoMinute) {
    return new Date(isoMinute).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function lineDataset(label, color) {
    return {
      label,
      data: [],
      borderColor: color,
      backgroundColor: color + "26",
      fill: true,
      // Monotone smoothing never dips below zero between two points, unlike a plain tension.
      cubicInterpolationMode: "monotone",
      pointRadius: 0,
      pointHoverRadius: 4,
      borderWidth: 2,
    };
  }

  const charts = {
    timeline: new Chart(document.querySelector('[data-chart="timeline"]'), {
      type: "line",
      data: {
        labels: [],
        datasets: [lineDataset("Fotos enviadas", COLORS.purple), lineDataset("Reemplazos", COLORS.teal)],
      },
      options: {
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } } },
        scales: {
          x: { grid: { display: false }, ticks: { maxTicksLimit: 7, maxRotation: 0 } },
          y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: COLORS.grid } },
        },
      },
    }),
    detected: buildRankingChart("detected", COLORS.blue),
    replaced: buildRankingChart("replaced", COLORS.teal),
    products: buildRankingChart("products", COLORS.amber),
  };

  // Counters count up to the new value, and the number briefly turns purple when it grows.
  const shown = new Map();
  function setKpi(name, target, decimals = 0) {
    const node = document.querySelector(`[data-kpi="${name}"]`);
    const from = shown.get(name) ?? 0;
    shown.set(name, target);
    if (from === target) {
      node.textContent = target.toFixed(decimals);
      return;
    }
    if (target > from) {
      node.classList.add("is-bumped");
      setTimeout(() => node.classList.remove("is-bumped"), 900);
    }
    const start = performance.now();
    const duration = 600;
    function frame(now) {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      node.textContent = (from + (target - from) * eased).toFixed(decimals);
      if (progress < 1 && shown.get(name) === target) {
        requestAnimationFrame(frame);
      } else {
        node.textContent = shown.get(name).toFixed(decimals);
      }
    }
    requestAnimationFrame(frame);
  }

  function setRanking(chartName, rows) {
    const chart = charts[chartName];
    chart.data.labels = rows.map((row) => row.name);
    chart.data.datasets[0].data = rows.map((row) => row.total);
    chart.update();
    const isEmpty = rows.length === 0;
    document.querySelector(`[data-empty="${chartName}"]`).hidden = !isEmpty;
    document.querySelector(`[data-chart="${chartName}"]`).parentElement.hidden = isEmpty;
  }

  function render(snapshot) {
    const { totals, timeline } = snapshot;
    setKpi("photos", totals.photos);
    setKpi("uploads", totals.uploads);
    setKpi("samples", totals.samples);
    setKpi("detected_objects", totals.detected_objects);
    setKpi("replacements", totals.replacements);
    setKpi("objects_per_upload", totals.uploads ? totals.detected_objects / totals.uploads : 0, 1);

    charts.timeline.data.labels = timeline.minutes.map(formatMinute);
    charts.timeline.data.datasets[0].data = timeline.photos;
    charts.timeline.data.datasets[1].data = timeline.replacements;
    charts.timeline.update();

    setRanking("detected", snapshot.top_detected);
    setRanking("replaced", snapshot.top_replaced);
    setRanking("products", snapshot.top_products);
  }

  let lastBody = null;
  let lastOkAt = null;
  let timer = null;
  let inFlight = false;

  function showStatus() {
    if (lastOkAt === null) {
      return;
    }
    const seconds = Math.round((Date.now() - lastOkAt) / 1000);
    liveText.textContent = seconds < 2 ? "En vivo · actualizado ahora" : `En vivo · actualizado hace ${seconds}s`;
  }

  async function poll() {
    clearTimeout(timer);
    if (!inFlight && !document.hidden) {
      inFlight = true;
      try {
        const response = await fetch("/analytics/data", { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`status ${response.status}`);
        }
        const body = await response.text();
        // Redrawing only on change keeps the charts still while nobody is using the app.
        if (body !== lastBody) {
          lastBody = body;
          render(JSON.parse(body));
        }
        lastOkAt = Date.now();
        live.classList.add("is-live");
        live.classList.remove("is-offline");
        showStatus();
      } catch {
        live.classList.remove("is-live");
        live.classList.add("is-offline");
        liveText.textContent = "Sin conexión · reintentando…";
      } finally {
        inFlight = false;
      }
    }
    timer = setTimeout(poll, POLL_MS);
  }

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      poll();
    }
  });
  setInterval(showStatus, 1000);
  poll();
})();
