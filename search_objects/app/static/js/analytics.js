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

  // Slice colors for the products doughnut; the last one is reserved for "Otros".
  const DONUT_COLORS = [
    "#fbbf24", "#60a5fa", "#2dd4bf", "#a78bfa", "#f472b6",
    "#fb923c", "#34d399", "#818cf8", "#f87171", "#a3e635",
  ];
  const OTHERS_COLOR = "#4b4f66";
  const OTHERS_LABEL = "Otros";
  const WIDE_CHART_PIXELS = 480;

  function truncate(text, maxLength) {
    return text.length > maxLength ? text.slice(0, maxLength - 1) + "…" : text;
  }

  // Writes the total of replacements in the hole of the doughnut.
  const centerTotal = {
    id: "centerTotal",
    afterDatasetsDraw(chart) {
      const arc = chart.getDatasetMeta(0).data[0];
      if (!arc) {
        return;
      }
      const { ctx } = chart;
      ctx.save();
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = COLORS.text;
      ctx.font = "700 28px " + Chart.defaults.font.family;
      ctx.fillText(String(chart.data.datasets[0].data.reduce((sum, value) => sum + value, 0)), arc.x, arc.y - 8);
      ctx.fillStyle = COLORS.muted;
      ctx.font = "12px " + Chart.defaults.font.family;
      ctx.fillText("reemplazos", arc.x, arc.y + 14);
      ctx.restore();
    },
  };

  function buildProductsDoughnut() {
    return new Chart(document.querySelector('[data-chart="products"]'), {
      type: "doughnut",
      data: { labels: [], datasets: [{ data: [], backgroundColor: [], borderColor: "#1b1c27", borderWidth: 2, hoverOffset: 6 }] },
      options: {
        maintainAspectRatio: false,
        cutout: "62%",
        // A wide card has room for the legend on the right; a narrow one puts it below.
        onResize(chart, size) {
          const position = size.width >= WIDE_CHART_PIXELS ? "right" : "bottom";
          if (chart.options.plugins.legend.position !== position) {
            chart.options.plugins.legend.position = position;
            chart.update("none");
          }
        },
        plugins: {
          legend: {
            position: "right",
            labels: {
              color: COLORS.text,
              usePointStyle: true,
              boxWidth: 8,
              generateLabels(chart) {
                const base = Chart.overrides.doughnut.plugins.legend.labels.generateLabels(chart);
                const maxLength = Math.max(12, Math.floor(chart.width / (chart.options.plugins.legend.position === "right" ? 14 : 9)));
                return base.map((item) => ({
                  ...item,
                  text: `${truncate(item.text, maxLength)}  ${chart.data.datasets[0].data[item.index]}`,
                }));
              },
            },
          },
          tooltip: {
            callbacks: {
              title: () => "",
              label(item) {
                const total = item.dataset.data.reduce((sum, value) => sum + value, 0);
                const percent = total ? Math.round((item.parsed / total) * 100) : 0;
                return ` ${item.label}: ${item.parsed} (${percent}%)`;
              },
            },
          },
        },
      },
      plugins: [centerTotal],
    });
  }

  const RANGE_NAMES = {
    "15m": "Últimos 15 minutos",
    "1h": "Última hora",
    "2h": "Últimas 2 horas",
    "1d": "Último día",
    "1w": "Última semana",
    "1mo": "Último mes",
  };
  const MINUTES_PER_DAY = 1440;
  const MAX_CUSTOM_DAYS = 400;

  // Bucket start times of the chart as full local dates, shown in the tooltip title.
  let bucketTitles = [];

  function formatBucketLabel(isoStart, spanMinutes, bucketMinutes) {
    const date = new Date(isoStart);
    if (bucketMinutes >= MINUTES_PER_DAY) {
      return date.toLocaleDateString([], { day: "2-digit", month: "2-digit" });
    }
    const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    if (spanMinutes <= MINUTES_PER_DAY) {
      return time;
    }
    return `${date.toLocaleDateString([], { day: "2-digit", month: "2-digit" })} ${time}`;
  }

  function describeBucket(minutes) {
    if (minutes < 60) {
      return `${minutes} min`;
    }
    return minutes < MINUTES_PER_DAY ? `${minutes / 60} h` : "1 día";
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
        plugins: {
          legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } },
          tooltip: { callbacks: { title: (items) => bucketTitles[items[0].dataIndex] } },
        },
        scales: {
          x: { grid: { display: false }, ticks: { maxTicksLimit: 7, maxRotation: 0 } },
          y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: COLORS.grid } },
        },
      },
    }),
    detected: buildRankingChart("detected", COLORS.blue),
    replaced: buildRankingChart("replaced", COLORS.teal),
    products: buildProductsDoughnut(),
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

  // Products beyond the top ten are grouped as "Otros", so the shares add up to all replacements.
  function setProducts(rows, totalReplacements) {
    const slices = rows.map((row, index) => ({ name: row.name, total: row.total, color: DONUT_COLORS[index % DONUT_COLORS.length] }));
    const others = totalReplacements - rows.reduce((sum, row) => sum + row.total, 0);
    if (others > 0) {
      slices.push({ name: OTHERS_LABEL, total: others, color: OTHERS_COLOR });
    }
    const chart = charts.products;
    chart.data.labels = slices.map((slice) => slice.name);
    chart.data.datasets[0].data = slices.map((slice) => slice.total);
    chart.data.datasets[0].backgroundColor = slices.map((slice) => slice.color);
    chart.update();
    const isEmpty = slices.length === 0;
    document.querySelector('[data-empty="products"]').hidden = !isEmpty;
    chart.canvas.parentElement.hidden = isEmpty;
  }

  function describeWindow(snapshot) {
    const bucket = `cada ${describeBucket(snapshot.timeline.bucket_minutes)}`;
    if (timeframe.range) {
      return `${RANGE_NAMES[timeframe.range]} · ${bucket}`;
    }
    const format = (iso) => new Date(iso).toLocaleString([], { dateStyle: "short", timeStyle: "short" });
    // The end is exclusive and one minute past the last minute shown for presets only.
    return `${format(snapshot.window.start)} a ${format(snapshot.window.end)} · ${bucket}`;
  }

  function render(snapshot) {
    const { totals, timeline } = snapshot;
    setKpi("photos", totals.photos);
    setKpi("uploads", totals.uploads);
    setKpi("samples", totals.samples);
    setKpi("detected_objects", totals.detected_objects);
    setKpi("replacements", totals.replacements);
    setKpi("objects_per_upload", totals.uploads ? totals.detected_objects / totals.uploads : 0, 1);

    const spanMinutes = timeline.bucket_minutes * timeline.buckets.length;
    bucketTitles = timeline.buckets.map((iso) =>
      new Date(iso).toLocaleString([], { dateStyle: "short", timeStyle: "short" }),
    );
    charts.timeline.data.labels = timeline.buckets.map((iso) =>
      formatBucketLabel(iso, spanMinutes, timeline.bucket_minutes),
    );
    charts.timeline.data.datasets[0].data = timeline.photos;
    charts.timeline.data.datasets[1].data = timeline.replacements;
    charts.timeline.update();
    timelineNote.textContent = describeWindow(snapshot);

    setRanking("detected", snapshot.top_detected);
    setRanking("replaced", snapshot.top_replaced);
    setProducts(snapshot.top_products, totals.replacements);
  }

  // The timeframe is either {range: "1d"} or {from, to} in ISO UTC; it lives in the URL.
  function readTimeframe() {
    const params = new URLSearchParams(location.search);
    const from = params.get("from");
    const to = params.get("to");
    if (from && to && !Number.isNaN(Date.parse(from)) && !Number.isNaN(Date.parse(to))) {
      return { from, to };
    }
    const range = params.get("range");
    return { range: range in RANGE_NAMES ? range : "1h" };
  }

  function timeframeQuery() {
    const params = new URLSearchParams(timeframe.range ? { range: timeframe.range } : timeframe);
    return params.toString();
  }

  // datetime-local inputs take local time as "YYYY-MM-DDTHH:mm".
  function toLocalInput(date) {
    const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return shifted.toISOString().slice(0, 16);
  }

  const timelineNote = document.querySelector("[data-timeline-note]");
  const rangeButtons = document.querySelectorAll("[data-range]");
  const customForm = document.querySelector("[data-custom-form]");
  const customFrom = document.querySelector("[data-custom-from]");
  const customTo = document.querySelector("[data-custom-to]");
  const customError = document.querySelector("[data-custom-error]");
  let timeframe = readTimeframe();
  let customOpen = Boolean(timeframe.from);

  function showCustomError(message) {
    customError.textContent = message;
    customError.hidden = !message;
  }

  function syncControls() {
    rangeButtons.forEach((button) => {
      const name = button.dataset.range;
      const active = name === "custom" ? Boolean(timeframe.from) || customOpen : name === timeframe.range && !customOpen;
      button.setAttribute("aria-pressed", String(active));
    });
    customForm.hidden = !customOpen;
  }

  let lastBody = null;
  let lastOkAt = null;
  let timer = null;
  let controller = null;

  function applyTimeframe(next) {
    timeframe = next;
    history.replaceState(null, "", `?${timeframeQuery()}`);
    syncControls();
    // Answers for the old timeframe must never be drawn over the new one.
    if (controller) {
      controller.abort();
      controller = null;
    }
    lastBody = null;
    poll();
  }

  rangeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const name = button.dataset.range;
      if (name === "custom") {
        customOpen = !customOpen;
        if (customOpen && !customFrom.value) {
          const now = new Date();
          customTo.value = toLocalInput(now);
          customFrom.value = toLocalInput(new Date(now.getTime() - MINUTES_PER_DAY * 60000));
        }
        showCustomError("");
        syncControls();
        return;
      }
      customOpen = false;
      showCustomError("");
      applyTimeframe({ range: name });
    });
  });

  customForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const from = new Date(customFrom.value);
    const to = new Date(customTo.value);
    if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime())) {
      showCustomError("Completá las dos fechas.");
    } else if (from >= to) {
      showCustomError("El inicio debe ser anterior al fin.");
    } else if (to - from > MAX_CUSTOM_DAYS * MINUTES_PER_DAY * 60000) {
      showCustomError(`El rango máximo es de ${MAX_CUSTOM_DAYS} días.`);
    } else {
      showCustomError("");
      applyTimeframe({ from: from.toISOString(), to: to.toISOString() });
    }
  });

  function showStatus() {
    if (lastOkAt === null) {
      return;
    }
    const seconds = Math.round((Date.now() - lastOkAt) / 1000);
    liveText.textContent = seconds < 2 ? "En vivo · actualizado ahora" : `En vivo · actualizado hace ${seconds}s`;
  }

  async function poll() {
    clearTimeout(timer);
    if (!controller && !document.hidden) {
      const mine = new AbortController();
      controller = mine;
      try {
        const response = await fetch(`/analytics/data?${timeframeQuery()}`, {
          cache: "no-store",
          signal: mine.signal,
        });
        if (!response.ok) {
          const failure = response.status === 400 ? await response.json().catch(() => ({})) : {};
          if (failure.error) {
            showCustomError(failure.error);
          }
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
      } catch (error) {
        if (error.name !== "AbortError") {
          live.classList.remove("is-live");
          live.classList.add("is-offline");
          liveText.textContent = "Sin conexión · reintentando…";
        }
      } finally {
        if (controller === mine) {
          controller = null;
        }
      }
    }
    timer = setTimeout(poll, POLL_MS);
  }

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      poll();
    }
  });
  syncControls();
  setInterval(showStatus, 1000);
  poll();
})();
