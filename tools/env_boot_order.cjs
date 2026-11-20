// Offline editor for the verified W152D two-copy environment layout.
// Node.js >= 22.15 (node:zlib.crc32). Never accesses a device.
'use strict';
const fs = require('node:fs');
const crypto = require('node:crypto');
const { crc32 } = require('node:zlib');
const COPY = 0x10000;
const PREFIX = COPY * 2;
const USB_FIRST = 'gpio set GPIOAO_11; setenv w152d_bootargs "${bootargs}"; run recovery_from_udisk; setenv bootargs "${w152d_bootargs}"; setenv w152d_bootargs; run common_dtb_load; run storeboot';
function check(value, message) { if (!value) throw new Error(message); }
function sha256(bytes) { return crypto.createHash('sha256').update(bytes).digest('hex'); }
function readCopy(image, base) {
  check(image.length >= PREFIX, 'Image smaller than two 64 KiB copies');
  const data = image.subarray(base + 4, base + COPY);
  check(image.readUInt32LE(base) === crc32(data), `CRC mismatch at ${base}`);
  const end = data.indexOf(Buffer.from([0, 0]));
  check(end > 0, `Missing environment terminator at ${base}`);
  check(data.subarray(end).every(x => x === 0), `Unexpected nonzero padding at ${base}`);
  const entries = data.subarray(0, end).toString('latin1').split('\0');
  const seen = new Set();
  const values = new Map();
  for (const entry of entries) {
    const equals = entry.indexOf('=');
    check(equals > 0, `Malformed entry at ${base}`);
    const name = entry.slice(0, equals);
    check(!seen.has(name), `Duplicate variable ${name} at ${base}`);
    seen.add(name);
    values.set(name, entry.slice(equals + 1));
  }
  check(values.has('bootcmd'), `Missing bootcmd at ${base}`);
  return { entries, values };
}
function inspect(image) {
  return { size: image.length, sha256: sha256(image), copies: [0, COPY].map(base => {
    const c = readCopy(image, base);
    return { offset: base, crc32: image.readUInt32LE(base).toString(16),
      entries: c.entries.length, bootcmd: c.values.get('bootcmd') };
  }) };
}
function patch(image, command = USB_FIRST) {
  check(typeof command === 'string' && command.length > 0 && /^[\x20-\x7e]+$/.test(command), 'bootcmd must be nonempty printable ASCII');
  const result = Buffer.from(image);
  for (const base of [0, COPY]) {
    const before = readCopy(image, base);
    if (command === USB_FIRST) {
      check(!before.values.has('w152d_bootargs'), 'Temporary variable already exists');
      for (const name of ['recovery_from_udisk', 'recovery_from_fat_dev', 'common_dtb_load', 'storeboot'])
        check(before.values.has(name), `Missing required variable ${name}`);
    }
    const entries = before.entries.map(e => e.startsWith('bootcmd=') ? 'bootcmd=' + command : e);
    const bytes = Buffer.from(entries.join('\0') + '\0\0', 'latin1');
    check(bytes.length <= COPY - 4, 'Environment capacity exceeded');
    const data = result.subarray(base + 4, base + COPY);
    data.fill(0);
    bytes.copy(data);
    result.writeUInt32LE(crc32(data), base);
    const after = readCopy(result, base);
    check(after.values.get('bootcmd') === command, 'bootcmd verification failed');
    check(before.entries.filter(e => !e.startsWith('bootcmd=')).join('\0') ===
      after.entries.filter(e => !e.startsWith('bootcmd=')).join('\0'), 'Other entries changed');
  }
  check(result.subarray(PREFIX).equals(image.subarray(PREFIX)), 'Partition tail changed');
  return result;
}
if (require.main === module) {
  try {
    const [action, input, output, command] = process.argv.slice(2);
    check(input && ['inspect', 'patch'].includes(action), 'Usage: node env_boot_order.cjs inspect INPUT | patch INPUT OUTPUT [BOOTCMD]');
    const original = fs.readFileSync(input);
    if (action === 'inspect') console.log(JSON.stringify(inspect(original), null, 2));
    else {
      check(output && !fs.existsSync(output) && !fs.existsSync(output + '.prefix') && !fs.existsSync(output + '.json'), 'Output exists or missing');
      const edited = patch(original, command);
      const report = { before: inspect(original), after: inspect(edited),
        changedVariables: ['bootcmd'], partitionTailUnchanged: true,
        prefixSize: PREFIX, prefixSha256: sha256(edited.subarray(0, PREFIX)) };
      fs.writeFileSync(output, edited, { flag: 'wx' });
      fs.writeFileSync(output + '.prefix', edited.subarray(0, PREFIX), { flag: 'wx' });
      fs.writeFileSync(output + '.json', JSON.stringify(report, null, 2) + '\n', { flag: 'wx' });
      console.log(JSON.stringify(report, null, 2));
    }
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
module.exports = { patch, inspect, readCopy, USB_FIRST, COPY, PREFIX };
