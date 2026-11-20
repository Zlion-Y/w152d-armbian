"""Extract this device's boot components locally; no flashing or shared blobs."""
from pathlib import Path
import argparse,sys,struct,gzip,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).resolve().parent))
import build_probe as bp
from ext4tool import Ext4
def write(path,data,manifest):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
 manifest[str(path.name)]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
def extract(stock_dir,vendor_path,out):
 manifest={}
 def read(name):
  p=stock_dir/name;b=p.read_bytes();checksum=p.with_name(p.name+'.sha256')
  if checksum.exists():assert hashlib.sha256(b).hexdigest()==checksum.read_text().split()[0],name+' checksum mismatch'
  return b
 boot=read('boot_a.img');vb=read('vendor_boot_a.img')
 assert boot[:8]==b'ANDROID!' and struct.unpack_from('<I',boot,40)[0]==3
 size=struct.unpack_from('<I',boot,8)[0];image=bp.lz4_frame(boot[4096:4096+size])
 assert image[56:60]==b'ARMd'
 assert 0x01080000+max(len(image),struct.unpack_from('<Q',image,16)[0])<0x02bffe00
 assert vb[:8]==b'VNDRBOOT' and struct.unpack_from('<I',vb,8)[0]==3
 page=struct.unpack_from('<I',vb,12)[0];rs=struct.unpack_from('<I',vb,24)[0]
 hs,ds=struct.unpack_from('<II',vb,2096);start=bp.align(hs,page)
 entries=bp.cpio_parse(gzip.decompress(vb[start:start+rs]))
 dtb=vb[start+bp.align(rs,page):start+bp.align(rs,page)+ds]
 write(out/'Image',image,manifest);write(out/'dtb.img',dtb,manifest)
 graph={}
 for line in entries['lib/modules/modules.dep'][1].decode().splitlines():
  name,deps=line.split(':',1);graph[Path(name).name]=[Path(x).name for x in deps.split()]
 order=[]
 def visit(name):
  if name in order:return
  for child in graph[name]:visit(child)
  order.append(name)
 for name in ['dwmac-meson8b.ko','meson-gxl.ko']:visit(name)
 for name in order:write(out/'stock/modules'/name,entries['lib/modules/'+name][1],manifest)
 (out/'stock/modules.order').write_bytes(('\n'.join(order)+'\n').encode())
 fs=Ext4(str(vendor_path))
 try:
  for name in ['wifi_comm.ko','uwe5621_bsp_sdio.ko','sprdwl_ng.ko']:
   inode=fs.lookup('/lib/modules/'+name);assert inode is not None,name
   data=fs.read_file(inode);assert b'vermagic=5.4.210 ' in data,name+' kernel mismatch'
   write(out/'stock/modules'/name,data,manifest)
  for name in ['wcnmodem.bin','regulatory.db','regulatory.db.p7s']:
   inode=fs.lookup('/firmware/'+name);assert inode is not None,name
   write(out/'stock/firmware'/name,fs.read_file(inode),manifest)
  inode=fs.lookup('/etc/wifi_board_config.ini');assert inode is not None
  write(out/'stock/wifi_board_config.ini',fs.read_file(inode),manifest)
 finally:fs.close()
 (out/'stock/extraction-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print('Extracted kernel, DTB and matching modules/firmware locally to',out)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--stock-dir',type=Path,required=True);p.add_argument('--vendor-image',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();extract(a.stock_dir,a.vendor_image,a.output)
