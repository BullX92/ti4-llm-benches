const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = __dirname;
const ORIGINAL_PATH = path.join(ROOT, "results.models.json");
const NORMALIZED_PATH = path.join(ROOT, "results.models_normalized.json");

function loadJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function evaluateAssertion(assertion, output) {
  if (!assertion || assertion.type !== "javascript") {
    return { pass: false, reason: `Unsupported assertion type: ${assertion?.type}` };
  }

  const context = { output, JSON };
  try {
    const result = vm.runInNewContext(assertion.value, context, { timeout: 1000 });
    return { pass: !!result, reason: !!result ? "pass" : "returned false" };
  } catch (error) {
    return { pass: false, reason: `error: ${error.message}` };
  }
}

function runAssertions(entry) {
  const assertions = entry.testCase?.assert || [];
  const output = entry.response?.output;
  return assertions.map((assertion, idx) => ({
    index: idx,
    type: assertion.type,
    value: assertion.value,
    ...evaluateAssertion(assertion, output),
  }));
}

function summarizeEntry(entry, results) {
  return {
    provider: entry.provider?.id || "unknown",
    testIdx: entry.testIdx,
    question: entry.vars?.question || "",
    passCount: results.filter((r) => r.pass).length,
    total: results.length,
    results,
  };
}

function makeKey(entry) {
  return `${entry.provider?.id}::${entry.testIdx}::${entry.promptIdx}`;
}

function main() {
  const original = loadJson(ORIGINAL_PATH).results.results;
  const normalized = loadJson(NORMALIZED_PATH).results.results;

  if (original.length !== normalized.length) {
    console.error(`Length mismatch: original=${original.length} normalized=${normalized.length}`);
    process.exit(1);
  }

  const originalMap = new Map(original.map((entry) => [makeKey(entry), entry]));
  const normalizedMap = new Map(normalized.map((entry) => [makeKey(entry), entry]));

  let originalPasses = 0;
  let normalizedPasses = 0;
  let totalAsserts = 0;
  const entryDiffs = [];

  for (const [key, originalEntry] of originalMap.entries()) {
    const normalizedEntry = normalizedMap.get(key);
    if (!normalizedEntry) {
      console.error(`Missing normalized entry for ${key}`);
      process.exit(1);
    }

    const originalResults = runAssertions(originalEntry);
    const normalizedResults = runAssertions(normalizedEntry);
    const originalSummary = summarizeEntry(originalEntry, originalResults);
    const normalizedSummary = summarizeEntry(normalizedEntry, normalizedResults);

    originalPasses += originalSummary.passCount;
    normalizedPasses += normalizedSummary.passCount;
    totalAsserts += originalSummary.total;

    const changed = [];
    for (let i = 0; i < originalResults.length; i += 1) {
      const before = originalResults[i];
      const after = normalizedResults[i];
      if (before.pass !== after.pass || before.reason !== after.reason) {
        changed.push({
          index: i,
          before: before.pass ? "PASS" : "FAIL",
          after: after.pass ? "PASS" : "FAIL",
          reasonBefore: before.reason,
          reasonAfter: after.reason,
          assertionBefore: before.value,
          assertionAfter: after.value,
        });
      }
    }

    if (changed.length || originalSummary.passCount !== normalizedSummary.passCount) {
      entryDiffs.push({
        provider: originalSummary.provider,
        testIdx: originalSummary.testIdx,
        question: originalSummary.question,
        originalPassCount: originalSummary.passCount,
        normalizedPassCount: normalizedSummary.passCount,
        changed,
      });
    }
  }

  console.log(`Total assertions: ${totalAsserts}`);
  console.log(`Original passes: ${originalPasses}`);
  console.log(`Normalized passes: ${normalizedPasses}`);
  console.log(`Delta: ${normalizedPasses - originalPasses}`);
  console.log("");

  if (!entryDiffs.length) {
    console.log("No assertion differences found.");
    return;
  }

  console.log(`Entries with differences: ${entryDiffs.length}`);
  console.log("");
  for (const diff of entryDiffs) {
    console.log(`[test ${diff.testIdx}] ${diff.provider}`);
    console.log(`Question: ${diff.question}`);
    console.log(`Pass count: ${diff.originalPassCount} -> ${diff.normalizedPassCount}`);
    for (const change of diff.changed) {
      console.log(`  assert[${change.index}]: ${change.before} -> ${change.after}`);
      console.log(`    before: ${change.reasonBefore}`);
      console.log(`    after: ${change.reasonAfter}`);
      if (change.assertionBefore === change.assertionAfter) {
        console.log(`    expr: ${change.assertionBefore}`);
      } else {
        console.log(`    expr before: ${change.assertionBefore}`);
        console.log(`    expr after: ${change.assertionAfter}`);
      }
    }
    console.log("");
  }
}

main();
