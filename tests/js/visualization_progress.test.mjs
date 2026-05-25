import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const progress = await readFile(
  new URL("../../docs-site/src/components/visualization/data/content-progress.js", import.meta.url),
  "utf8",
);
const currentWork = await readFile(
  new URL("../../docs/current-work.md", import.meta.url),
  "utf8",
);

const PR2_RAG_ADR_ALIGNMENT_PLAN = {
  date: "2026-05-17",
  title: "PR2 Rag ADR Alignment",
  kind: "refactor",
  adr: "ADR-004",
};
const LIVING_DOCS_P2_SERVICES_PLAN = {
  date: "2026-05-23",
  title: "Living Docs P2 Services",
  kind: "docs",
  adr: "ADR-005",
};
const CURRENT_ADR_LINKED_PLANS = [
  PR2_RAG_ADR_ALIGNMENT_PLAN,
  LIVING_DOCS_P2_SERVICES_PLAN,
];

function requiredMatch(value, pattern, label) {
  const match = value.match(pattern);
  assert.ok(match, `Missing ${label}`);
  return match;
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function extractPropertyBlock(source, propertyName, opener, closer) {
  const pattern = new RegExp(
    String.raw`(?:^|\n)\s*${escapeRegExp(propertyName)}:\s*${escapeRegExp(opener)}`,
    "m",
  );
  const match = source.match(pattern);
  assert.ok(match, `Missing ${propertyName} block`);

  const openIndex = match.index + match[0].lastIndexOf(opener);
  let depth = 0;
  let quote = null;
  let escaped = false;

  for (let index = openIndex; index < source.length; index += 1) {
    const char = source[index];
    if (quote) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === quote) {
        quote = null;
      }
      continue;
    }
    if (char === '"' || char === "'") {
      quote = char;
      continue;
    }
    if (char === opener) {
      depth += 1;
      continue;
    }
    if (char === closer) {
      depth -= 1;
      if (depth === 0) {
        return source.slice(openIndex + 1, index);
      }
    }
  }

  assert.fail(`Unterminated ${propertyName} block`);
}

function extractCurrentWorkLastReviewed(markdown) {
  const frontmatter = requiredMatch(
    markdown,
    /^---\n([\s\S]*?)\n---(?:\n|$)/,
    "current-work frontmatter",
  )[1];
  return requiredMatch(
    frontmatter,
    /^last_reviewed:\s*(\d{4}-\d{2}-\d{2})$/m,
    "frontmatter last_reviewed date",
  )[1];
}

function extractProgressLastReviewed(source) {
  const phaseBlock = extractPropertyBlock(source, "phase", "{", "}");
  return requiredMatch(
    phaseBlock,
    /(?:^|\n)\s*lastReviewed:\s*"(\d{4}-\d{2}-\d{2})"/,
    "PROGRESS.phase.lastReviewed date",
  )[1];
}

function collectTopLevelObjectBlocks(source) {
  const blocks = [];
  let quote = null;
  let escaped = false;
  let depth = 0;
  let start = null;

  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    if (quote) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === quote) {
        quote = null;
      }
      continue;
    }
    if (char === '"' || char === "'") {
      quote = char;
      continue;
    }
    if (char === "{") {
      if (depth === 0) {
        start = index;
      }
      depth += 1;
      continue;
    }
    if (char === "}") {
      depth -= 1;
      if (depth === 0 && start !== null) {
        blocks.push(source.slice(start + 1, index));
        start = null;
      }
    }
  }

  return blocks;
}

function parseStringProperties(objectBlock) {
  return Object.fromEntries(
    [...objectBlock.matchAll(/\b([a-zA-Z_$][\w$]*)\s*:\s*"([^"]*)"/g)]
      .map(([, key, value]) => [key, value]),
  );
}

function parsePlansTimelineEntries(source) {
  const block = extractPropertyBlock(source, "plansTimeline", "[", "]");
  return collectTopLevelObjectBlocks(block).map(parseStringProperties);
}

function requirePlanEntry(entries, expected) {
  const entry = entries.find((candidate) => (
    Object.entries(expected).every(([key, value]) => candidate[key] === value)
  ));
  assert.ok(entry, `Missing plan entry ${JSON.stringify(expected)}`);
  return entry;
}

test("visualization progress mirrors current-work review date", () => {
  assert.equal(
    extractProgressLastReviewed(progress),
    extractCurrentWorkLastReviewed(currentWork),
  );
});

test("visualization progress includes current A1-A17 work", () => {
  const verificationLine = requiredMatch(
    currentWork,
    /^- Verification: (.+)$/m,
    "current-work Verification line",
  )[1];

  assert.match(progress, /A1-A17 Refactoring Continuation/);
  assert.ok(progress.includes(verificationLine));
});

test("visualization progress includes the latest visualization landing", () => {
  assert.match(progress, /2026-05-22: プロジェクト可視化ページ/);
  assert.match(progress, /\/visualization/);
});

test("visualization progress includes current ADR-linked plans", () => {
  const entries = parsePlansTimelineEntries(progress);

  for (const plan of CURRENT_ADR_LINKED_PLANS) {
    requirePlanEntry(entries, plan);
  }
});

test("plansTimeline parser ignores prefixed property names", () => {
  const entries = parsePlansTimelineEntries(`
    wrappedplansTimeline: [
      { date: "1999-01-01", title: "Wrong", kind: "docs", adr: "ADR-999" },
    ],
    plansTimeline: [
      { date: "2026-05-17", title: "PR2 Rag ADR Alignment", kind: "refactor", adr: "ADR-004" },
    ],
  `);

  assert.deepEqual(entries, [PR2_RAG_ADR_ALIGNMENT_PLAN]);
});

test("plansTimeline validation requires attributes on the same entry", () => {
  const entries = parsePlansTimelineEntries(`
    plansTimeline: [
      { date: "2026-05-17", title: "PR1 Queue + XSS Prevention", kind: "security" },
      { title: "PR2 Rag ADR Alignment", kind: "refactor", adr: "ADR-004" },
    ],
  `);

  assert.throws(
    () => requirePlanEntry(entries, PR2_RAG_ADR_ALIGNMENT_PLAN),
    /Missing plan entry/,
  );
});

test("plansTimeline validation keeps PR2 kind exact", () => {
  const entries = parsePlansTimelineEntries(`
    plansTimeline: [
      { date: "2026-05-17", title: "PR2 Rag ADR Alignment", kind: "docs", adr: "ADR-004" },
    ],
  `);

  assert.throws(
    () => requirePlanEntry(entries, PR2_RAG_ADR_ALIGNMENT_PLAN),
    /Missing plan entry/,
  );
});

test("current-work review date is read from frontmatter only", () => {
  assert.throws(
    () => extractCurrentWorkLastReviewed(`---\nscope: demo\n---\n\nlast_reviewed: 2099-01-01\n`),
    /frontmatter last_reviewed/,
  );
});
