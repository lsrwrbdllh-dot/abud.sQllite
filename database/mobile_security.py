"""Offline authentication and authorization. Only the JSON boundary issues sessions.

The original financial schema is extended, never reset. Permissions are reloaded
on every command. Session secrets live in process memory, not in SQLite/backups.
"""
from datetime import date, datetime, timezone
from functools import lru_cache
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import time

from .build_schema import TABLES, SOURCES
from .engine import EFFECT_TABLES, RuleError, require
from .mobile_metadata import TABLE_LABELS

MIGRATION = Path(__file__).parent / 'migrations' / '002_mobile_security.sql'
SECURITY_TABLES = {'AppUser', 'Role', 'UserRole', 'Permission', 'RolePermission'}
READ_ONLY = EFFECT_TABLES | {'ManualJournal'} | SECURITY_TABLES
ROLES = {'manager': 'المدير', 'cashier': 'الكاشير', 'purchasing': 'مسؤول المشتريات',
         'stock': 'مسؤول المخزن', 'accountant': 'المحاسب'}
ACTIONS = {'view': 'عرض', 'create': 'إضافة', 'update': 'تعديل مسودة / بيانات',
           'delete': 'حذف مسودة / سجل غير مستخدم', 'post': 'اعتماد', 'print': 'طباعة', 'export': 'تصدير'}
SPECIAL = {
    'users.manage': 'إدارة المستخدمين وصلاحياتهم', 'data.all': 'عرض عمليات جميع الموظفين',
    'cash.all': 'استخدام جميع الصناديق والبنوك', 'costs.view': 'عرض أسعار التكلفة',
    'profits.view': 'عرض الأرباح والدفتر المحاسبي الكامل', 'prices.change': 'تغيير سعر سطر بيع محفوظ',
    'returns.approve': 'اعتماد المرتجعات', 'stock.adjust': 'اعتماد تسويات وعجز الجرد',
    'journal.manual': 'إنشاء واعتماد قيد يدوي', 'journal.reverse': 'عكس قيد يدوي',
    'period.close': 'إغلاق / إعادة فتح الفترات والسنوات',
    'backup.create': 'إنشاء نسخة SQLite كاملة', 'backup.restore': 'استعادة قاعدة SQLite',
    'database.check': 'فحص سلامة القاعدة',
}
REPORTS = {'trial': 'ميزان المراجعة', 'income': 'قائمة الدخل', 'financial': 'الصناديق والبنوك',
           'stock': 'المخزون الحالي', 'transit': 'المخزون قيد النقل',
           'customers': 'ذمم العملاء', 'suppliers': 'ذمم الموردين'}
CHILDREN = {
    'PurchaseInvoiceDetail': ('PurchaseInvoice', 'PurchaseInvoiceID'),
    'GoodsReceiptDetail': ('GoodsReceipt', 'GoodsReceiptID'),
    'FreightAllocation': ('PurchaseFreight', 'FreightID'),
    'InventoryBatch': ('GoodsReceiptDetail', 'GoodsReceiptDetailID'),
    'StockTransferDetail': ('StockTransfer', 'TransferID'),
    'StockTransferReceiptDetail': ('StockTransferReceipt', 'TransferReceiptID'),
    'InventoryCountDetail': ('InventoryCount', 'InventoryCountID'),
    'InventoryAdjustmentDetail': ('InventoryAdjustment', 'AdjustmentID'),
    'SalesInvoiceDetail': ('SalesInvoice', 'SalesInvoiceID'),
    'SalesReturnDetail': ('SalesReturn', 'SalesReturnID'),
    'PurchaseReturnDetail': ('PurchaseReturn', 'PurchaseReturnID'),
    'ReceiptAllocation': ('CustomerReceipt', 'ReceiptID'),
    'SupplierPaymentAllocation': ('SupplierPayment', 'SupplierPaymentID'),
    'PayrollDetail': ('Payroll', 'PayrollID'),
    'JournalEntryDetail': ('JournalEntry', 'JournalEntryID'),
}
DOCUMENTS = set(SOURCES) | {'InventoryCount'}
COST_COLUMNS = {'UnitCost', 'TotalCost', 'CostAmount', 'Cost'}
PURCHASE_COST_TABLES = {'PurchaseInvoiceDetail', 'PurchaseReturnDetail', 'PurchaseFreight', 'FreightAllocation'}
SESSIONS = {}
ATTEMPTS = {}
IDLE_SECONDS = 15 * 60
MAX_SECONDS = 8 * 60 * 60


