import unittest,tempfile,hashlib,base64,io,contextlib
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from configure_usb import configure
from package_mainline_usb import INPUTS, USB_ID
from prepare_usb import prepare

class ProvisioningTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
  (self.base/'w152d').mkdir();(self.base/'w152d/USB_ID').write_bytes(USB_ID+b'\n')
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

class PrepareUsbTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.usb = base / "usb"
        self.usb.mkdir()
        self.bundle = base / "bundle"
        self.bundle.mkdir()
        self.rootfs = base / "rootfs.ext4"
        self.rootfs.write_bytes(bytes(1080) + b"\x53\xef")
        checksums = []
        for name in (*INPUTS, "boot.scr", "aml_autoscript"):
            data = name.encode()
            (self.bundle / name).write_bytes(data)
            checksums.append(f"{hashlib.sha256(data).hexdigest()}  {name}\n")
        (self.bundle / "SHA256SUMS").write_text("".join(checksums), encoding="ascii")

    def test_prepares_mainline_layout(self):
        prepare(self.usb, self.bundle, self.rootfs)
        self.assertEqual((self.usb / "w152d/USB_ID").read_bytes().strip(), USB_ID)
        self.assertEqual((self.usb / "w152d/rootfs.ext4").read_bytes(), self.rootfs.read_bytes())
        self.assertEqual((self.usb / "aml_autoscript").read_bytes(), b"aml_autoscript")
        self.assertEqual(
            {path.name for path in (self.usb / "w152d/mainline").iterdir()},
            {"Image", "integrated-probe.dtb", "initramfs.cpio.gz", "boot.scr"},
        )
        with self.assertRaisesRegex(ValueError, "existing"):
            prepare(self.usb, self.bundle, self.rootfs)

    def test_rejects_mismatched_bundle_before_copying(self):
        (self.bundle / "Image").write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            prepare(self.usb, self.bundle, self.rootfs)
        self.assertEqual(list(self.usb.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
