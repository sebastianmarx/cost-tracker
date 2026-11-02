<script lang="ts">
  import {
    Chart,
    Legend,
    LineController,
    LineElement,
    LinearScale,
    PointElement,
    TimeScale,
    Tooltip,
    type ChartDataset,
  } from 'chart.js'
  import 'chartjs-adapter-date-fns'
  import { onMount } from 'svelte'
  import { money, OVERFLOW_SERIES, SERIES_DARK, SERIES_LIGHT } from '../lib/format'
  import type { ChartSeries } from '../lib/types'

  Chart.register(LineController, LineElement, PointElement, LinearScale, TimeScale, Tooltip, Legend)

  let { series, target = null }: { series: ChartSeries[]; target?: number | null } = $props()

  let canvas: HTMLCanvasElement
  let chart: Chart<'line', { x: number; y: number }[]> | null = null
  let dark = $state(window.matchMedia('(prefers-color-scheme: dark)').matches)

  onMount(() => {
    const query = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = (e: MediaQueryListEvent) => (dark = e.matches)
    query.addEventListener('change', onChange)
    return () => {
      query.removeEventListener('change', onChange)
      chart?.destroy()
    }
  })

  const hasData = $derived(series.some((s) => s.points.length > 0))
  const currency = $derived(series[0]?.currency ?? 'EUR')

  $effect(() => {
    const palette = dark ? SERIES_DARK : SERIES_LIGHT
    const ink = dark ? '#c3c2b7' : '#52514e'
    const muted = '#898781'
    const grid = dark ? '#2c2c2a' : '#e1e0d9'
    const surface = dark ? '#1a1a19' : '#fcfcfb'

    const datasets: ChartDataset<'line', { x: number; y: number }[]>[] = series.map((s) => {
      const color = palette[s.slot] ?? OVERFLOW_SERIES
      return {
        label: s.label,
        data: s.points.map((p) => ({ x: new Date(p.ts).getTime(), y: p.price })),
        borderColor: color,
        backgroundColor: color,
        borderWidth: 2,
        stepped: 'after', // a price holds until the next check
        pointRadius: s.points.length === 1 ? 4 : 0,
        pointHoverRadius: 5,
        pointHoverBorderWidth: 2,
        pointHoverBorderColor: surface,
      }
    })

    const xs = datasets.flatMap((d) => d.data.map((p) => p.x))
    if (target !== null && xs.length) {
      datasets.push({
        label: 'Target',
        data: [
          { x: Math.min(...xs), y: target },
          { x: Math.max(...xs), y: target },
        ],
        borderColor: muted,
        backgroundColor: muted,
        borderWidth: 1.5,
        borderDash: [6, 4],
        pointRadius: 0,
        pointHoverRadius: 0,
      })
    }

    const showLegend = datasets.length > 1
    chart?.destroy()
    chart = new Chart<'line', { x: number; y: number }[]>(canvas, {
      type: 'line',
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: 'nearest', axis: 'x', intersect: false },
        scales: {
          x: {
            type: 'time',
            time: { tooltipFormat: 'dd.MM.yyyy HH:mm' },
            grid: { display: false },
            border: { color: dark ? '#383835' : '#c3c2b7' },
            ticks: { color: muted, maxRotation: 0, autoSkipPadding: 24 },
          },
          y: {
            grid: { color: grid },
            border: { display: false },
            ticks: { color: muted, callback: (v) => money(Number(v), currency) },
            grace: '5%',
          },
        },
        plugins: {
          legend: {
            display: showLegend,
            position: 'top',
            align: 'start',
            labels: { color: ink, usePointStyle: true, pointStyle: 'line', boxWidth: 24 },
          },
          tooltip: {
            backgroundColor: surface,
            titleColor: dark ? '#ffffff' : '#0b0b0b',
            bodyColor: ink,
            borderColor: dark ? 'rgba(255,255,255,0.1)' : 'rgba(11,11,11,0.1)',
            borderWidth: 1,
            padding: 10,
            usePointStyle: true,
            filter: (item) => item.dataset.label !== 'Target',
            callbacks: {
              label: (item) => ` ${item.dataset.label}: ${money(item.parsed.y, currency)}`,
            },
          },
        },
      },
    })
  })
</script>

<div class="wrap">
  <canvas bind:this={canvas} aria-label="Price history per shop"></canvas>
  {#if !hasData}
    <div class="empty muted">No price history in this range yet.</div>
  {/if}
</div>

<style>
  .wrap {
    position: relative;
    height: 320px;
  }
  .empty {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
  }
</style>