def now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def audit(db, action, table, ident, old=None, new=None, user=None):
    def clean(value):
        return json.dumps({k: ('***' if 'password' in k.lower() or 'token' in k.lower() else v)
                           for k, v in (value or {}).items()}, ensure_ascii=False)
    db._insert('AuditLog', UserID=user if user is not None else getattr(db, 'actor_user_id', None),
               ActionType=action, EntityName=table, AffectedRecordID=int(ident),
               OldValues=clean(old), NewValues=clean(new), ActionAt=now())


@lru_cache(maxsize=1)
def catalog():
    result = dict(SPECIAL)
    for table in TABLES:
        for action, label in ACTIONS.items():
            if action in {'create', 'update', 'delete'} and table in READ_ONLY:
                continue
            if action == 'post' and table not in (set(SOURCES) - {'ManualJournal'}) | {'InventoryCount'}:
                continue
            result[f'{table}.{action}'] = f'{TABLE_LABELS[table]} — {label}'
    for kind, label in REPORTS.items():
        for action in ('view', 'print', 'export'):
            result[f'report.{kind}.{action}'] = f'تقرير {label} — {ACTIONS[action]}'
    return result


@lru_cache(maxsize=5)
def defaults(role):
    if role == 'manager':
        return set(catalog())
    result = set()
    def grant(names, actions):
        for table in names.split():
            for action in actions.split():
                code = f'{table}.{action}'
                if code in catalog():
                    result.add(code)
    grant('Branch Warehouse Category Product FinancialAccount FinancialAccountType', 'view')
    if role == 'cashier':
        grant('Customer', 'view create update')
        grant('SalesInvoice SalesInvoiceDetail CustomerReceipt ReceiptAllocation', 'view create update post print')
        grant('SalesReturn SalesReturnDetail', 'view create update print')
        grant('InventoryBalance InventoryBatch', 'view')
    elif role == 'purchasing':
        grant('Supplier SupplierProduct PurchaseInvoice PurchaseInvoiceDetail PurchaseFreight FreightAllocation PurchaseReturn PurchaseReturnDetail',
              'view create update print export')
        grant('PurchaseInvoice PurchaseFreight', 'post')
        grant('GoodsReceipt GoodsReceiptDetail InventoryBatch', 'view')
        result |= {'data.all', 'costs.view', 'report.suppliers.view'}
    elif role == 'stock':
        grant('Category Product GoodsReceipt GoodsReceiptDetail InventoryBatch StockTransfer StockTransferDetail StockTransferReceipt StockTransferReceiptDetail InventoryCount InventoryCountDetail InventoryAdjustment InventoryAdjustmentDetail',
              'view create update print export')
        grant('GoodsReceipt StockTransfer StockTransferReceipt InventoryCount', 'post')
        grant('PurchaseInvoice PurchaseInvoiceDetail InventoryBalance BatchStock InventoryMovement StockAllocation', 'view')
        result |= {'data.all', 'report.stock.view', 'report.stock.print', 'report.stock.export', 'report.transit.view'}
    elif role == 'accountant':
        grant('Customer Supplier Employee ExpenseCategory FinancialAccount FinancialAccountType ChartOfAccounts AccountingPolicy FinancialYear AccountingPeriod',
              'view')
        grant('Expense ExpensePayment Payroll PayrollDetail SalaryPayment CustomerReceipt ReceiptAllocation SupplierPayment SupplierPaymentAllocation FinancialTransfer FixedAsset AssetDepreciation AssetDisposal',
              'view create update post print export')
        grant('JournalEntry JournalEntryDetail ManualJournal PostingEvent FinancialTransaction SalesInvoice SalesInvoiceDetail PurchaseInvoice PurchaseInvoiceDetail SalesReturn PurchaseReturn AuditLog',
              'view print export')
        result |= {'data.all', 'cash.all', 'costs.view', 'profits.view', 'journal.manual', 'database.check'}
        result |= {f'report.{kind}.{action}' for kind in REPORTS for action in ('view', 'print', 'export')}
    return result


