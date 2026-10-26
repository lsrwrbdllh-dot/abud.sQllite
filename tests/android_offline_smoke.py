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
    result=list(ET.fromstring(text[text.index('<?xml'):]).iter('node'))
    # Android 15's first-boot launcher can show an unrelated ANR over the app.
    # Dismiss only that launcher dialog; never dismiss this app's errors/ANRs.
    if any("Pixel Launcher isn't responding" in n.get('text','') for n in result):
        close=next((n for n in result if n.get('resource-id')=='android:id/aerr_close'),None)
        if close is not None:
            tap_node(close)
            print('Dismissed an unrelated first-boot Pixel Launcher ANR.')
            return []
    return result

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

def tap_node(node):
    x1,y1,x2,y2=map(int,re.findall(r'\d+',node.get('bounds')))
    adb('shell','input','tap',str((x1+x2)//2),str((y1+y2)//2))

def tap(label,scroll=False):
    tap_node(find(label,scroll=scroll))

def tap_account(code):
    until=time.monotonic()+20
    while time.monotonic()<until:
        for node in nodes():
            if node.get('class')=='android.widget.TextView' and code in node.get('text',''):
                tap_node(node)
                return
        time.sleep(.5)
    raise AssertionError('Financial account not found: '+code)

def enter(label,value):
    tap(label)
    adb('shell','input','keyevent','KEYCODE_MOVE_END')
    adb('shell','input','keyevent','KEYCODE_DEL')
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
    find('محاسبة على هاتفك',timeout=60)
    enter('اسم المتجر','OfflineStore')
    enter('اسم العملة','UNIT')
    enter('اسم مستخدم المدير','admin')
    enter('كلمة مرور المدير (8 أحرف على الأقل)','admin-pass-123')
    tap('إنشاء متجر جديد',scroll=True)
    find('تعمل محلياً • العملة: UNIT')
    tap('المخزون والفروع',scroll=True)
    tap('تصنيفات المنتجات')
    tap('إضافة سجل')
    enter('الاسم *','OfflineCategory')
    tap('حفظ المسودة / البيانات',scroll=True)
    find('الاسم: OfflineCategory')
    adb('shell','input','keyevent','KEYCODE_BACK')
    tap('قيد يومية يدوي / تمويل رأس المال')
    enter('وصف القيد','OpeningCapital')
    for code,field in [('1500','مبلغ مدين'),('3000','مبلغ دائن')]:
        tap('إضافة سطر')
        enter('بحث عن سجل مرتبط',code)
        tap_account(code)
        enter(field,'100')
        tap('إضافة')
    tap('اعتماد القيد المتوازن',scroll=True)
    tap('متابعة')
    find('الوصف: OpeningCapital')
    find('الحالة: معتمد')
    adb('shell','am','force-stop',PACKAGE)
    adb('shell','am','start','-W','-n',PACKAGE+'/com.abud.supermarket.MainActivity')
    find('تسجيل الدخول',timeout=60)
    enter('اسم المستخدم','admin')
    enter('كلمة المرور','admin-pass-123')
    tap('دخول')
    find('تعمل محلياً • العملة: UNIT')
    tap('المخزون والفروع',scroll=True)
    tap('تصنيفات المنتجات')
    # Query the exact persisted value rather than accepting an empty list.
    found=False
    for _ in range(15):
        if any('OfflineCategory' in n.get('text','') for n in nodes()):found=True;break
        time.sleep(.5)
    assert found,'Created category was lost after process restart.'
    tap('الرئيسية')
    tap('إدارة الموظفين والصلاحيات')
    tap('إضافة موظف')
    enter('اسم الموظف','Cashier')
    enter('اسم مستخدم الموظف','cashier')
    enter('كلمة مرور الموظف (اتركها فارغة للإبقاء على الحالية)','employee-pass')
    tap('الصندوق الرئيسي',scroll=True)
    tap('حفظ الموظف والصلاحيات',scroll=True)
    find('cashier — Cashier — نشط')
    tap('الرئيسية')
    tap('تسجيل الخروج',scroll=True)
    find('تسجيل الدخول')
    enter('اسم المستخدم','cashier')
    enter('كلمة المرور','employee-pass')
    tap('دخول')
    find('المستخدم: cashier')
    visible=set()
    for _ in range(10):
        visible.update(n.get('text','') for n in nodes())
        adb('shell','input','swipe','500','1750','500','450','250')
    for forbidden in ('إدارة الموظفين والصلاحيات','قيد يومية يدوي / تمويل رأس المال','نسخ احتياطي واستيراد وفحص','شراء جديد واستلام المخزون'):
        assert forbidden not in visible,'Cashier received a restricted screen: '+forbidden
    tap('تسجيل الخروج',scroll=True)
    find('تسجيل الدخول')
    assert adb('shell','pidof',PACKAGE),'App exited.'
    print('PASS: APK opened offline, created a manager, saved a category, posted capital, required login after restart, retained data, created a cashier and restricted cashier navigation.')
finally:
    (OUT/'logcat.txt').write_text(adb('logcat','-d',check=False),encoding='utf-8')
    with (OUT/'screen.png').open('wb') as image:
        subprocess.run(['adb','exec-out','screencap','-p'],stdout=image,check=False)
    adb('shell','cmd','connectivity','airplane-mode','disable',check=False)
