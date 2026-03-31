declare const process: {
  cwd(): string;
  env: Record<string, string | undefined>;
};

declare function require(name: string): any;

const path = require('path');
const { promises: fs } = require('fs');

import type { Page } from '../playwright';

const REPO_ROOT = process.cwd();
const DEFAULT_FIXTURE_PATH = path.join(REPO_ROOT, 'tests', 'fixtures', 'perf', 'benchmark-fixtures.json');
const DEFAULT_EVIDENCE_PATH = path.join(REPO_ROOT, '.sisyphus', 'evidence', 'final-performance-summary.json');
const FRONTEND_EVIDENCE_DIR = path.join(REPO_ROOT, '.sisyphus', 'evidence', 'frontend-perf');

export type BenchmarkFixtures = {
  frontend: {
    cold_boot: {
      render_selector: string;
      expected_minimum_cards: number;
      static_harness_base_url: string;
    };
    category_filter: {
      category: string;
      tag_selector: string;
      expected_count: number;
      sample_expected_ids: string[];
    };
    search_filter: {
      query: string;
      expected_ids: string[];
      expected_count: number;
    };
    route_detail: {
      drug_id: string;
      drug_name: string;
      prefilter_query: string;
      detail_selector: string;
    };
    combined_filter: {
      disease_id: string;
      disease_name: string;
      category: string;
      search_query: string;
      expected_ids: string[];
      expected_count: number;
    };
  };
};

function resolveFixturePath(): string {
  const override = process.env.DRUGTREE_PERF_FIXTURES_PATH;
  if (!override) {
    return DEFAULT_FIXTURE_PATH;
  }
  return path.isAbsolute(override) ? override : path.join(REPO_ROOT, override);
}

function resolveEvidencePath(): string {
  const override = process.env.DRUGTREE_PERF_EVIDENCE_PATH;
  if (!override) {
    return DEFAULT_EVIDENCE_PATH;
  }
  return path.isAbsolute(override) ? override : path.join(REPO_ROOT, override);
}

function percentile(values: number[], ratio: number): number {
  if (values.length === 0) {
    return 0;
  }
  const sorted = [...values].sort((left, right) => left - right);
  const index = Math.max(0, Math.min(sorted.length - 1, Math.ceil(sorted.length * ratio) - 1));
  return sorted[index];
}

export function summarizeSamples(samples: number[]) {
  const rounded = samples.map((sample) => Number(sample.toFixed(3)));
  return {
    samples_ms: rounded,
    sample_count: rounded.length,
    min_ms: rounded.length ? Number(Math.min(...rounded).toFixed(3)) : 0,
    max_ms: rounded.length ? Number(Math.max(...rounded).toFixed(3)) : 0,
    median_ms: Number(percentile(rounded, 0.5).toFixed(3)),
    p95_ms: Number(percentile(rounded, 0.95).toFixed(3)),
  };
}

export async function loadBenchmarkFixtures(): Promise<BenchmarkFixtures> {
  const fixturePath = resolveFixturePath();
  const raw = await fs.readFile(fixturePath, 'utf8').catch(() => {
    throw new Error(
      `Benchmark fixture file missing: ${fixturePath}. Run \`python3 scripts/perf/generate_fixtures.py --output tests/fixtures/perf\` first.`,
    );
  });
  return JSON.parse(raw) as BenchmarkFixtures;
}

async function loadEvidence(): Promise<Record<string, unknown>> {
  const aggregatePath = resolveEvidencePath();
  try {
    return JSON.parse(await fs.readFile(aggregatePath, 'utf8')) as Record<string, unknown>;
  } catch {
    return { benchmark_contract_version: 1 };
  }
}

export async function recordFrontendMetric(metricName: string, payload: Record<string, unknown>) {
  const aggregatePath = resolveEvidencePath();
  await fs.mkdir(path.dirname(aggregatePath), { recursive: true });
  await fs.mkdir(FRONTEND_EVIDENCE_DIR, { recursive: true });

  const evidence = await loadEvidence();
  const frontend = (evidence.frontend as Record<string, unknown> | undefined) ?? {
    suite: 'playwright-static-harness',
    metrics: {},
  };
  const metrics = (frontend.metrics as Record<string, unknown> | undefined) ?? {};

  metrics[metricName] = payload;
  frontend.metrics = metrics;
  evidence.frontend = frontend;
  evidence.generated_at = new Date().toISOString();

  await fs.writeFile(aggregatePath, `${JSON.stringify(evidence, null, 2)}\n`, 'utf8');
  await fs.writeFile(
    path.join(FRONTEND_EVIDENCE_DIR, `${metricName}.json`),
    `${JSON.stringify(payload, null, 2)}\n`,
    'utf8',
  );
}

export async function openAtlas(page: Page) {
  await page.goto('/');
  await page.waitForSelector('.app-shell', { timeout: 10000 });
  await page.waitForSelector('.drug-card', { timeout: 15000 });
}

export async function samplePerformanceNow(page: Page): Promise<number> {
  return page.evaluate(() => Number(performance.now().toFixed(3)));
}

export async function measureInteraction(
  page: Page,
  action: () => Promise<void>,
  settle: () => Promise<void>,
): Promise<number> {
  await page.evaluate(() => {
    (window as Window & { __drugtreePerfStart?: number }).__drugtreePerfStart = performance.now();
  });
  await action();
  await settle();
  return page.evaluate(() => {
    const started = (window as Window & { __drugtreePerfStart?: number }).__drugtreePerfStart ?? 0;
    return Number((performance.now() - started).toFixed(3));
  });
}

export async function visibleDrugIds(page: Page): Promise<string[]> {
  return page.locator('.drug-card').evaluateAll((nodes) => {
    return nodes
      .map((node) => node.getAttribute('data-drug-id'))
      .filter((value): value is string => Boolean(value));
  });
}
