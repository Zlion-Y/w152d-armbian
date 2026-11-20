import unittest,tempfile,hashlib,base64,io,contextlib,subprocess,shutil
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from configure_usb import configure

class ProvisioningTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
  (self.base/'w152d').mkdir();(self.base/'w152d/USB_ID').write_bytes(b'W152D_ARMBIAN_USB_DIRECT_V1\n')
  self.key=self.base/'test.pub'
  raw=b'\0\0\0\x0bssh-ed25519\0\0\0\x20'+bytes(range(32))
  self.key.write_text('ssh-ed25519 '+base64.b64encode(raw).decode()+' test-only\n')
 def tearDown(self):self.tmp.cleanup()
 def test_wifi_credentials_are_derived_not_logged(self):
  password='test-only-secret';ssid='quotes" and spaces'
  output=io.StringIO()
  with contextlib.redirect_stdout(output):configure(self.base,self.key,ssid,password)
  data=(self.base/'w152d/config/wpa_supplicant.conf').read_text()
  self.assertNotIn(password,data+output.getvalue())
  self.assertIn('ssid='+ssid.encode().hex(),data)
  self.assertIn(hashlib.pbkdf2_hmac('sha1',password.encode(),ssid.encode(),4096,32).hex(),data)
 def test_wrong_usb_is_rejected(self):
  (self.base/'w152d/USB_ID').write_bytes(b'OTHER_USB\n')
  with self.assertRaises(AssertionError):configure(self.base,self.key,None,'')
 def test_oversized_unicode_password_is_rejected(self):
  with self.assertRaises(AssertionError):configure(self.base,self.key,'test','\u4e2d'*30)
 def test_authorized_key_options_are_not_silently_accepted(self):
  self.key.write_text('command="something" '+self.key.read_text())
  with self.assertRaises(AssertionError):configure(self.base,self.key,None,'')

class EnvironmentTests(unittest.TestCase):
 @unittest.skipUnless(shutil.which('node'),'Node.js required for env editor tests')
 def test_distinct_copies_crc_tail_and_invalid_input(self):
  code=r'''
const assert=require('node:assert/strict');
const {crc32}=require('node:zlib');
const e=require('./tools/env_boot_order.cjs');
const b=Buffer.alloc(8*1024*1024,0x5a);
for(const base of [0,e.COPY]) {
 const data=b.subarray(base+4,base+e.COPY);data.fill(0);
 Buffer.from(['bootcmd=run storeboot','recovery_from_udisk=test','recovery_from_fat_dev=test','common_dtb_load=test','storeboot=test','copy='+base].join('\0')+'\0\0').copy(data);
 b.writeUInt32LE(crc32(data),base);
}
const p=e.patch(b);
assert(!p.subarray(0,e.COPY).equals(p.subarray(e.COPY,e.PREFIX)));
assert(p.subarray(e.PREFIX).equals(b.subarray(e.PREFIX)));
assert(e.patch(p,'run storeboot').equals(b));
const bad=Buffer.from(b);bad[100]^=1;
assert.throws(()=>e.patch(bad),/CRC mismatch/);
assert.throws(()=>e.patch(b.subarray(0,e.COPY)),/smaller/);
assert.equal(e.inspect(p).copies.length,2);
'''
  p=subprocess.run(['node','-e',code],cwd=ROOT,capture_output=True,text=True)
  self.assertEqual(p.returncode,0,p.stderr)

if __name__=='__main__':unittest.main()
