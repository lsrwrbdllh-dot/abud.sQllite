"""Adversarial authorization checks through the same JSON boundary as the APK."""
from datetime import date
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from database.engine import Database
from database.mobile_bridge import invoke
from database import mobile_security as sec


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'store.sqlite'
        db = Database(self.path); db.migrate(); db.seed(); db.close()
        self.admin = self.ok(None, 'bootstrap', username='admin', password='admin-pass-123')['token']

    def raw(self, token, action, **request):
        if token: request['_session'] = token
        return json.loads(invoke(str(self.path), action, json.dumps(request, ensure_ascii=False)))

    def ok(self, token, action, **request):
        result = self.raw(token, action, **request)
        self.assertTrue(result['ok'], result)
        return result['data']

    def no(self, token, action, **request):
        result = self.raw(token, action, **request)
        self.assertFalse(result['ok'], result)
        return result['error']

    def sql(self, sql, args=()):
        db = sqlite3.connect(self.path)
        try: return db.execute(sql, args).fetchall()
        finally: db.close()

    def employee(self, name='cashier', role='cashier', overrides=None, cash=None):
        uid = self.ok(self.admin, 'user_save', name=name, username=name, password='employee-pass',
                      role=role, overrides=overrides or {}, cash=[1] if cash is None else cash)['id']
        return uid, self.ok(None, 'login', username=name, password='employee-pass')['token']

    def add(self, token, table, **values):
        return next(iter(self.ok(token, 'save', table=table, values=values)['key'].values()))

    def invoice(self, token):
        return self.add(token, 'SalesInvoice', BranchID='1', WarehouseID='1', InvoiceDate='2026-01-02', SaleType='CASH', FinancialAccountID='1')

    def demo(self):
        from database.demo import populate
        db = Database(self.path); populate(db); db.close()

    def test_no_unauthenticated_command_or_forged_identity(self):
        requests = [('schema', {}), ('rows', {'table':'Customer'}), ('record', {'table':'AppUser','key':{'UserID':1}}),
                    ('save', {'table':'Customer','values':{'Name':'Injected'}}), ('backup', {}), ('backup_previous', {}),
                    ('restore', {}), ('check', {}), ('users', {}), ('user_save', {}), ('manual', {}), ('post', {})]
        for action, request in requests:
            with self.subTest(action=action):
                self.no(None, action, **request)
                self.no('invented-session', action, UserID=1, **request)
        self.assertTrue(self.ok(None,'status')['configured'])
        self.assertEqual(self.sql("SELECT count(*) FROM Customer WHERE Name='Injected'")[0][0],0)

    def test_original_database_upgrades_without_financial_changes_and_bootstrap_once(self):
        self.demo()
        before=self.sql('SELECT * FROM FinancialTransaction')
        self.no(None,'bootstrap',username='takeover',password='takeover-pass')
        self.ok(self.admin,'schema');self.ok(self.admin,'schema')
        self.assertEqual(before,self.sql('SELECT * FROM FinancialTransaction'))
        self.assertEqual(self.sql('SELECT max(Version) FROM SchemaMigration')[0][0],1)
        self.assertEqual(self.sql('SELECT Version FROM MobileSecurity')[0][0],1)

    def test_default_five_roles_and_cashier_restrictions(self):
        self.assertEqual(set(self.ok(self.admin,'users')['roles']),set(sec.ROLES))
        for role in ('cashier','purchasing','stock','accountant'):
            _,token=self.employee(role,role)
            schema=self.ok(token,'schema')
            self.assertFalse(schema['user']['manager'])
            self.no(token,'users');self.no(token,'backup');self.no(token,'restore')
        _,token=self.employee('seller')
        for table in ('PurchaseInvoice','Expense','JournalEntry','AppUser','AuditLog'):
            self.no(token,'rows',table=table)
        self.no(token,'manual',date='2026-01-02',description='bad',lines=[])

    def test_own_documents_search_counts_details_children_and_reparenting(self):
        uid,a=self.employee('alpha');_,b=self.employee('bravo')
        first=self.invoice(a);second=self.invoice(b)
        detail=self.add(a,'SalesInvoiceDetail',SalesInvoiceID=str(first),ProductID='1',Quantity='1',UnitPrice='9.99')
        self.assertEqual(self.ok(a,'rows',table='SalesInvoice')['total'],1)
        self.assertEqual(self.ok(b,'rows',table='SalesInvoiceDetail')['total'],0)
        self.no(b,'record',table='SalesInvoice',key={'SalesInvoiceID':first})
        self.no(b,'record',table='SalesInvoiceDetail',key={'SalesInvoiceDetailID':detail})
        self.no(b,'save',table='SalesInvoiceDetail',values={'SalesInvoiceID':str(first),'ProductID':'1','Quantity':'1','UnitPrice':'1'})
        self.no(a,'save',table='SalesInvoiceDetail',key={'SalesInvoiceDetailID':detail},values={'SalesInvoiceID':str(second)})
        self.assertEqual(self.sql("SELECT UserID FROM MobileRecordOwner WHERE EntityName='SalesInvoice' AND RecordID=?",(first,))[0][0],uid)

    def test_all_employee_scope_override_and_immediate_revocation(self):
        uid,a=self.employee('alpha');_,b=self.employee('bravo')
        self.invoice(a);self.invoice(b)
        self.ok(self.admin,'user_save',id=uid,name='alpha',username='alpha',role='cashier',cash=[1],overrides={'data.all':True})
        self.no(a,'schema')
        a=self.ok(None,'login',username='alpha',password='employee-pass')['token']
        self.assertEqual(self.ok(a,'rows',table='SalesInvoice')['total'],2)
        self.ok(self.admin,'user_save',id=uid,name='alpha',username='alpha',role='cashier',cash=[1],overrides={'data.all':False})
        self.no(a,'rows',table='SalesInvoice')
        a=self.ok(None,'login',username='alpha',password='employee-pass')['token']
        self.assertEqual(self.ok(a,'rows',table='SalesInvoice')['total'],1)

    def test_cash_account_scope_is_checked_for_reads_saves_and_posting(self):
        _,token=self.employee()
        self.assertEqual([r['FinancialAccountID'] for r in self.ok(token,'rows',table='FinancialAccount')['rows']],[1])
        self.no(token,'record',table='FinancialAccount',key={'FinancialAccountID':2})
        self.no(token,'save',table='SalesInvoice',values={'BranchID':'1','WarehouseID':'1','InvoiceDate':'2026-01-02','SaleType':'CASH','FinancialAccountID':'2'})
        ident=self.invoice(token)
        db=sqlite3.connect(self.path);db.execute('UPDATE SalesInvoice SET FinancialAccountID=2 WHERE SalesInvoiceID=?',(ident,));db.commit();db.close()
        self.no(token,'post',table='SalesInvoice',id=ident)
        self.assertEqual(self.sql('SELECT count(*) FROM PostingEvent')[0][0],0)

    def test_generic_security_crud_and_sql_injection_are_blocked_even_for_manager(self):
        for table in sec.SECURITY_TABLES:
            self.no(self.admin,'save',table=table,values={'Username':'hacker'})
            self.no(self.admin,'delete',table=table,key={'UserID':1})
        self.no(self.admin,'rows',table='Customer; DROP TABLE AppUser')
        self.no(self.admin,'rows',table='Customer',filters={'Name OR 1=1':'x'})

    def test_costs_removed_from_schema_rows_details_summaries_print_export_and_reports(self):
        self.demo();_,token=self.employee('warehouse','stock')
        schema={t['name']:t for t in self.ok(token,'schema')['tables']}
        self.assertNotIn('UnitPrice',[c['name'] for c in schema['PurchaseInvoiceDetail']['columns']])
        self.assertNotIn('UnitCost',[c['name'] for c in schema['InventoryBatch']['columns']])
        self.assertNotIn('_summary',self.ok(token,'record',table='PurchaseInvoice',key={'PurchaseInvoiceID':1}))
        for action in ('rows','export_rows'):
            rows=self.ok(token,action,table='InventoryBatch')['rows']
            self.assertTrue(rows)
            self.assertTrue(all('UnitCost' not in row and 'TotalCost' not in row for row in rows))
        row=self.ok(token,'print_record',table='InventoryBatch',key={'BatchID':1})
        self.assertNotIn('UnitCost',row)
        self.no(token,'rows',table='PurchaseInvoiceDetail',filters={'UnitPrice':1234})
        result=self.ok(token,'report',kind='stock',**{'from':'2026-01-01','to':'2026-12-31'})
        self.assertTrue(result['rows']);self.assertNotIn('القيمة',result['rows'][0])

    def test_independent_view_create_edit_delete_post_print_export_permissions(self):
        _,token=self.employee(overrides={'SalesInvoice.update':False,'SalesInvoice.post':False,'SalesInvoice.print':False})
        ident=self.invoice(token)
        self.ok(token,'record',table='SalesInvoice',key={'SalesInvoiceID':ident})
        self.no(token,'save',table='SalesInvoice',key={'SalesInvoiceID':ident},values={'InvoiceDate':'2026-01-03'})
        self.no(token,'post',table='SalesInvoice',id=ident)
        self.no(token,'delete',table='SalesInvoice',key={'SalesInvoiceID':ident})
        self.no(token,'print_record',table='SalesInvoice',key={'SalesInvoiceID':ident})
        self.no(token,'export_rows',table='SalesInvoice')

    def test_return_and_stock_adjustment_approval_need_separate_sensitive_permissions(self):
        self.demo()
        _,token=self.employee(overrides={'data.all':True,'SalesReturn.post':True})
        self.no(token,'post',table='SalesReturn',id=1)
        db=Database(self.path)
        count=db.add('InventoryCount',WarehouseID=1,CountDate='2026-01-20')
        adjustment=db.add('InventoryAdjustment',InventoryCountID=count,AdjustmentDate='2026-01-20',Reason='test')
        db.close()
        _,token=self.employee('stock','stock',overrides={'InventoryAdjustment.post':True})
        self.no(token,'post',table='InventoryAdjustment',id=adjustment)

    def test_existing_sale_price_change_requires_its_own_permission(self):
        uid,token=self.employee();invoice=self.invoice(token)
        line=self.add(token,'SalesInvoiceDetail',SalesInvoiceID=str(invoice),ProductID='1',Quantity='1',UnitPrice='10')
        self.ok(token,'save',table='SalesInvoiceDetail',key={'SalesInvoiceDetailID':line},values={'Quantity':'2'})
        self.no(token,'save',table='SalesInvoiceDetail',key={'SalesInvoiceDetailID':line},values={'UnitPrice':'9'})
        self.ok(self.admin,'user_save',id=uid,name='cashier',username='cashier',role='cashier',cash=[1],overrides={'prices.change':True})
        token=self.ok(None,'login',username='cashier',password='employee-pass')['token']
        self.ok(token,'save',table='SalesInvoiceDetail',key={'SalesInvoiceDetailID':line},values={'UnitPrice':'9'})

    def test_period_closing_and_global_profit_reports_need_sensitive_permissions(self):
        _,token=self.employee(overrides={'AccountingPeriod.update':True,'report.income.view':True,'data.all':True})
        self.no(token,'save',table='AccountingPeriod',key={'AccountingPeriodID':1},values={'Status':'CLOSED'})
        self.no(token,'report',kind='income',**{'from':'2026-01-01','to':'2026-12-31'})

    def test_post_and_automatic_payment_and_manual_reversal_are_attributed(self):
        expense=self.add(self.admin,'Expense',BranchID='1',ExpenseCategoryID='1',ExpenseDate='2026-01-02',Amount='10',Description='test',FinancialAccountID='1')
        self.ok(self.admin,'post',table='Expense',id=expense)
        original=self.ok(self.admin,'manual',date='2026-01-02',description='capital',lines=[{'account':17,'debit':'10','credit':'0'},{'account':20,'debit':'0','credit':'10'}])['id']
        self.ok(self.admin,'reverse',id=original,date='2026-01-03',description='correction')
        rows=self.sql("SELECT UserID FROM AuditLog WHERE ActionType IN ('POST','REVERSE')")
        self.assertGreaterEqual(len(rows),5);self.assertTrue(all(row[0]==1 for row in rows))
        self.no(self.admin,'delete',table='Expense',key={'ExpenseID':expense})
        self.no(self.admin,'save',table='JournalEntry',key={'JournalEntryID':original},values={'Description':'tamper'})
        self.ok(self.admin,'check')

    def test_disabled_user_and_password_reset_invalidate_all_existing_sessions(self):
        uid,token=self.employee();other=self.ok(None,'login',username='cashier',password='employee-pass')['token']
        self.ok(self.admin,'user_save',id=uid,name='cashier',username='cashier',role='cashier',active=False,cash=[1])
        self.no(token,'schema');self.no(other,'schema');self.no(None,'login',username='cashier',password='employee-pass')
        self.ok(self.admin,'user_save',id=uid,name='cashier',username='cashier',role='cashier',active=True,password='changed-pass',cash=[1])
        self.no(None,'login',username='cashier',password='employee-pass')
        self.ok(None,'login',username='cashier',password='changed-pass')

    def test_last_active_manager_cannot_be_disabled_or_demoted(self):
        for role,active in [('cashier',True),('manager',False)]:
            self.no(self.admin,'user_save',id=1,name='admin',username='admin',role=role,active=active)
        self.ok(self.admin,'schema')
        self.employee('second-manager','manager')
        self.ok(self.admin,'user_save',id=1,name='admin',username='admin',role='cashier',active=True)
        self.no(self.admin,'schema')

    def test_password_change_hash_salt_and_audit_do_not_expose_secrets(self):
        uid,token=self.employee()
        self.no(token,'password',old='wrong',password='new-password')
        self.ok(token,'password',old='employee-pass',password='new-password')
        self.no(token,'schema');self.no(None,'login',username='cashier',password='employee-pass')
        self.ok(None,'login',username='cashier',password='new-password')
        content=str(self.sql('SELECT OldValues,NewValues FROM AuditLog'))
        for secret in ('employee-pass','new-password','admin-pass-123'):
            self.assertNotIn(secret,content)
        self.assertNotEqual(sec.password_hash('same-password'),sec.password_hash('same-password'))

    def test_logout_expiry_and_session_bound_to_database(self):
        _,token=self.employee();stamp=sec.SESSIONS[token]['last']
        other=Path(self.temp.name)/'other.sqlite'
        db=Database(other);db.migrate();db.seed();db.close()
        invoke(str(other),'status')
        cross=json.loads(invoke(str(other),'schema',json.dumps({'_session':token})))
        self.assertFalse(cross['ok'])
        with patch('database.mobile_security.time.monotonic',return_value=stamp+sec.IDLE_SECONDS+1):
            self.no(token,'schema')
        self.ok(token,'logout');self.no(token,'schema')
        self.ok(self.admin,'schema')

    def test_login_throttling_and_no_built_in_password(self):
        self.no(None,'login',username='admin',password='admin')
        for _ in range(5): self.no(None,'login',username='missing',password='wrong-pass')
        self.assertIn('انتظر',self.no(None,'login',username='missing',password='wrong-pass'))

    def test_backup_restore_preserves_security_and_ends_sessions(self):
        _,token=self.employee();backup=self.ok(self.admin,'backup')['file']
        Path(self.temp.name,'import.sqlite').write_bytes(Path(backup).read_bytes())
        self.ok(self.admin,'restore');self.no(token,'schema');self.no(self.admin,'schema')
        self.admin=self.ok(None,'login',username='admin',password='admin-pass-123')['token']
        self.assertEqual(len(self.ok(self.admin,'users')['users']),2)
        self.assertTrue(Path(self.temp.name,'before-restore.sqlite').is_file())
        db=sqlite3.connect(Path(self.temp.name,'before-restore.sqlite'))
        self.assertEqual(db.execute("SELECT UserID FROM AuditLog WHERE ActionType='RESTORE'").fetchone()[0],1);db.close()

    def test_legacy_import_accepts_original_schema_then_requires_new_owner(self):
        old=Path(self.temp.name,'import.sqlite');db=Database(old);db.migrate();db.seed();db.close()
        self.ok(self.admin,'restore')
        self.assertFalse(self.ok(None,'status')['configured'])
        self.no(None,'schema')
        self.admin=self.ok(None,'bootstrap',username='new-admin',password='new-admin-pass')['token']
        self.assertEqual(self.ok(self.admin,'rows',table='Product')['total'],2)

    def test_delegated_user_manager_cannot_escalate_to_manager_or_grant_own_missing_permissions(self):
        _,token=self.employee(overrides={'users.manage':True})
        self.ok(token,'users')
        for role,overrides in [('manager',{}),('cashier',{'backup.create':True})]:
            self.no(token,'user_save',name='bad',username='bad',role=role,password='bad-password',cash=[1],overrides=overrides)
        self.no(token,'user_save',id=1,name='admin',username='admin',role='cashier',cash=[1])


if __name__ == '__main__':
    unittest.main()