def ensure(db):
    exists = db.scalar("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='MobileSecurity'")
    if exists and db.scalar("SELECT count(*) FROM Role WHERE RoleName LIKE 'mobile:%'") == 5:
        return
    if not exists:
        db.conn.executescript(MIGRATION.read_text(encoding='utf-8'))
    # Idempotent catalog seeding. Never overwrite the administrator's user overrides.
    with db.transaction():
        for code, label in catalog().items():
            db.conn.execute('INSERT OR IGNORE INTO Permission(PermissionName,PermissionCode) VALUES(?,?)', (label, code))
        for code, label in ROLES.items():
            name = 'mobile:' + code
            db.conn.execute('INSERT OR IGNORE INTO Role(RoleName,Description) VALUES(?,?)', (name, label))
            rid = db.scalar('SELECT RoleID FROM Role WHERE RoleName=?', (name,))
            for permission in defaults(code):
                db.conn.execute('INSERT OR IGNORE INTO RolePermission SELECT ?,PermissionID FROM Permission WHERE PermissionCode=?', (rid, permission))


def configured(db):
    return bool(db.scalar('SELECT Configured FROM MobileSecurity WHERE SettingID=1'))


def password_hash(password):
    require(isinstance(password, str) and 8 <= len(password) <= 256, 'كلمة المرور من 8 إلى 256 حرفاً.')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 210000).hex()
    return f'pbkdf2_sha256$210000${salt}${digest}'


def verify(password, encoded):
    if not isinstance(password, str) or len(password) > 256:
        return False
    try:
        algorithm, rounds, salt, expected = encoded.split('$')
        if algorithm != 'pbkdf2_sha256' or not 100000 <= int(rounds) <= 1000000:
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), int(rounds)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, AttributeError):
        return False


def _path(db):
    return str(Path(db.rows('PRAGMA database_list')[0]['file']).resolve())


def invalidate(db, user=None):
    path = _path(db)
    for token, session in list(SESSIONS.items()):
        if session['path'] == path and (user is None or session['user'] == user):
            del SESSIONS[token]


def _session(db, user):
    token = secrets.token_urlsafe(32)
    stamp = time.monotonic()
    SESSIONS[token] = {'path': _path(db), 'user': user, 'created': stamp, 'last': stamp}
    return {'token': token, 'username': db.scalar('SELECT Username FROM AppUser WHERE UserID=?', (user,))}


def actor(db, token):
    session = SESSIONS.get(token) if isinstance(token, str) else None
    stamp = time.monotonic()
    require(session is not None and session['path'] == _path(db) and
            stamp-session['last'] <= IDLE_SECONDS and stamp-session['created'] <= MAX_SECONDS,
            'انتهت الجلسة؛ سجّل الدخول من جديد.')
    user = db.conn.execute('SELECT UserID,Username,IsActive FROM AppUser WHERE UserID=?', (session['user'],)).fetchone()
    require(user is not None and user['IsActive'], 'الحساب موقوف؛ سجّل الدخول بحساب فعال.')
    session['last'] = stamp
    uid = user['UserID']
    manager = bool(db.scalar("SELECT count(*) FROM UserRole u JOIN Role r USING(RoleID) WHERE u.UserID=? AND r.RoleName='mobile:manager'", (uid,)))
    permissions = {r[0] for r in db.rows('''SELECT DISTINCT p.PermissionCode FROM UserRole u
        JOIN RolePermission rp USING(RoleID) JOIN Permission p USING(PermissionID) WHERE u.UserID=?''', (uid,))}
    for row in db.rows('SELECT p.PermissionCode,o.Allowed FROM MobileUserPermission o JOIN Permission p USING(PermissionID) WHERE UserID=?', (uid,)):
        if row['Allowed']:
            permissions.add(row['PermissionCode'])
        else:
            permissions.discard(row['PermissionCode'])
    db.actor_user_id = uid
    return {'id': uid, 'username': user['Username'], 'manager': manager, 'permissions': permissions}


def has(user, permission):
    return user['manager'] or permission in user['permissions']


def check(user, permission):
    require(has(user, permission), 'ليس لديك صلاحية: ' + catalog().get(permission, permission))


def table_check(user, table, action='view'):
    require(table in TABLES, 'جدول غير معروف.')
    check(user, f'{table}.{action}')
    if table in SECURITY_TABLES:
        check(user, 'users.manage')
    if table in {'JournalEntry', 'JournalEntryDetail', 'ManualJournal', 'AuditLog'}:
        check(user, 'costs.view')
        check(user, 'profits.view')


