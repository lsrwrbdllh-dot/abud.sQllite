"""Local Android command boundary. No HTTP, network connection, or SQL input."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import calendar
import hashlib
import json
import os
import re
import sqlite3
import threading

from .build_schema import TABLES, SOURCES
from .engine import Database, EFFECT_TABLES, RuleError, require, money, quantity
from .mobile_metadata import TABLE_LABELS, GROUPS, MONEY, QUANTITIES, AUTO, ENUM_LABELS, field_label
from . import mobile_security as security

LOCK = threading.RLock()
READ_ONLY = EFFECT_TABLES | {'ManualJournal'} | security.SECURITY_TABLES
DOCUMENTS = set(SOURCES) | {'InventoryCount'}

def _columns(db, table):
    require(table in TABLES, 'unknown table')
    return [dict(row) for row in db.rows(f'PRAGMA table_info("{table}")')]

def _keys(db, table):
    return [c['name'] for c in sorted(_columns(db, table), key=lambda c: c['pk']) if c['pk']]

def _where(db, table, values, primary=False):
    names = {c['name'] for c in _columns(db, table)}
    require(isinstance(values, dict) and set(values) <= names, 'unknown filter')
    if primary:
        require(set(values) == set(_keys(db, table)), 'record key required')
    return (' AND '.join(f'"{name}" IS ?' for name in values) or '1'), tuple(values.values())

def _rows(db, table, filters=None, search='', offset=0, limit=50):
    where, args = _where(db, table, filters or {})
    user = db.security_user
    allowed = security.columns(user, table, [c['name'] for c in _columns(db, table)])
    require(set(filters or {}) <= set(allowed), 'لا يسمح بالبحث في حقول محجوبة.')
    scope, scope_args = security.scope(db, user, table)
    where += ' AND (' + scope + ')'
    args += scope_args
    fields = [c for c in _columns(db, table) if c['name'] in allowed]
    if search:
        searchable = [c['name'] for c in fields if c['name'] != 'PasswordHash']
        where += ' AND (' + ' OR '.join(f'CAST("{c}" AS TEXT) LIKE ?' for c in searchable) + ')'
        args += tuple('%' + str(search) + '%' for _ in searchable)
    require(type(offset) is int and offset >= 0, 'invalid offset')
    total = db.scalar(f'SELECT count(*) FROM "{table}" WHERE {where}', args)
    rows = [dict(r) for r in db.rows(f'SELECT * FROM "{table}" WHERE {where} ORDER BY {",".join(_keys(db,table))} DESC LIMIT ? OFFSET ?', args + (limit, offset))]
    for row in rows:
        if 'PasswordHash' in row:
            row['PasswordHash'] = '••••••••'
    return {'rows': [security.visible(user, table, row) for row in rows], 'total': total, 'offset': offset}

def schema(db):
    tables = []
    user = db.security_user
    for name in TABLES:
        try: security.table_check(user, name)
        except RuleError: continue
        foreign = {r['from']: r['table'] for r in db.rows(f'PRAGMA foreign_key_list("{name}")')}
        columns = _columns(db, name)
        single_key = len(_keys(db, name)) == 1
        columns = [c for c in columns if c['name'] in security.columns(user, name, [x['name'] for x in columns])]
        for c in columns:
            key = c['name']
            c['foreign'] = foreign.get(key)
            c['label'] = field_label(key, foreign.get(key))
            c['scale'] = 100 if key in MONEY else 1000 if key in QUANTITIES else 1
            c['automatic'] = (single_key and bool(c['pk'])) or (key == 'Status' and name in DOCUMENTS) or key in AUTO.get(name, set())
            c['secret'] = key == 'PasswordHash'
            match = re.search(r'\b' + re.escape(key) + r"\s+IN\s*\(([^)]+)\)", TABLES[name])
            c['choices'] = re.findall(r"'([^']+)'", match[1]) if match else []
            c['boolean'] = 'INTEGER' == c['type'] and bool(re.search(r'\b'+re.escape(key)+r'\s+IN\s*\(0,1\)',TABLES[name]))
        children = []
        for child in TABLES:
            try: security.table_check(user, child)
            except RuleError: continue
            for fk in db.rows(f'PRAGMA foreign_key_list("{child}")'):
                if fk['table'] == name:
                    children.append({'table':child,'field':fk['from'],'target':fk['to'] or _keys(db,name)[0]})
        rights = {action: security.has(user, f'{name}.{action}') for action in security.ACTIONS}
        tables.append({'name':name,'label':TABLE_LABELS[name], 'columns':columns, 'rights':rights,
                       'editable': name not in READ_ONLY and (rights['create'] or rights['update']),
                       'postable':name in SOURCES and name != 'ManualJournal' and rights['post'] and
                           (name not in {'SalesReturn','PurchaseReturn'} or security.has(user,'returns.approve')) and
                           (name!='InventoryAdjustment' or security.has(user,'stock.adjust')),
                       'freezable':name=='InventoryCount' and rights['post'],'children':children})
    allowed_tables = {t['name'] for t in tables}
    return {'tables':tables,'groups':{k:[t for t in v.split() if t in allowed_tables] for k,v in GROUPS.items() if any(t in allowed_tables for t in v.split())},'choices':ENUM_LABELS,
            'user':{'id':user['id'],'username':user['username'],'manager':user['manager'],
                    'permissions':sorted(security.catalog() if user['manager'] else user['permissions'])},
            'currency':db.scalar('SELECT CurrencyName FROM SystemSetting WHERE SettingID=1')}

def _parse(db, table, values, updating=False):
    require(table not in READ_ONLY, 'الحركات والأرصدة المحاسبية تنشأ من اعتماد المستند فقط.')
    columns = {c['name']:c for c in _columns(db, table)}
    require(isinstance(values,dict) and set(values) <= set(columns), 'unknown column')
    protected = AUTO.get(table,set()) | ({'Status'} if table in DOCUMENTS else set())
    require(not set(values) & protected, 'لا يمكن إدخال الحقول المحسوبة أو حالة الاعتماد مباشرة.')
    if len(_keys(db,table)) == 1 or updating:
        require(not set(values) & set(_keys(db,table)), 'رقم السجل ينشأ تلقائياً.')
    result = {}
    for key, value in values.items():
        require(not isinstance(value,(float,bool)), 'أدخل الأرقام كنص عشري دقيق.')
        c = columns[key]
        if value is None or (value == '' and not c['notnull']):
            result[key] = None
        elif key == 'PasswordHash':
            require(isinstance(value,str) and len(value)>=8, 'كلمة المرور ثمانية أحرف على الأقل.')
            salt=os.urandom(16).hex()
            digest=hashlib.pbkdf2_hmac('sha256',value.encode(),salt.encode(),210000).hex()
            result[key]=f'pbkdf2_sha256$210000${salt}${digest}'
        elif c['type']=='INTEGER':
            scale=100 if key in MONEY else 1000 if key in QUANTITIES else 1
            text=str(value).strip().replace('٫','.').replace('−','-')
            try:
                number=Decimal(text)
                require(number.is_finite() and number*scale == (number*scale).to_integral_value(), 'دقة المبلغ منزلتان والكمية ثلاث منازل فقط.')
                parsed=int(number*scale)
                require(-(2**63)<=parsed<2**63, 'القيمة خارج الحدود المسموحة.')
                result[key]=parsed
            except (InvalidOperation, ValueError) as error:
                raise RuleError(f'{field_label(key)}: قيمة رقمية غير صحيحة.') from error
        else:
            require(isinstance(value,str), 'قيمة نصية مطلوبة.')
            result[key]=value.strip()
    return result

def _computed(db, table, values, old=None):
    all_values = dict(old or {}) | values
    if table == 'PayrollDetail':
        values['NetSalary']=all_values.get('BasicSalary',0)+all_values.get('Allowances',0)-all_values.get('Deductions',0)
    elif table == 'InventoryCountDetail':
        parent=db.get('InventoryCount',all_values['InventoryCountID'])
        values['SystemQuantity']=db.scalar('SELECT CurrentQuantity FROM BatchStock WHERE WarehouseID=? AND BatchID=?',(parent['WarehouseID'],all_values['BatchID'])) or 0
    elif table == 'InventoryAdjustmentDetail':
        row=db.get('InventoryCountDetail',all_values['InventoryCountDetailID'])
        values['QuantityDifference']=row['ActualQuantity']-row['SystemQuantity']
    elif table == 'AssetDepreciation':
        values['Amount']=db.depreciation_amount(all_values['AssetID'])
    elif table == 'AppUser' and old is None:
        values['CreatedAt']=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def _audit(db, table, ident, action, old, new):
    security.audit(db, action, table, ident, old, new)

def save(db, request):
    table=request['table']
    key=request.get('key')
    values=_parse(db,table,request['values'],updating=bool(key))
    with db.transaction():
        old=None
        if key:
            where,args=_where(db,table,key,primary=True)
            rows=db.rows(f'SELECT * FROM "{table}" WHERE {where}',args)
            require(len(rows)==1,'السجل غير موجود.')
            old=dict(rows[0])
            require(old.get('Status')!='POSTED','المستند المعتمد محفوظ ولا يقبل التعديل.')
        _computed(db,table,values,old)
        if key:
            require(values,'أدخل الحقول المطلوبة.')
            db.conn.execute(f'UPDATE "{table}" SET '+','.join(f'"{k}"=?' for k in values)+' WHERE '+where,tuple(values.values())+args)
            ident=next(iter(key.values()))
        else:
            ident=db.add(table,**values)
            security.ownership(db, db.security_user, table, ident)
        _audit(db,table,int(ident),'UPDATE' if key else 'CREATE',old,values)
        if key:
            return {'key':key}
        keys=_keys(db,table)
        return {'key':{keys[0]:ident} if len(keys)==1 else {k:values[k] for k in keys}}

def initialize(path, request):
    require(not path.exists(), 'توجد قاعدة بالفعل؛ لا يعاد تهيئتها.')
    currency=str(request.get('currency','')).strip()
    branch=str(request.get('branch','')).strip()
    require(currency and branch,'أدخل اسم المتجر والعملة.')
    temp=path.with_suffix('.initializing')
    temp.unlink(missing_ok=True)
    db=Database(temp)
    sample=Database(':memory:')
    try:
        db.migrate();sample.migrate();sample.seed()
        year=date.today().year
        with db.transaction():
            db.add('SystemSetting',SettingID=1,CurrencyName=currency,MoneyScale=100,QuantityScale=1000)
            db.add('Branch',BranchID=1,Name=branch)
            db.add('Warehouse',WarehouseID=1,Name='المستودع الرئيسي',BranchID=1)
            for table in ('ChartOfAccounts','FinancialAccountType','AccountingPolicy'):
                for row in sample.rows(f'SELECT * FROM {table}'):
                    values=dict(row)
                    for k,v in values.items():
                        if isinstance(v,str): values[k]=v.replace(' التجريبي','').replace(' تجريبي','')
                    db.add(table,**values)
            db.add('FinancialAccount',FinancialAccountID=1,AccountTypeID=1,BranchID=1,PostingAccountID=17,AccountName='الصندوق الرئيسي')
            db.add('FinancialAccount',FinancialAccountID=2,AccountTypeID=2,BranchID=1,PostingAccountID=18,AccountName='الحساب البنكي')
            db.add('FinancialYear',FinancialYearID=1,Name=str(year),StartDate=f'{year}-01-01',EndDate=f'{year}-12-31')
            for month in range(1,13):
                db.add('AccountingPeriod',AccountingPeriodID=month,FinancialYearID=1,Name=f'{month:02}',StartDate=f'{year}-{month:02}-01',EndDate=f'{year}-{month:02}-{calendar.monthrange(year,month)[1]}')
        db.check()
    finally:
        db.close();sample.close()
    os.replace(temp,path)
    return {'message':'تم إنشاء القاعدة على الهاتف دون بيانات أو حركات تجريبية.'}

def _signature(db):
    return {(r['type'],r['name']):r['sql'] for r in db.rows("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'")}

def restore(path, source, requester=None):
    require(source.is_file() and source.stat().st_size<=100*1024*1024,'ملف القاعدة غير موجود أو يتجاوز 100 ميغابايت.')
    with source.open('rb') as stream:
        require(stream.read(16)==b'SQLite format 3\x00','اختر ملف SQLite صحيحاً.')
    staged=path.with_suffix('.validated')
    staged.unlink(missing_ok=True)
    candidate=Database(source)
    expected=Database(':memory:')
    target=None
    try:
        expected.migrate()
        original_signature = _signature(expected)
        security.ensure(expected)
        require(_signature(candidate) in (original_signature,_signature(expected)),'مخطط الملف لا يطابق قاعدة abud.sQllite المعتمدة.')
        require(candidate.scalar('SELECT max(Version) FROM SchemaMigration')==1,'إصدار قاعدة غير مدعوم.')
        require(candidate.scalar('SELECT count(*) FROM SystemSetting WHERE SettingID=1 AND MoneyScale=100 AND QuantityScale=1000')==1,'إعداد العملة غير مكتمل.')
        candidate.check()
        if _signature(candidate)!=original_signature and security.configured(candidate):
            require(candidate.scalar("SELECT count(DISTINCT u.UserID) FROM AppUser u JOIN UserRole ur USING(UserID) JOIN Role r USING(RoleID) WHERE u.IsActive=1 AND r.RoleName='mobile:manager'"),
                    'النسخة المحمية لا تحتوي مديراً نشطاً؛ لم تستبدل القاعدة الحالية.')
        target=sqlite3.connect(staged)
        candidate.conn.backup(target)
    finally:
        if target: target.close()
        candidate.close();expected.close()
    if path.exists():
        current=Database(path)
        backup_path=path.parent/'before-restore.sqlite'
        dest=sqlite3.connect(backup_path)
        try:
            if requester:
                security.audit(current,'RESTORE','MobileSecurity',1,new={'RequestedBy':requester['username']},user=requester['id'])
            current.conn.backup(dest)
        finally: dest.close();current.close()
    os.replace(staged,path)
    return {'message':'تم استيراد القاعدة والتحقق من سلامتها. حفظت نسخة من القاعدة السابقة على الهاتف.'}

def report(db, kind, start, end):
    require(date.fromisoformat(start)<=date.fromisoformat(end),'الفترة غير صحيحة.')
    if kind=='trial':
        sql='''SELECT a.AccountCode AS الحساب,a.AccountName AS الاسم,
          COALESCE(sum(CASE WHEN j.EntryDate<=? THEN d.Debit ELSE 0 END),0) AS مدين,
          COALESCE(sum(CASE WHEN j.EntryDate<=? THEN d.Credit ELSE 0 END),0) AS دائن
          FROM ChartOfAccounts a LEFT JOIN JournalEntryDetail d USING(AccountID)
          LEFT JOIN JournalEntry j ON j.JournalEntryID=d.JournalEntryID AND j.Status='POSTED'
          GROUP BY a.AccountID ORDER BY a.AccountCode'''
        rows=[dict(r) for r in db.rows(sql,(end,end))]
        for row in rows:
            row['الرصيد']=row['مدين']-row['دائن']
    elif kind=='income':
        rows=[dict(r) for r in db.rows('''SELECT a.AccountName AS الحساب,a.AccountType AS النوع,
          COALESCE(sum(CASE WHEN j.EntryDate BETWEEN ? AND ? THEN d.Credit-d.Debit ELSE 0 END),0) AS الصافي
          FROM ChartOfAccounts a LEFT JOIN JournalEntryDetail d USING(AccountID)
          LEFT JOIN JournalEntry j ON j.JournalEntryID=d.JournalEntryID AND j.Status='POSTED'
          WHERE a.AccountType IN ('REVENUE','EXPENSE') GROUP BY a.AccountID ORDER BY a.AccountCode''',(start,end))]
        rows.append({'الحساب':'صافي الربح','النوع':'الصافي','الصافي':sum(r['الصافي'] for r in rows)})
    elif kind=='financial':
        rows=[dict(r) for r in db.rows('''SELECT f.AccountName AS الحساب,
          COALESCE(sum(CASE WHEN j.EntryDate<? THEN d.Debit-d.Credit ELSE 0 END),0) AS الافتتاحي,
          COALESCE(sum(CASE WHEN j.EntryDate BETWEEN ? AND ? THEN d.Debit ELSE 0 END),0) AS المقبوض,
          COALESCE(sum(CASE WHEN j.EntryDate BETWEEN ? AND ? THEN d.Credit ELSE 0 END),0) AS المدفوع
          FROM FinancialAccount f LEFT JOIN JournalEntryDetail d ON d.AccountID=f.PostingAccountID
          LEFT JOIN JournalEntry j ON j.JournalEntryID=d.JournalEntryID AND j.Status='POSTED'
          GROUP BY f.FinancialAccountID''',(start,start,end,start,end))]
        for row in rows: row['الختامي']=row['الافتتاحي']+row['المقبوض']-row['المدفوع']
    elif kind in ('customers','suppliers'):
        sales=kind=='customers'
        prefix='Sales' if sales else 'Purchase'
        party='Customer' if sales else 'Supplier'
        payment='CustomerReceipt' if sales else 'SupplierPayment'
        payment_day='ReceiptDate' if sales else 'PaymentDate'
        result=[]
        for p in db.rows(f'SELECT * FROM {party} ORDER BY Name'):
            ident=p[party+'ID']
            invoices=db.rows(f"SELECT * FROM {prefix}Invoice WHERE {party}ID=? AND Status='POSTED' AND InvoiceDate<=?",(ident,end))
            # Values are current net outstanding for invoices through this date;
            # returns and allocations follow the original engine's policy.
            net=sum(db.invoice_total(prefix,r[prefix+'InvoiceID']) for r in invoices if not sales or r['SaleType']=='CREDIT')
            paid=db.scalar(f"SELECT COALESCE(sum(Amount),0) FROM {payment} WHERE {party}ID=? AND Status='POSTED' AND {payment_day}<=?",(ident,end))
            result.append({'الطرف':p['Name'],'صافي_الفواتير':net,'المقبوض' if sales else 'المدفوع':paid,'المستحق_أو_المقدم':net-paid})
        return {'rows':result,'scales':{key:100 for row in result for key,value in row.items() if isinstance(value,int)},'asOf':'صافي المستحق الحالي للفواتير حتى تاريخ النهاية، بعد المرتجعات الحالية؛ الرصيد السالب مقدم.'}
    elif kind=='transit':
        return {'rows':[dict(r) for r in db.rows('SELECT * FROM StockInTransit')],
                'scales':{'ShippedQuantity':1000,'RemainingQuantity':1000},'asOf':'المخزون قيد النقل حالياً؛ لا يتبع فلتر التاريخ.'}
    elif kind=='stock':
        return {'rows':[dict(r) for r in db.rows('''SELECT w.Name AS المستودع,p.Name AS المنتج,b.ManufacturerLot AS الدفعة,b.ExpiryDate AS الصلاحية,s.CurrentQuantity AS الكمية,s.CostAmount AS القيمة
          FROM BatchStock s JOIN Warehouse w USING(WarehouseID) JOIN InventoryBatch b USING(BatchID) JOIN Product p USING(ProductID) ORDER BY w.Name,p.Name,b.BatchID''')], 'scales':{'الكمية':1000,'القيمة':100},'asOf':'أرصدة حالية؛ لا تتبع فلتر التاريخ.'}
    else:
        raise RuleError('تقرير غير معروف.')
    return {'rows':rows,'scales':{key:100 for row in rows for key,value in row.items() if isinstance(value,int)}}

def _authorize(db, user, action, r):
    """Every external command passes this check, including direct JSON calls."""
    if action in {'rows','record','export_rows','print_record','save','delete','post'}:
        table = r['table']
        operation = {'rows':'view','record':'view','export_rows':'export','print_record':'print',
                     'save':'update' if r.get('key') else 'create','delete':'delete','post':'post'}[action]
        security.table_check(user, table, operation)
        if operation in {'print','export'}:
            security.table_check(user, table, 'view')
        if action in {'save','delete'}:
            require(table not in READ_ONLY, 'السجل محمي؛ إدارة المستخدمين من شاشة الصلاحيات فقط.')
        if action == 'save':
            values = r['values']
            require(isinstance(values,dict), 'حقول غير صحيحة.')
            require(set(values) <= set(security.columns(user,table,values)), 'لا يسمح بتعديل حقول التكلفة المحجوبة.')
            old = security.accessible(db,user,table,r['key']) if r.get('key') else {}
            security.references(db,user,table,old | values)
            if table == 'SalesInvoiceDetail' and old and 'UnitPrice' in values:
                parsed = _parse(db,table,values,True)
                if parsed['UnitPrice'] != old['UnitPrice']:
                    security.check(user,'prices.change')
            if table in {'FinancialYear','AccountingPeriod'} and 'Status' in values:
                security.check(user,'period.close')
        elif action in {'record','print_record','delete'}:
            security.accessible(db,user,table,r['key'])
        elif action == 'post':
            doc = security.accessible(db,user,table,{_keys(db,table)[0]:r['id']})
            security.references(db,user,table,doc)
            if table in {'SalesReturn','PurchaseReturn'}:
                security.check(user,'returns.approve')
            if table == 'InventoryAdjustment':
                security.check(user,'stock.adjust')
    elif action == 'freeze':
        security.table_check(user,'InventoryCount','post')
        security.accessible(db,user,'InventoryCount',{'InventoryCountID':r['id']})
    elif action in {'manual','reverse'}:
        security.check(user,'journal.manual' if action=='manual' else 'journal.reverse')
        security.check(user,'cash.all')
        if action=='reverse':
            security.accessible(db,user,'JournalEntry',{'JournalEntryID':r['id']})
    elif action == 'report':
        kind = r['kind'];mode = r.get('mode','view')
        require(kind in security.REPORTS and mode in {'view','print','export'},'تقرير أو إجراء غير صحيح.')
        security.check(user,f'report.{kind}.view')
        security.check(user,f'report.{kind}.{mode}')
        if kind not in {'stock','transit'}:
            security.check(user,'data.all')
        if kind in {'income','trial'}:
            security.check(user,'costs.view');security.check(user,'profits.view')
        if kind=='financial': security.check(user,'cash.all')
    elif action in {'backup','backup_previous','restore','check'}:
        security.check(user,{'backup':'backup.create','backup_previous':'backup.create','restore':'backup.restore','check':'database.check'}[action])
    elif action in {'users','user_save'}:
        security.check(user,'users.manage')
    elif action not in {'schema','logout','password'}:
        raise RuleError('أمر غير معروف.')


def _dispatch(path, action, r):
    require(isinstance(r,dict),'طلب غير صحيح.')
    if action=='initialize':
        security.password_hash(r.get('password'))
        require(2<=len(str(r.get('username','')).strip())<=60,'أدخل اسم مستخدم للمدير.')
        initialize(path,r)
    if action=='restore' and not path.exists():
        return restore(path,path.parent/'import.sqlite')
    if action=='status' and not path.exists():
        return {'exists':False,'configured':False}
    require(path.exists(),'أنشئ قاعدة المتجر أو استورد ملف SQLite أولاً.')
    db=Database(path)
    try:
        security.ensure(db)
        if action=='status': return {'exists':True,'configured':security.configured(db)}
        if action in {'initialize','bootstrap'}: return security.bootstrap(db,r)
        if action=='login': return security.login(db,r)
        user=security.actor(db,r.get('_session'))
        db.security_user=user
        _authorize(db,user,action,r)
        if action=='logout':
            security.audit(db,'LOGOUT','AppUser',user['id'])
            security.SESSIONS.pop(r['_session'],None)
            return {'message':'تم تسجيل الخروج.'}
        if action=='password': return security.change_password(db,user,r)
        if action=='users': return security.user_catalog(db,user)
        if action=='user_save': return security.user_save(db,user,r)
        if action=='restore':
            result=restore(path,path.parent/'import.sqlite',user)
            security.invalidate(db)
            return result
        if action=='schema': return schema(db)
        if action=='rows': return _rows(db,r['table'],r.get('filters'),r.get('search',''),r.get('offset',0))
        if action=='export_rows':
            result=_rows(db,r['table'],r.get('filters'),r.get('search',''),0,10000)
            require(result['total']<=10000,'حد التصدير 10000 سجل؛ ضيّق البحث أولاً.')
            result['scales']={c['name']:100 if c['name'] in MONEY else 1000 for c in _columns(db,r['table']) if c['name'] in MONEY|QUANTITIES}
            security.audit(db,'EXPORT',''+r['table'],0,new={'Rows':len(result['rows'])})
            return result
        if action in {'record','print_record'}:
            where,args=_where(db,r['table'],r['key'],primary=True)
            row=db.conn.execute(f'SELECT * FROM "{r["table"]}" WHERE {where}',args).fetchone()
            require(row is not None,'السجل غير موجود.')
            value=dict(row)
            if 'PasswordHash' in value: value['PasswordHash']='••••••••'
            if r['table']=='SalesInvoice' or (r['table']=='PurchaseInvoice' and security.has(user,'costs.view')):
                kind='Sales' if r['table']=='SalesInvoice' else 'Purchase'
                ident=value[kind+'InvoiceID']
                total=db.invoice_total(kind,ident)
                paid=total if value.get('SaleType')=='CASH' else db.allocated(kind,ident)
                value['_summary']={'إجمالي الفاتورة بعد المرتجعات والشحن أو التوصيل':format(Decimal(total)/100,'.2f'),
                                   'المسدد أو المخصص':format(Decimal(paid)/100,'.2f'),'المتبقي':format(Decimal(total-paid)/100,'.2f')}
            if action=='print_record':
                lines=[]
                for child,(parent,field) in security.CHILDREN.items():
                    if parent!=r['table'] or not security.has(user,child+'.view'): continue
                    rows=_rows(db,child,{field:next(iter(r['key'].values()))},limit=10000)['rows']
                    lines.append({'table':child,'rows':rows})
                value['_lines']=lines
                security.audit(db,'PRINT',r['table'],int(next(iter(r['key'].values()))))
            return security.visible(user,r['table'],value)
        if action=='save': return save(db,r)
        if action=='delete':
            table=r['table'];require(table not in READ_ONLY,'السجل محمي.')
            where,args=_where(db,table,r['key'],primary=True)
            with db.transaction():
                old=db.conn.execute(f'SELECT * FROM "{table}" WHERE {where}',args).fetchone()
                require(old is not None and dict(old).get('Status')!='POSTED','السجل معتمد أو غير موجود.')
                db.conn.execute(f'DELETE FROM "{table}" WHERE {where}',args)
                _audit(db,table,int(next(iter(r['key'].values()))),'DELETE',dict(old),{})
            return {'message':'تم حذف المسودة أو السجل غير المستخدم.'}
        if action=='post':
            table=r['table'];require(table in SOURCES and table!='ManualJournal','مستند غير قابل للاعتماد.')
            ident=int(r['id'])
            if db.get(table,ident)['Status']=='POSTED': return {'message':'المستند معتمد بالفعل؛ لم يتكرر أثره.'}
            event=db.post(table,ident)
            return {'message':'تم اعتماد المستند وترحيل آثاره.','event':event}
        if action=='freeze':
            with db.transaction():
                db.freeze_count(int(r['id']))
                security.audit(db,'FREEZE','InventoryCount',int(r['id']))
            return {'message':'تم تثبيت لقطة الجرد.'}
        if action=='manual':
            lines=[(int(x['account']),money(x.get('debit','0')),money(x.get('credit','0'))) for x in r['lines']]
            require(all(d>=0 and c>=0 for _,d,c in lines),'قيم القيد غير صحيحة.')
            with db.transaction():
                ident=db.manual_entry(r['date'],lines,r['description'])
                source=db.scalar('SELECT SourceID FROM JournalEntry WHERE JournalEntryID=?',(ident,))
                security.ownership(db,user,'ManualJournal',source)
            return {'id':ident}
        if action=='reverse':
            original=int(r['id'])
            lines=[(x['AccountID'],x['Credit'],x['Debit']) for x in db.rows('SELECT * FROM JournalEntryDetail WHERE JournalEntryID=? ORDER BY JournalEntryDetailID',(original,))]
            with db.transaction():
                ident=db.manual_entry(r['date'],lines,r['description'],reversal_of=original)
                source=db.scalar('SELECT SourceID FROM JournalEntry WHERE JournalEntryID=?',(ident,))
                security.ownership(db,user,'ManualJournal',source)
                security.audit(db,'REVERSE','JournalEntry',original,new={'ReversalID':ident})
            return {'id':ident}
        if action=='report':
            result=report(db,r['kind'],r['from'],r['to'])
            if not security.has(user,'costs.view'):
                for row in result['rows']:
                    for key in security.COST_COLUMNS|{'القيمة'}: row.pop(key,None)
                for key in security.COST_COLUMNS|{'القيمة'}: result['scales'].pop(key,None)
            if r.get('mode') in {'print','export'}:
                security.audit(db,r['mode'].upper(),'report.'+r['kind'],0)
            return result
        if action=='check': db.check();return {'message':'القاعدة سليمة؛ القيود والأرصدة والحركات متطابقة.'}
        if action=='backup_previous':
            previous=path.parent/'before-restore.sqlite'
            require(previous.is_file(),'لا توجد نسخة سابقة للاستيراد.')
            security.audit(db,'BACKUP_PREVIOUS','MobileSecurity',1)
            return {'file':str(previous)}
        if action=='backup':
            security.audit(db,'BACKUP','MobileSecurity',1)
            dest_path=path.parent/'export.sqlite'
            dest=sqlite3.connect(dest_path)
            try: db.conn.backup(dest)
            finally: dest.close()
            return {'file':str(dest_path),'message':'تم تجهيز نسخة SQLite كاملة.'}
        raise RuleError('أمر غير معروف.')
    finally:
        if db: db.close()

def invoke(path, action, request='{}'):
    """Called by Chaquopy on one background executor, and by desktop tests."""
    try:
        with LOCK:
            result=_dispatch(Path(path),action,json.loads(request))
            return json.dumps({'ok':True,'data':result},ensure_ascii=False)
    except (RuleError,sqlite3.Error,ValueError,KeyError,TypeError,OSError) as error:
        return json.dumps({'ok':False,'error':str(error)},ensure_ascii=False)
