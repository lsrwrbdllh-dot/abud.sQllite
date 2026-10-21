"""Exercise the exact JSON command interface embedded in the Android APK."""
from contextlib import nullcontext
from datetime import date
from decimal import Decimal
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest

from database.build_schema import TABLES, SOURCES
from database.engine import Database
from database.mobile_bridge import invoke
from database.mobile_metadata import AUTO, GROUPS, TABLE_LABELS


class MobileBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'store.sqlite'
        db=Database(self.path);db.migrate();db.seed();db.close()

    def call(self, action, **request):
        response=json.loads(invoke(str(self.path),action,json.dumps(request,ensure_ascii=False)))
        self.assertTrue(response['ok'],response.get('error'))
        return response['data']

    def rejected(self, action, **request):
        conn=sqlite3.connect(self.path)
        before='\n'.join(conn.iterdump());conn.close()
        response=json.loads(invoke(str(self.path),action,json.dumps(request)))
        self.assertFalse(response['ok'],response)
        conn=sqlite3.connect(self.path)
        self.assertEqual(before,'\n'.join(conn.iterdump()));conn.close()
        return response['error']

    def add(self, table, **values):
        return next(iter(self.call('save',table=table,values=values)['key'].values()))

    def post(self, table, ident):
        return self.call('post',table=table,id=ident)

    def test_schema_all_68_tables_412_fields_and_21_posting_commands(self):
        schema=self.call('schema')
        self.assertEqual(set(TABLES),{t['name'] for t in schema['tables']})
        self.assertEqual(412,sum(len(t['columns']) for t in schema['tables']))
        self.assertEqual(set(TABLES),set(TABLE_LABELS))
        self.assertEqual(set(TABLES),{name for members in GROUPS.values() for name in members.split()})
        self.assertEqual(set(SOURCES)-{'ManualJournal'},{t['name'] for t in schema['tables'] if t['postable']})
        conn=sqlite3.connect(self.path)
        for table in schema['tables']:
            expected={r[1] for r in conn.execute(f'PRAGMA table_info({table["name"]})')}
            self.assertEqual(expected,{c['name'] for c in table['columns']})
            for c in table['columns']:self.assertNotEqual(c['name'],c['label'])
        conn.close()

    def test_new_store_has_current_year_no_fictional_products_or_postings(self):
        self.path.unlink()
        self.assertFalse(self.call('status')['exists'])
        self.call('initialize',branch='متجر عبد الله',currency='ريال')
        self.assertTrue(self.call('status')['exists'])
        self.assertEqual(self.call('schema')['currency'],'ريال')
        for table in ('Product','Supplier','Customer','PostingEvent','FinancialTransaction'):
            self.assertEqual(self.call('rows',table=table)['total'],0)
        self.assertEqual(self.call('rows',table='Branch')['rows'][0]['Name'],'متجر عبد الله')
        self.assertEqual(self.call('rows',table='FinancialYear')['rows'][0]['StartDate'],f'{date.today().year}-01-01')
        self.rejected('initialize',branch='بديل',currency='وحدة')
        self.call('check')

    def test_demo_all_twenty_events_through_android_json_interface(self):
        from database.demo import populate
        parent=self
        schema={t['name']:t for t in self.call('schema')['tables']}
        class AndroidProxy:
            def transaction(self):return nullcontext()
            def add(self,table,**values):
                fields={f['name']:f for f in schema[table]['columns']}
                converted={k:str(Decimal(v)/fields[k]['scale']) if isinstance(v,int) and fields[k]['scale']>1 else v
                           for k,v in values.items() if k not in AUTO.get(table,set())}
                return parent.add(table,**converted)
            def post(self,table,ident):return parent.post(table,ident)
            def check(self):return parent.call('check')
        populate(AndroidProxy())
        self.assertEqual(self.call('rows',table='PostingEvent')['total'],20)
        self.call('check')
        report=self.call('report',kind='trial',**{'from':'2026-01-01','to':'2026-12-31'})
        self.assertEqual(sum(r['مدين'] for r in report['rows']),sum(r['دائن'] for r in report['rows']))

    def test_exact_decimal_unicode_input_rejects_overprecision_and_float(self):
        self.add('PurchaseInvoice',SupplierID='1',BranchID='1',InvoiceDate='2026-01-02')
        ident=self.add('PurchaseInvoiceDetail',PurchaseInvoiceID='1',ProductID='1',Quantity='١٫٢٥٠',UnitPrice='١٢٫٣٤')
        row=self.call('record',table='PurchaseInvoiceDetail',key={'PurchaseInvoiceDetailID':ident})
        self.assertEqual((row['Quantity'],row['UnitPrice']),(1250,1234))
        for qty in ('0.0001',0.1,'NaN','Infinity'):
            self.rejected('save',table='PurchaseInvoiceDetail',values={'PurchaseInvoiceID':'1','ProductID':'1','Quantity':qty,'UnitPrice':'1'})
        self.rejected('save',table='PurchaseInvoiceDetail',values={'PurchaseInvoiceID':'1','ProductID':'1','Quantity':'1','UnitPrice':'0.001'})

    def test_effects_status_sql_and_primary_key_cannot_be_forged(self):
        for table in ('JournalEntry','JournalEntryDetail','FinancialTransaction','InventoryBalance','AuditLog','ManualJournal'):
            self.rejected('save',table=table,values={'fake':'1'})
        self.rejected('save',table='PurchaseInvoice',values={'SupplierID':'1','InvoiceDate':'2026-01-01','Status':'POSTED'})
        self.rejected('save',table='Customer',values={'CustomerID':'111','Name':'bad'})
        self.rejected('rows',table='Customer; DROP TABLE Product')
        self.rejected('rows',table='Customer',filters={'Name; DROP TABLE Product':'x'})

    def test_post_retry_is_idempotent_posted_edits_and_deletes_roll_back(self):
        ident=self.add('PurchaseInvoice',SupplierID='1',InvoiceDate='2026-01-02')
        self.add('PurchaseInvoiceDetail',PurchaseInvoiceID=str(ident),ProductID='1',Quantity='2',UnitPrice='3')
        self.post('PurchaseInvoice',ident)
        before=self.call('rows',table='PostingEvent')['total']
        self.post('PurchaseInvoice',ident)
        self.assertEqual(before,self.call('rows',table='PostingEvent')['total'])
        self.rejected('save',table='PurchaseInvoice',key={'PurchaseInvoiceID':ident},values={'InvoiceDate':'2026-01-03'})
        self.rejected('delete',table='PurchaseInvoice',key={'PurchaseInvoiceID':ident})
        self.rejected('save',table='PurchaseInvoiceDetail',values={'PurchaseInvoiceID':str(ident),'ProductID':'2','Quantity':'1','UnitPrice':'2'})

    def test_post_rejection_preserves_every_table(self):
        ident=self.add('SalesInvoice',BranchID='1',WarehouseID='1',InvoiceDate='2026-01-02',SaleType='CASH',FinancialAccountID='1')
        self.add('SalesInvoiceDetail',SalesInvoiceID=str(ident),ProductID='1',Quantity='1',UnitPrice='3')
        self.rejected('post',table='SalesInvoice',id=ident)

    def test_manual_funding_report_opening_and_exact_reversal(self):
        result=self.call('manual',date='2026-01-02',description='تمويل الصندوق',lines=[{'account':17,'debit':'100','credit':'0'},{'account':20,'debit':'0','credit':'100'}])
        report=self.call('report',kind='financial',**{'from':'2026-01-03','to':'2026-01-31'})
        cash=next(r for r in report['rows'] if 'الصندوق' in r['الحساب'])
        self.assertEqual((cash['الافتتاحي'],cash['الختامي']),(10000,10000))
        self.call('reverse',id=result['id'],date='2026-01-04',description='تصحيح موثق')
        report=self.call('report',kind='financial',**{'from':'2026-01-01','to':'2026-01-31'})
        self.assertEqual(next(r for r in report['rows'] if 'الصندوق' in r['الحساب'])['الختامي'],0)
        self.rejected('manual',date='2026-01-02',description='غير متوازن',lines=[{'account':17,'debit':'10','credit':'0'},{'account':20,'debit':'0','credit':'9'}])

    def test_financial_transfer_and_unpaid_expense_payment_are_separate(self):
        ident=self.add('FinancialTransfer',FromAccountID='1',ToAccountID='2',TransferDate='2026-01-03',Amount='5.20')
        self.post('FinancialTransfer',ident)
        rows=self.call('rows',table='FinancialTransaction')['rows']
        self.assertEqual({(r['TransactionType'],r['Amount']) for r in rows},{('IN',520),('OUT',520)})
        expense=self.add('Expense',BranchID='1',ExpenseCategoryID='1',ExpenseDate='2026-01-04',Amount='10',Description='مصروف آجل')
        self.post('Expense',expense)
        self.assertEqual(self.call('rows',table='FinancialTransaction')['total'],2)
        pay=self.add('ExpensePayment',ExpenseRef=str(expense),FinancialAccountID='1',PaymentDate='2026-01-05',Amount='10')
        self.post('ExpensePayment',pay)
        self.assertEqual(self.call('rows',table='FinancialTransaction')['total'],3)
        report=self.call('report',kind='income',**{'from':'2026-01-01','to':'2026-01-31'})
        self.assertEqual(report['rows'][-1]['الصافي'],-1000)
        self.call('check')

    def test_payroll_computed_net_and_current_count_snapshot(self):
        payroll=self.add('Payroll',BranchID='1',PayrollMonth='1',PayrollYear='2026',CreatedDate='2026-01-01')
        line=self.add('PayrollDetail',PayrollID=str(payroll),EmployeeID='1',BasicSalary='100',Allowances='20',Deductions='5')
        self.assertEqual(self.call('record',table='PayrollDetail',key={'PayrollDetailID':line})['NetSalary'],11500)
        self.post('Payroll',payroll)

    def test_count_snapshot_freeze_adjustment_and_calculated_difference(self):
        purchase=self.add('PurchaseInvoice',SupplierID='1',InvoiceDate='2026-01-02')
        line=self.add('PurchaseInvoiceDetail',PurchaseInvoiceID=str(purchase),ProductID='1',Quantity='10',UnitPrice='2')
        self.post('PurchaseInvoice',purchase)
        receipt=self.add('GoodsReceipt',PurchaseInvoiceID=str(purchase),WarehouseID='1',ReceiptDate='2026-01-03')
        detail=self.add('GoodsReceiptDetail',GoodsReceiptID=str(receipt),PurchaseInvoiceDetailID=str(line),ReceivedQuantity='10')
        batch=self.add('InventoryBatch',ProductID='1',GoodsReceiptDetailID=str(detail),Quantity='10',ExpiryDate='2027-01-01')
        self.post('GoodsReceipt',receipt)
        count=self.add('InventoryCount',WarehouseID='1',CountDate='2026-01-04')
        counted=self.add('InventoryCountDetail',InventoryCountID=str(count),BatchID=str(batch),ActualQuantity='9')
        self.assertEqual(self.call('record',table='InventoryCountDetail',key={'InventoryCountDetailID':counted})['SystemQuantity'],10000)
        self.call('freeze',id=count)
        adjustment=self.add('InventoryAdjustment',InventoryCountID=str(count),AdjustmentDate='2026-01-04',Reason='عجز الجرد')
        adjusted=self.add('InventoryAdjustmentDetail',AdjustmentID=str(adjustment),InventoryCountDetailID=str(counted))
        self.assertEqual(self.call('record',table='InventoryAdjustmentDetail',key={'AdjustmentDetailID':adjusted})['QuantityDifference'],-1000)
        self.post('InventoryAdjustment',adjustment)
        stock=self.call('report',kind='stock',**{'from':'2026-01-01','to':'2026-12-31'})
        self.assertEqual(stock['rows'][0]['الكمية'],9000)
        self.call('check')

    def test_delivery_expense_later_payment_and_asset_disposal(self):
        from database.demo import populate
        db=Database(self.path);populate(db);db.close()
        delivery=self.add('Delivery',SalesInvoiceID='2',EmployeeID='1',DeliveryAddress='عنوان العميل',ExpectedDate='2026-01-12',ActualDate='2026-01-12',DeliveryFee='1.50')
        self.post('Delivery',delivery)
        expense=self.add('DeliveryExpense',DeliveryID=str(delivery),ExpenseType='وقود',ExpenseDate='2026-01-12',Amount='0.50')
        self.post('DeliveryExpense',expense)
        payment=self.add('ExpensePayment',DeliveryExpenseRef=str(expense),FinancialAccountID='1',PaymentDate='2026-01-12',Amount='0.50')
        self.post('ExpensePayment',payment)
        disposal=self.add('AssetDisposal',AssetID='1',DisposalDate='2026-02-02',Reason='بيع الأصل',SaleProceeds='100',FinancialAccountID='1')
        self.post('AssetDisposal',disposal)
        self.call('check')

    def test_invoice_summary_and_party_balances_and_transit_units(self):
        from database.demo import populate
        db=Database(self.path);populate(db);db.close()
        row=self.call('record',table='SalesInvoice',key={'SalesInvoiceID':2})
        self.assertEqual(row['_summary']['المتبقي'],'0.00')
        customers=self.call('report',kind='customers',**{'from':'2026-01-01','to':'2026-12-31'})
        self.assertEqual(customers['rows'][0]['المستحق_أو_المقدم'],200)
        transit=self.call('report',kind='transit',**{'from':'2026-01-01','to':'2026-12-31'})
        self.assertEqual(transit['rows'][0]['RemainingQuantity'],1000)
        self.assertEqual(transit['scales']['ShippedQuantity'],1000)
        suppliers=self.call('report',kind='suppliers',**{'from':'2026-01-01','to':'2026-12-31'})
        self.assertEqual(suppliers['rows'][0]['المستحق_أو_المقدم'],5300)

    def test_invalid_report_dates_are_rejected(self):
        self.rejected('report',kind='trial',**{'from':'2026-02-01','to':'2026-01-01'})
        self.rejected('report',kind='income',**{'from':'2026-02-30','to':'2026-03-01'})

    def test_close_period_blocks_posting(self):
        self.call('save',table='AccountingPeriod',key={'AccountingPeriodID':1},values={'Status':'CLOSED'})
        ident=self.add('Expense',BranchID='1',ExpenseCategoryID='1',ExpenseDate='2026-01-04',Amount='1',Description='مرفوض')
        self.rejected('post',table='Expense',id=ident)

    def test_composite_keys_crud_related_filter_pagination_and_search(self):
        for i in range(55):self.add('Category',Name=f'فئة {i:03}')
        first=self.call('rows',table='Category',search='فئة')
        second=self.call('rows',table='Category',search='فئة',offset=50)
        self.assertEqual((first['total'],len(first['rows']),len(second['rows'])),(55,50,5))
        self.assertFalse({r['CategoryID'] for r in first['rows']} & {r['CategoryID'] for r in second['rows']})
        role=self.add('Role',RoleName='manager')
        result=self.call('save',table='RolePermission',values={'RoleID':str(role),'PermissionID':'1'})
        self.assertEqual(result['key'],{'RoleID':role,'PermissionID':1})
        self.assertEqual(self.call('rows',table='RolePermission',filters={'RoleID':role})['total'],1)
        self.call('delete',table='RolePermission',key=result['key'])

    def test_password_hashed_redacted_and_changes_audited_without_secret(self):
        user=self.add('AppUser',EmployeeID='1',Username='owner',PasswordHash='my-secret-pass')
        row=self.call('record',table='AppUser',key={'UserID':user})
        self.assertEqual(row['PasswordHash'],'••••••••')
        conn=sqlite3.connect(self.path)
        hashed=conn.execute('SELECT PasswordHash FROM AppUser').fetchone()[0]
        self.assertTrue(hashed.startswith('pbkdf2_sha256$210000$'))
        self.assertNotIn('my-secret-pass',hashed)
        self.assertNotIn('my-secret-pass',str(self.call('rows',table='AuditLog')))
        conn.close()

    def test_backup_restore_preserves_all_tables_fields_postings_and_old_database(self):
        from database.demo import populate
        db=Database(self.path);populate(db);db.close()
        backup=self.call('backup')['file']
        before=self.call('rows',table='PostingEvent')['total']
        self.add('Customer',Name='بعد النسخة')
        Path(self.temp.name,'import.sqlite').write_bytes(Path(backup).read_bytes())
        self.call('restore')
        self.assertEqual(self.call('rows',table='PostingEvent')['total'],before)
        self.assertEqual(self.call('rows',table='Customer',search='بعد النسخة')['total'],0)
        old=Database(Path(self.temp.name,'before-restore.sqlite'))
        self.assertEqual(old.scalar("SELECT count(*) FROM Customer WHERE Name='بعد النسخة'"),1)
        old.close();self.call('check')

    def test_restore_invalid_missing_guard_and_corrupt_file_preserves_current_data(self):
        source=Path(self.temp.name,'import.sqlite')
        source.write_bytes(b'not a SQLite file')
        self.rejected('restore')

    def test_restore_rejects_changed_schema_guard_even_with_valid_sqlite_header(self):
        backup=self.call('backup')['file'];source=Path(self.temp.name,'import.sqlite');source.write_bytes(Path(backup).read_bytes())
        conn=sqlite3.connect(source)
        trigger=conn.execute("SELECT name FROM sqlite_master WHERE type='trigger' LIMIT 1").fetchone()[0]
        conn.execute(f'DROP TRIGGER "{trigger}"');conn.close()
        self.rejected('restore')


if __name__=='__main__':unittest.main()