def columns(user, table, names):
    if has(user, 'costs.view'):
        return list(names)
    hidden = COST_COLUMNS | ({'UnitPrice', 'Amount', 'AllocatedAmount'} if table in PURCHASE_COST_TABLES else set())
    return [name for name in names if name not in hidden]


def visible(user, table, row):
    return {key: value for key, value in row.items() if key in columns(user, table, row)}


def pk(db, table):
    return next(row['name'] for row in db.rows(f'PRAGMA table_info("{table}")') if row['pk'])


def scope(db, user, table):
    """A SQL predicate shared by listing, counts, searches, details and writes."""
    if not has(user, 'data.all'):
        if table == 'AuditLog':
            own, args = '"AuditLog".UserID=?', (user['id'],)
        elif table in CHILDREN:
            parent, field = CHILDREN[table]
            predicate, args = scope(db, user, parent)
            own = f'"{table}"."{field}" IN (SELECT "{pk(db,parent)}" FROM "{parent}" WHERE {predicate})'
        elif table in DOCUMENTS:
            own = f'"{table}"."{pk(db,table)}" IN (SELECT RecordID FROM MobileRecordOwner WHERE EntityName=? AND UserID=?)'
            args = (table, user['id'])
        elif table in {'JournalEntry', 'PostingEvent', 'FinancialTransaction'}:
            own = f'EXISTS(SELECT 1 FROM MobileRecordOwner o WHERE o.EntityName="{table}".SourceType AND o.RecordID="{table}".SourceID AND o.UserID=?)'
            args = (user['id'],)
        elif table in {'InventoryMovement', 'StockAllocation'}:
            predicate, args = scope(db, user, 'PostingEvent')
            own = f'"{table}".EventID IN (SELECT EventID FROM PostingEvent WHERE {predicate})'
        else:
            own, args = '1', ()
    else:
        own, args = '1', ()
    if not has(user, 'cash.all'):
        fields = [r['from'] for r in db.rows(f'PRAGMA foreign_key_list("{table}")') if r['table'] == 'FinancialAccount']
        if table == 'FinancialAccount':
            fields.append('FinancialAccountID')
        for field in fields:
            own += f' AND ("{table}"."{field}" IS NULL OR "{table}"."{field}" IN (SELECT FinancialAccountID FROM MobileUserCash WHERE UserID=?))'
            args += (user['id'],)
    return own, args


def accessible(db, user, table, key):
    require(table in TABLES, 'جدول غير معروف.')
    names = {r['name'] for r in db.rows(f'PRAGMA table_info("{table}")') if r['pk']}
    require(isinstance(key, dict) and set(key) == names, 'مفتاح السجل غير صحيح.')
    predicate, args = scope(db, user, table)
    predicate += ' AND ' + ' AND '.join(f'"{table}"."{name}" IS ?' for name in key)
    row = db.conn.execute(f'SELECT * FROM "{table}" WHERE {predicate}', args + tuple(key.values())).fetchone()
    require(row is not None, 'السجل غير موجود أو خارج صلاحياتك.')
    return dict(row)


def references(db, user, table, values):
    for fk in db.rows(f'PRAGMA foreign_key_list("{table}")'):
        value = values.get(fk['from'])
        if value not in (None, ''):
            accessible(db, user, fk['table'], {fk['to'] or pk(db,fk['table']): value})


def ownership(db, user, table, ident):
    if table in DOCUMENTS:
        db.conn.execute('INSERT OR REPLACE INTO MobileRecordOwner VALUES(?,?,?)', (table, ident, user['id']))


def bootstrap(db, request):
    require(not configured(db), 'تم إعداد المدير بالفعل؛ استخدم تسجيل الدخول.')
    name = str(request.get('username', '')).strip()
    require(2 <= len(name) <= 60, 'اسم المستخدم من 2 إلى 60 حرفاً.')
    hashed = password_hash(request.get('password'))
    with db.transaction():
        branch = db.scalar('SELECT min(BranchID) FROM Branch')
        if branch is None: branch = db.add('Branch', Name='المتجر')
        eid = db.add('Employee', BranchID=branch, EmployeeName=name, JobTitle='مدير النظام', HireDate=date.today().isoformat())
        uid = db.add('AppUser', EmployeeID=eid, Username=name, PasswordHash=hashed, CreatedAt=now())
        rid = db.scalar("SELECT RoleID FROM Role WHERE RoleName='mobile:manager'")
        db.add('UserRole', UserID=uid, RoleID=rid)
        db.conn.execute('UPDATE MobileSecurity SET Configured=1 WHERE SettingID=1')
        audit(db, 'SECURITY_SETUP', 'AppUser', uid, new={'Username': name, 'Role': 'manager'}, user=uid)
    return _session(db, uid)


