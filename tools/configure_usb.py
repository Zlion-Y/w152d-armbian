"""Write only the user's first-boot configuration to an already prepared USB."""
from pathlib import Path
import argparse,getpass,hashlib,json,base64,re,os
def configure(destination,key,ssid,password):
 base=destination/'w152d';assert (base/'USB_ID').read_bytes().strip()==b'W152D_ARMBIAN_USB_DIRECT_V1','Not a prepared W152D USB'
 line=key.read_text(encoding='utf-8').strip()
 assert re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/=]+(?: [^\r\n]*)?',line),'Use a plain OpenSSH ED25519 public key'
 base64.b64decode(line.split()[1],validate=True)
 config=base/'config';config.mkdir(exist_ok=True)
 (config/'authorized_keys').write_text(line+'\n',encoding='utf-8')
 if ssid:
  assert 1<=len(ssid.encode())<=32
  assert 8<=len(password.encode())<=63,'WPA2 passphrase must have 8..63 UTF-8 bytes'
  psk=hashlib.pbkdf2_hmac('sha1',password.encode(),ssid.encode(),4096,32).hex()
  # Hex SSID avoids all shell, newline and wpa_supplicant quoting ambiguities.
  text='ctrl_interface=/run/wpa_supplicant\nupdate_config=0\ncountry=CN\nnetwork={\n ssid='+ssid.encode().hex()+'\n psk='+psk+'\n key_mgmt=WPA-PSK\n scan_ssid=1\n}\n'
  path=config/'wpa_supplicant.conf';path.write_bytes(text.encode());os.chmod(path,0o600)
 print('First-boot configuration written locally. No password was logged. Do not upload w152d/config/.')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--usb',type=Path,required=True);p.add_argument('--public-key',type=Path,required=True);p.add_argument('--ssid');p.add_argument('--password-stdin',action='store_true');a=p.parse_args()
 password=input() if a.ssid and a.password_stdin else getpass.getpass('Wi-Fi password (not echoed): ') if a.ssid else ''
 configure(a.usb,a.public_key,a.ssid,password)
