const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { test } = require('node:test');

function check(t, input, reportOnly = false) {
  const parent = fs.realpathSync(os.tmpdir());
  const directory = fs.mkdtempSync(path.join(parent, 'vendorops-guard-test-'));
  t.after(() => {
    const resolved = fs.realpathSync(directory);
    assert.equal(path.dirname(resolved), parent);
    assert.ok(path.basename(resolved).startsWith('vendorops-guard-test-'));
    fs.rmSync(resolved, { recursive: true });
  });
  const data = path.join(directory, 'template.yaml');
  const output = path.join(directory, 'report.json');
  fs.writeFileSync(data, typeof input === 'string' ? input : JSON.stringify(input));
  const result = spawnSync(process.execPath, [
    path.join(__dirname, 'check.cjs'), '--data', data, '--output', output,
    ...(reportOnly ? ['--report-only'] : []),
  ], { encoding: 'utf8', timeout: 30000 });
  assert.ifError(result.error);
  return { ...result, report: fs.existsSync(output) ? JSON.parse(fs.readFileSync(output, 'utf8')) : null };
}

function fixture(publicIP = false) {
  const properties = {
    ImageId: 'ami-0123456789abcdef0', InstanceType: 't3.small',
    IamInstanceProfile: 'synthetic-profile', SubnetId: 'subnet-example',
  };
  if (publicIP) {
    delete properties.SubnetId;
    properties.NetworkInterfaces = [{
      DeviceIndex: '0', SubnetId: 'subnet-example', AssociatePublicIpAddress: true,
    }];
  }
  return { Resources: { Example: { Type: 'AWS::EC2::Instance', Properties: properties } } };
}

test('an EC2 policy probe without a public IP has no reported violations', t => {
  const result = check(t, fixture());
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.report.properties.vendorops.reportedViolations, 0);
});

test('a public IP produces findings and fails strict validation', t => {
  const result = check(t, fixture(true));
  assert.equal(result.status, 1, result.stderr);
  assert.ok(result.report.runs[0].results.some(row => row.ruleId === 'EC2_INSTANCE_NO_PUBLIC_IP'));
});

test('advisory mode preserves the violations in its report', t => {
  const result = check(t, fixture(true), true);
  assert.equal(result.status, 0, result.stderr);
  assert.ok(result.report.properties.vendorops.reportedViolations > 0);
  assert.equal(result.report.properties.vendorops.reportOnly, true);
});

test('invalid input fails even in advisory mode', t => {
  const result = check(t, 'Resources: [', true);
  assert.equal(result.status, 2, result.stderr);
  assert.equal(result.report, null);
});