def login(db, request):
    require(configured(db), 'أنشئ حساب المدير أولاً.')
    name = str(request.get('username', '')).strip()
    attempt_key = (_path(db), name.casefold())
    count, until = ATTEMPTS.get(attempt_key, (0, 0))
    require(time.monotonic() >= until, 'محاولات كثيرة؛ انتظر دقيقة ثم حاول مجدداً.')
    row = db.conn.execute('SELECT * FROM AppUser WHERE Username=?', (name,)).fetchone()
    # A dummy hash makes unknown-user checks perform the same PBKDF work.
    encoded = row['PasswordHash'] if row else 'pbkdf2_sha256$210000$00000000000000000000000000000000$' + '0'*64
    valid = verify(request.get('password'), encoded)
    if not (row is not None and row['IsActive'] and valid):
        count += 1
        ATTEMPTS[attempt_key] = (count, time.monotonic()+60 if count >= 5 else 0)
        raise RuleError('اسم المستخدم أو كلمة المرور غير صحيحين، أو الحساب موقوف.')
    ATTEMPTS.pop(attempt_key, None)
    audit(db, 'LOGIN', 'AppUser', row['UserID'], user=row['UserID'])
    return _session(db, row['UserID'])


def user_catalog(db, user):
    check(user, 'users.manage')
    records = []
    for row in db.rows('SELECT u.UserID,u.Username,u.IsActive,e.EmployeeName FROM AppUser u JOIN Employee e USING(EmployeeID) ORDER BY u.UserID'):
        value = dict(row)
        value['roles'] = [r[0].removeprefix('mobile:') for r in db.rows('SELECT RoleName FROM UserRole JOIN Role USING(RoleID) WHERE UserID=?', (row['UserID'],)) if r[0].startswith('mobile:')]
        value['overrides'] = {r[0]: bool(r[1]) for r in db.rows('SELECT PermissionCode,Allowed FROM MobileUserPermission JOIN Permission USING(PermissionID) WHERE UserID=?', (row['UserID'],))}
        value['cash'] = [r[0] for r in db.rows('SELECT FinancialAccountID FROM MobileUserCash WHERE UserID=?', (row['UserID'],))]
        records.append(value)
    return {'users': records, 'roles': ROLES, 'permissions': catalog(),
            'defaults': {role: sorted(defaults(role)) for role in ROLES},
            'accounts': [dict(r) for r in db.rows('SELECT FinancialAccountID,AccountName FROM FinancialAccount')]}


