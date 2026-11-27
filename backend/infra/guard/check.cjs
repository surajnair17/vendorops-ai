// Run the official AWS Guard WebAssembly engine without native executable wrappers.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { parseArgs } = require('node:util');
const { validate } = require('@aws/cloudformation-guard');
const { version } = require('@aws/cloudformation-guard/package.json');

const ROOT = path.resolve(__dirname, '../../..');
const REGISTRY_COMMIT = '7f7340c26ae5d5e8874651dbffeb12e0e9f505b6';
const MAPPING = 'mappings/rule_set_wa-Security-Pillar.json';

async function main() {
  const { values } = parseArgs({ options: {
    registry: { type: 'string', default: path.join(ROOT, 'backend/artifacts/aws/guard/rules-registry') },
    data: { type: 'string', default: path.join(ROOT, 'backend/infra/cloudformation.yaml') },
    output: { type: 'string', default: path.join(ROOT, 'backend/artifacts/aws/guard/report.sarif.json') },
    'report-only': { type: 'boolean', default: false },
  }});
  const registry = path.resolve(values.registry);
  const git = (...args) => execFileSync('git', [
    '-c', `safe.directory=${registry.replaceAll(path.sep, '/')}`, '-C', registry, ...args,
  ], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
  if (git('rev-parse', 'HEAD') !== REGISTRY_COMMIT ||
      git('status', '--porcelain', '--untracked-files=no')) {
    throw new Error(`Use an unchanged AWS rules registry checkout at ${REGISTRY_COMMIT}.`);
  }
  const mapping = JSON.parse(fs.readFileSync(path.join(registry, MAPPING), 'utf8'));
  if (!mapping.mappings?.length || !fs.statSync(values.data).size) {
    throw new Error('The rules mapping and template must not be empty.');
  }
  const temporaryRoot = fs.realpathSync(os.tmpdir());
  const temporaryRules = fs.mkdtempSync(path.join(temporaryRoot, 'vendorops-guard-'));
  let report;
  try {
    for (const [index, entry] of mapping.mappings.entries()) {
      const source = path.resolve(registry, entry.guardFilePath);
      const relative = path.relative(registry, source);
      if (relative.startsWith('..') || path.isAbsolute(relative)) {
        throw new Error('The rules mapping contains a path outside its registry.');
      }
      fs.copyFileSync(source, path.join(temporaryRules, `${index}.guard`));
    }
    report = await validate({ rulesPath: temporaryRules, dataPath: path.resolve(values.data) });
  } finally {
    // Verify the absolute target before recursively removing this process's scratch files.
    const resolved = fs.realpathSync(temporaryRules);
    if (path.dirname(resolved) !== temporaryRoot || !path.basename(resolved).startsWith('vendorops-guard-')) {
      throw new Error('Refusing to remove an unexpected temporary directory.');
    }
    fs.rmSync(temporaryRules, { recursive: true });
  }
  const results = report.runs.flatMap(run => run.results ?? []);
  report.properties = { ...report.properties, vendorops: {
    guardVersion: version,
    registryCommit: REGISTRY_COMMIT,
    ruleSet: mapping.ruleSetName,
    ruleFiles: mapping.mappings.length,
    reportedViolations: results.length,
    reportOnly: values['report-only'],
  }};
  const destination = path.resolve(values.output);
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  fs.writeFileSync(destination, JSON.stringify(report, null, 2) + '\n');
  const counts = new Map();
  for (const result of results) {
    counts.set(result.ruleId, (counts.get(result.ruleId) ?? 0) + 1);
  }
  console.log(`Your template has ${results.length} reported violations across ${counts.size} AWS rules.`);
  console.log(`Guard ${version}; ${mapping.mappings.length} rule files; registry ${REGISTRY_COMMIT}.`);
  for (const [rule, count] of [...counts].sort()) console.log(`  ${rule}: ${count}`);
  console.log(`Full SARIF report: ${destination}`);
  if (values['report-only']) console.log('Report-only mode: findings require review; this is not a compliance pass.');
  if (process.env.GITHUB_STEP_SUMMARY) {
    fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY,
      `### AWS Guard findings\n\n${results.length} reported violations across ${counts.size} rules. ` +
      'This advisory scan is not a compliance pass. Download the SARIF artifact and see ' +
      '`backend/docs/infrastructure-checks.md` for reviewed findings.\n');
  }
  if (results.length && !values['report-only']) process.exitCode = 1;
}

main().catch(error => {
  console.error(`Guard could not complete: ${error.message}`);
  process.exitCode = 2;
});
