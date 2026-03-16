/* ======================================================================
   Mnemos Dashboard — ApexCharts wrappers
   ====================================================================== */

const ChartColors = {
  blue: '#6ea8fe',
  green: '#00d68f',
  red: '#ff6b6b',
  yellow: '#ffc107',
  purple: '#b197fc',
  cyan: '#66d9ef',
  bg: '#1a1d28',
  grid: '#2a2d3a',
  text: '#8b8fa3',
};

const CHART_PALETTE = [
  ChartColors.blue,
  ChartColors.green,
  ChartColors.purple,
  ChartColors.yellow,
  ChartColors.red,
  ChartColors.cyan,
];

const BASE_THEME = {
  chart: {
    background: 'transparent',
    foreColor: ChartColors.text,
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    toolbar: { show: false },
    animations: { enabled: true, speed: 400, dynamicAnimation: { speed: 300 } },
  },
  grid: {
    borderColor: ChartColors.grid,
    strokeDashArray: 3,
    xaxis: { lines: { show: false } },
  },
  tooltip: {
    theme: 'dark',
    style: { fontSize: '12px' },
  },
  legend: {
    labels: { colors: ChartColors.text },
    fontSize: '12px',
  },
};

/* ── Volume chart (time-series line) ──────────────────────────────── */

function renderVolumeChart(elementId, data) {
  const series = [];
  const categories = data.dates || [];

  if (data.plan) series.push({ name: 'Plan', data: data.plan });
  if (data.review) series.push({ name: 'Review', data: data.review });
  if (data.maintain) series.push({ name: 'Maintain', data: data.maintain });

  if (series.length === 0) {
    series.push({ name: 'Decisions', data: [] });
  }

  const options = {
    ...BASE_THEME,
    chart: {
      ...BASE_THEME.chart,
      type: 'area',
      height: 260,
      stacked: false,
    },
    series: series,
    colors: [ChartColors.blue, ChartColors.purple, ChartColors.cyan],
    xaxis: {
      categories: categories,
      labels: { style: { colors: ChartColors.text, fontSize: '11px' } },
      axisBorder: { color: ChartColors.grid },
      axisTicks: { color: ChartColors.grid },
    },
    yaxis: {
      labels: { style: { colors: ChartColors.text, fontSize: '11px' } },
    },
    stroke: { curve: 'smooth', width: 2 },
    fill: {
      type: 'gradient',
      gradient: { opacityFrom: 0.25, opacityTo: 0.02 },
    },
    dataLabels: { enabled: false },
  };

  const el = document.querySelector('#' + elementId);
  if (!el) return null;
  el.innerHTML = '';
  const chart = new ApexCharts(el, options);
  chart.render();
  return chart;
}

/* ── Pattern distribution (donut) ─────────────────────────────────── */

function renderPatternDistribution(elementId, data) {
  const labels = Object.keys(data || {});
  const values = Object.values(data || {});

  if (labels.length === 0) {
    labels.push('No data');
    values.push(1);
  }

  const options = {
    ...BASE_THEME,
    chart: {
      ...BASE_THEME.chart,
      type: 'donut',
      height: 260,
    },
    series: values,
    labels: labels,
    colors: CHART_PALETTE,
    plotOptions: {
      pie: {
        donut: {
          size: '60%',
          labels: {
            show: true,
            name: { color: ChartColors.text, fontSize: '13px' },
            value: { color: '#e0e0e0', fontSize: '18px', fontWeight: 600 },
            total: {
              show: true,
              label: 'Total',
              color: ChartColors.text,
              formatter: function (w) {
                return w.globals.seriesTotals.reduce((a, b) => a + b, 0);
              },
            },
          },
        },
      },
    },
    stroke: { width: 2, colors: ['#1a1d28'] },
    dataLabels: { enabled: false },
  };

  const el = document.querySelector('#' + elementId);
  if (!el) return null;
  el.innerHTML = '';
  const chart = new ApexCharts(el, options);
  chart.render();
  return chart;
}

/* ── Accuracy trend (line) ────────────────────────────────────────── */

function renderAccuracyTrend(elementId, data) {
  const series = [{
    name: 'Accuracy %',
    data: data.values || [],
  }];

  const options = {
    ...BASE_THEME,
    chart: {
      ...BASE_THEME.chart,
      type: 'line',
      height: 260,
    },
    series: series,
    colors: [ChartColors.green],
    xaxis: {
      categories: data.dates || [],
      labels: { style: { colors: ChartColors.text, fontSize: '11px' } },
      axisBorder: { color: ChartColors.grid },
      axisTicks: { color: ChartColors.grid },
    },
    yaxis: {
      min: 0,
      max: 100,
      labels: {
        style: { colors: ChartColors.text, fontSize: '11px' },
        formatter: (v) => v.toFixed(0) + '%',
      },
    },
    stroke: { curve: 'smooth', width: 3 },
    markers: { size: 4, strokeWidth: 0, hover: { size: 6 } },
    dataLabels: { enabled: false },
    fill: {
      type: 'gradient',
      gradient: { opacityFrom: 0.2, opacityTo: 0 },
    },
  };

  const el = document.querySelector('#' + elementId);
  if (!el) return null;
  el.innerHTML = '';
  const chart = new ApexCharts(el, options);
  chart.render();
  return chart;
}

/* ── Heatmap ──────────────────────────────────────────────────────── */

function renderHeatmap(elementId, data) {
  // data: { series: [{ name: 'pattern', data: [{ x: 'ds', y: count }] }] }
  const series = data.series || [];

  if (series.length === 0) {
    series.push({ name: 'No data', data: [{ x: '-', y: 0 }] });
  }

  const options = {
    ...BASE_THEME,
    chart: {
      ...BASE_THEME.chart,
      type: 'heatmap',
      height: 240,
    },
    series: series,
    colors: [ChartColors.blue],
    plotOptions: {
      heatmap: {
        radius: 4,
        enableShades: true,
        shadeIntensity: 0.7,
        colorScale: {
          ranges: [
            { from: 0, to: 0, color: '#1e2233', name: 'none' },
            { from: 1, to: 3, color: '#2a4a7f', name: 'low' },
            { from: 4, to: 8, color: '#3d6fbf', name: 'medium' },
            { from: 9, to: 100, color: '#6ea8fe', name: 'high' },
          ],
        },
      },
    },
    dataLabels: {
      enabled: true,
      style: { colors: ['#e0e0e0'], fontSize: '11px' },
    },
    xaxis: {
      labels: { style: { colors: ChartColors.text, fontSize: '11px' } },
    },
    yaxis: {
      labels: { style: { colors: ChartColors.text, fontSize: '11px' } },
    },
    stroke: { width: 2, colors: ['#1a1d28'] },
  };

  const el = document.querySelector('#' + elementId);
  if (!el) return null;
  el.innerHTML = '';
  const chart = new ApexCharts(el, options);
  chart.render();
  return chart;
}

/* ── Update an existing chart with new data ───────────────────────── */

function updateChart(chart, newData) {
  if (!chart) return;
  if (Array.isArray(newData)) {
    chart.updateSeries(newData);
  } else if (newData.series) {
    chart.updateSeries(newData.series);
  } else if (newData.labels && newData.values) {
    chart.updateOptions({ labels: newData.labels });
    chart.updateSeries(newData.values);
  }
}