def user_save(db, user, request):
    check(user, 'users.manage')
    uid = request.get('id')
    require(uid is None or (type(uid) is int and uid > 0), 'رقم مستخدم غير صحيح.')
    role = request.get('role')
    require(role in ROLES, 'اختر دوراً صحيحاً.')
    # Only a manager may create another manager, or edit a manager account.
    is_manager = uid and db.scalar("SELECT count(*) FROM UserRole JOIN Role USING(RoleID) WHERE UserID=? AND RoleName='mobile:manager'", (uid,))
    require(user['manager'] or (role != 'manager' and not is_manager), 'تعديل المدير متاح للمدير فقط.')
    overrides = request.get('overrides', {})
    require(isinstance(overrides, dict) and set(overrides) <= set(catalog()) and all(type(v) is bool for v in overrides.values()), 'صلاحيات مخصصة غير صحيحة.')
    # A delegated employee manager cannot grant privileges they do not hold.
    if not user['manager']:
        effective = (defaults(role) | {k for k,v in overrides.items() if v}) - {k for k,v in overrides.items() if not v}
        require(effective <= user['permissions'], 'لا يمكنك منح صلاحيات لا تملكها.')
    name = str(request.get('username', '')).strip()
    employee = str(request.get('name', '')).strip()
    require(2 <= len(name) <= 60 and employee, 'أدخل اسم الموظف واسم مستخدم من 2 إلى 60 حرفاً.')
    active = request.get('active', True)
    require(type(active) is bool, 'حالة الحساب غير صحيحة.')
    cash = request.get('cash', [])
    require(isinstance(cash, list) and all(type(v) is int for v in cash) and len(cash) == len(set(cash)), 'الصناديق غير صحيحة.')
    for account in cash:
        require(db.scalar('SELECT count(*) FROM FinancialAccount WHERE FinancialAccountID=?', (account,)), 'الصندوق غير موجود.')
        if not user['manager'] and not has(user, 'cash.all'):
            accessible(db, user, 'FinancialAccount', {'FinancialAccountID': account})
    hashed = password_hash(request['password']) if request.get('password') else None
    with db.transaction():
        old = None
        if uid:
            old = db.get('AppUser', int(uid))
            old = dict(old)
            old['Roles'] = [r[0] for r in db.rows('SELECT RoleName FROM UserRole JOIN Role USING(RoleID) WHERE UserID=?', (uid,))]
            old['Overrides'] = {r[0]:bool(r[1]) for r in db.rows('SELECT PermissionCode,Allowed FROM MobileUserPermission JOIN Permission USING(PermissionID) WHERE UserID=?', (uid,))}
            old['Cash'] = [r[0] for r in db.rows('SELECT FinancialAccountID FROM MobileUserCash WHERE UserID=?', (uid,))]
            db.conn.execute('UPDATE Employee SET EmployeeName=? WHERE EmployeeID=?', (employee, old['EmployeeID']))
            db.conn.execute('UPDATE AppUser SET Username=?,IsActive=?,PasswordHash=? WHERE UserID=?',
                            (name, int(active), hashed or old['PasswordHash'], uid))
        else:
            require(hashed, 'أدخل كلمة مرور للحساب الجديد.')
            branch = db.scalar('SELECT min(BranchID) FROM Branch')
            eid = db.add('Employee', BranchID=branch, EmployeeName=employee, JobTitle=ROLES[role], HireDate=date.today().isoformat())
            uid = db.add('AppUser', EmployeeID=eid, Username=name, PasswordHash=hashed, IsActive=int(active), CreatedAt=now())
        db.conn.execute('DELETE FROM UserRole WHERE UserID=?', (uid,))
        db.add('UserRole', UserID=uid, RoleID=db.scalar('SELECT RoleID FROM Role WHERE RoleName=?', ('mobile:'+role,)))
        for table in ('MobileUserPermission', 'MobileUserCash'):
            db.conn.execute(f'DELETE FROM {table} WHERE UserID=?', (uid,))
        for code, allowed in overrides.items():
            db.conn.execute('INSERT INTO MobileUserPermission VALUES(?,?,?)', (uid, db.scalar('SELECT PermissionID FROM Permission WHERE PermissionCode=?', (code,)), int(allowed)))
        for account in cash:
            db.conn.execute('INSERT INTO MobileUserCash VALUES(?,?)', (uid, account))
        require(db.scalar("SELECT count(DISTINCT u.UserID) FROM AppUser u JOIN UserRole ur USING(UserID) JOIN Role r USING(RoleID) WHERE u.IsActive=1 AND r.RoleName='mobile:manager'"),
                'يجب إبقاء مدير نشط واحد على الأقل.')
        audit(db, 'USER_UPDATE' if old else 'USER_CREATE', 'AppUser', uid,
              old={k:old[k] for k in ('Username','IsActive','Roles','Overrides','Cash')} if old else None,
              new={'Username': name, 'IsActive': active, 'Role': role, 'Overrides': overrides,
                   'Cash': cash, 'PasswordChanged': bool(hashed)})
    invalidate(db, int(uid))
    return {'id': uid, 'message': 'تم حفظ المستخدم وصلاحياته. يلزم تسجيل دخوله مجدداً.'}


def change_password(db, user, request):
    old = db.scalar('SELECT PasswordHash FROM AppUser WHERE UserID=?', (user['id'],))
    require(verify(request.get('old'), old), 'كلمة المرور الحالية غير صحيحة.')
    hashed = password_hash(request.get('password'))
    with db.transaction():
        db.conn.execute('UPDATE AppUser SET PasswordHash=? WHERE UserID=?', (hashed, user['id']))
        audit(db, 'PASSWORD_CHANGE', 'AppUser', user['id'])
    invalidate(db, user['id'])
    return {'message': 'تم تغيير كلمة المرور؛ سجّل الدخول مجدداً.'}
