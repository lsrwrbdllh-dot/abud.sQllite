"""Run on a disposable Android emulator with the final packaged APK, no backend."""
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

PACKAGE='com.abud.supermarket.offline'
OUT=Path('artifacts/android-offline')
OUT.mkdir(parents=True,exist_ok=True)

def adb(*args,check=True):
    return subprocess.run(['adb',*args],text=True,capture_output=True,check=check).stdout.strip()

def nodes():
    adb('shell','uiautomator','dump','/sdcard/mobile-window.xml',check=False)
    text=adb('shell','cat','/sdcard/mobile-window.xml',check=False)
    if '<?xml' not in text:return []
    (OUT/'window.xml').write_text(text,encoding='utf-8')
    return list(ET.fromstring(text[text.index('<?xml'):]).iter('node'))

def find(label,timeout=25,scroll=False):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        candidates=nodes()
        # A field's visible label and EditText share the accessible name.
        # Prefer the input, then buttons, so tapping never targets its label.
        candidates.sort(key=lambda n: (0 if n.get('class','').endswith('EditText') else 1 if n.get('clickable')=='true' else 2))
        for node in candidates:
            if label in (node.get('text'),node.get('content-desc')):
                if node.get('bounds') not in (None,'[0,0][0,0]'):return node
        if scroll:adb('shell','input','swipe','500','1750','500','450','300')
        time.sleep(.5)
    raise AssertionError('Missing UI label: '+label)

def tap(label,scroll=False):
    node=find(label,scroll=scroll)
    x1,y1,x2,y2=map(int,re.findall(r'\d+',node.get('bounds')))
    adb('shell','input','tap',str((x1+x2)//2),str((y1+y2)//2))

def enter(label,value):
    tap(label)
    adb('shell','input','keyevent','KEYCODE_MOVE_END')
    adb('shell','input','text',value)
    adb('shell','input','keyevent','KEYCODE_BACK')

try:
    adb('install','-r',sys.argv[1])
    adb('shell','pm','clear',PACKAGE)
    adb('logcat','-c')
    adb('shell','cmd','connectivity','airplane-mode','enable',check=False)
    adb('shell','svc','wifi','disable')
    adb('shell','svc','data','disable')
    adb('shell','am','start','-W','-n',PACKAGE+'/com.abud.supermarket.MainActivity')
    find('محاسبة على هاتفك')
    enter('اسم المتجر','OfflineStore')
    enter('اسم العملة','UNIT')
    tap('إنشاء متجر جديد')
    find('تعمل محلياً • العملة: UNIT')
    tap('المخزون والفروع',scroll=True)
    tap('تصنيفات المنتجات')
    tap('إضافة سجل')
    enter('الاسم *','OfflineCategory')
    tap('حفظ المسودة / البيانات',scroll=True)
    find('الاسم: OfflineCategory')
    adb('shell','am','force-stop',PACKAGE)
    adb('shell','am','start','-W','-n',PACKAGE+'/com.abud.supermarket.MainActivity')
    find('تعمل محلياً • العملة: UNIT')
    tap('المخزون والفروع',scroll=True)
    tap('تصنيفات المنتجات')
    # Query the exact persisted value rather than accepting an empty list.
    found=False
    for _ in range(15):
        if any('OfflineCategory' in n.get('text','') for n in nodes()):found=True;break
        time.sleep(.5)
    assert found,'Created category was lost after process restart.'
    assert adb('shell','pidof',PACKAGE),'App exited.'
    print('PASS: packaged APK opened offline, initialized SQLite, saved a field and retained data after force-stop.')
finally:
    (OUT/'logcat.txt').write_text(adb('logcat','-d',check=False),encoding='utf-8')
    with (OUT/'screen.png').open('wb') as image:
        subprocess.run(['adb','exec-out','screencap','-p'],stdout=image,check=False)
    adb('shell','cmd','connectivity','airplane-mode','disable',check=False)
