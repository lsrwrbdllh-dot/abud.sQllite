import hashlib
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path

from database.engine import Database, RuleError, money, quantity, rounded
from database.build_schema import TABLES, build


class AccountingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'accounting.sqlite'
        self.db = Database(self.path)
        self.db.migrate()
        self.db.seed()
        self.add = self.db.add

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def assert_rejected(self, call):
        # Failure must preserve every table, not merely the status being tested.
        before = '\n'.join(self.db.conn.iterdump())
        with self.assertRaises((RuleError, sqlite3.IntegrityError, sqlite3.OperationalError, OverflowError)):
            call()
        self.assertEqual(before, '\n'.join(self.db.conn.iterdump()))

    def purchase(self, qty=10000, price=100, product=1, supplier=1):
        invoice = self.add('PurchaseInvoice', SupplierID=supplier, BranchID=1, InvoiceDate='2026-01-02')
        line = self.add('PurchaseInvoiceDetail', PurchaseInvoiceID=invoice, ProductID=product, Quantity=qty, UnitPrice=price)
        self.db.post('PurchaseInvoice', invoice)
        return invoice, line

    def receipt(self, invoice, line, qty, warehouse=1, post=True, lot='SAME-FACTORY-LOT'):
        receipt = self.add('GoodsReceipt', PurchaseInvoiceID=invoice, WarehouseID=warehouse, ReceiptDate='2026-01-04')
        detail = self.add('GoodsReceiptDetail', GoodsReceiptID=receipt, PurchaseInvoiceDetailID=line, ReceivedQuantity=qty)
        batch = self.add('InventoryBatch', ProductID=self.db.get('PurchaseInvoiceDetail',line)['ProductID'],
                         GoodsReceiptDetailID=detail, Quantity=qty, ManufacturerLot=lot,
                         ProductionDate='2026-01-01', ExpiryDate='2027-01-01')
        if post:
            self.db.post('GoodsReceipt',receipt)
        return receipt, detail, batch

    def stocked(self, qty=10000, price=100):
        invoice, line = self.purchase(qty,price)
        receipt, detail, batch = self.receipt(invoice,line,qty)
        return invoice,line,batch

    def sale(self, qty=1000, price=200, credit=False, post=True, product=1):
        invoice = self.add('SalesInvoice', BranchID=1, CustomerID=1 if credit else None, WarehouseID=1,
                           InvoiceDate='2026-01-05', SaleType='CREDIT' if credit else 'CASH',
                           FinancialAccountID=None if credit else 1)
        line = self.add('SalesInvoiceDetail', SalesInvoiceID=invoice, ProductID=product, Quantity=qty, UnitPrice=price)
        if post:
            self.db.post('SalesInvoice',invoice)
        return invoice,line

    def stock(self, warehouse=1, product=1):
        return self.db.scalar('SELECT CurrentQuantity FROM InventoryBalance WHERE WarehouseID=? AND ProductID=?', (warehouse,product)) or 0

    def expense_debit(self, account):
        return self.db.scalar('SELECT COALESCE(sum(Debit),0) FROM JournalEntryDetail WHERE AccountID=?', (account,))

    def test_schema_migration_seed_and_every_fk(self):
        self.assertEqual(self.db.scalar('PRAGMA foreign_keys'),1)
        self.assertEqual(self.db.scalar('PRAGMA integrity_check'),'ok')
        self.assertFalse(self.db.rows('PRAGMA foreign_key_check'))
        self.assertEqual((Path(__file__).parents[1]/'database/migrations/001_initial.sql').read_text(),build())
        self.db.migrate()
        table_names = {r[0] for r in self.db.rows("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(set(TABLES),table_names)
        # Probe every declared FK using syntactically valid rows and a nonexistent target.
        checked = 0
        for table in TABLES:
            for fk in self.db.rows(f'PRAGMA foreign_key_list({table})'):
                target_key = fk[4] or TABLES[fk[2]].split()[0]
                target = self.db.scalar(f'SELECT count(*) FROM {fk[2]} WHERE {target_key}=?',(-987654,))
                self.assertEqual(target,0)
                checked += 1
        self.assertGreater(checked,100)
        self.assert_rejected(lambda:self.add('Warehouse',Name='broken',BranchID=999))
        self.assert_rejected(lambda:self.add('SupplierProduct',SupplierID=999,ProductID=1))
        self.assert_rejected(lambda:self.add('Product',Name='broken',Unit='pc',CategoryID=999))
        self.assert_rejected(lambda:self.db.conn.execute('DELETE FROM Category WHERE CategoryID=1'))

    def test_every_declared_fk_rejects_orphan_in_isolation(self):
        # Test-only isolated copy: remove business triggers and checks so they
        # cannot hide a missing FK behind a different validation failure.
        probe = Database(':memory:')
        self.addCleanup(probe.close)
        probe.migrate()
        for trigger in probe.rows("SELECT name FROM sqlite_master WHERE type='trigger'"):
            probe.conn.execute(f'DROP TRIGGER {trigger[0]}')
        probe.conn.execute('PRAGMA ignore_check_constraints=ON')
        probe.conn.execute('PRAGMA foreign_keys=OFF')
        for table in TABLES:
            if table=='SchemaMigration':
                continue
            columns = probe.rows(f'PRAGMA table_info({table})')
            names = ','.join(c[1] for c in columns)
            values = [1 if c[2]=='INTEGER' else 'fixture' for c in columns]
            probe.conn.execute(f"INSERT INTO {table}({names}) VALUES({','.join('?' for _ in values)})",values)
        probe.conn.execute('PRAGMA foreign_keys=ON')
        self.assertFalse(probe.rows('PRAGMA foreign_key_check'))
        checked = 0
        for table in TABLES:
            for fk in probe.rows(f'PRAGMA foreign_key_list({table})'):
                with self.subTest(table=table,column=fk[3]):
                    with self.assertRaisesRegex(sqlite3.IntegrityError,'FOREIGN KEY constraint failed'):
                        probe.conn.execute(f'UPDATE {table} SET {fk[3]}=-987654')
                    checked += 1
        self.assertGreater(checked,100)
        self.assertFalse(probe.rows('PRAGMA foreign_key_check'))

    def test_migration_failure_rolls_back_schema_and_seed_failure_preserves_data(self):
        failed = Database(':memory:')
        self.addCleanup(failed.close)
        invalid = build().replace('COMMIT;', 'INSERT INTO MissingTable VALUES(1);\nCOMMIT;')
        with patch.object(Path,'read_text',return_value=invalid):
            with self.assertRaises(sqlite3.OperationalError):
                failed.migrate()
        self.assertFalse(failed.conn.in_transaction)
        self.assertEqual(failed.scalar("SELECT count(*) FROM sqlite_master WHERE type='table'"),0)
        failed.migrate()
        self.assertEqual(failed.scalar('SELECT Version FROM SchemaMigration'),1)
        self.assert_rejected(self.db.seed)

    def test_standalone_sql_migration_and_seed(self):
        conn = sqlite3.connect(':memory:',isolation_level=None)
        self.addCleanup(conn.close)
        root = Path(__file__).parents[1]/'database'
        conn.executescript((root/'migrations/001_initial.sql').read_text())
        conn.executescript((root/'seed.sql').read_text())
        self.assertEqual(conn.execute('PRAGMA foreign_keys').fetchone()[0],1)
        self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
        self.assertFalse(conn.in_transaction)

    def test_demo_populates_all_core_workflows(self):
        from database.demo import populate
        populate(self.db)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM PostingEvent'),20)
        self.assertEqual(self.db.scalar('SELECT RemainingQuantity FROM StockInTransit'),1000)
        self.db.check()

    def test_exact_money_quantity_and_rounding(self):
        self.assertEqual(money('1.005'),101)
        self.assertEqual(money('-1.005'),-101)
        self.assertEqual(quantity('0.0005'),1)
        self.assertEqual(rounded(1,2),1)
        self.assertEqual(money('90071992547409.01'),9007199254740901)
        with self.assertRaises(RuleError):
            money(0.1)
        self.assert_rejected(lambda:self.add('PurchaseFreight',PurchaseInvoiceID=1,Amount=1.1,FreightDate='2026-01-01',Description='x',Treatment='INVENTORY'))

    def test_partial_receipts_duplicate_lots_and_idempotence(self):
        invoice,line = self.purchase()
        self.assertEqual(self.stock(),0)  # invoice is not a physical receipt
        first,_,b1 = self.receipt(invoice,line,4000)
        _,_,b2 = self.receipt(invoice,line,6000)
        self.assertNotEqual(b1,b2)
        self.assertEqual(self.stock(),10000)
        self.assertEqual(self.db.get('InventoryBatch',b1)['TotalCost'],400)
        excess,_,_ = self.receipt(invoice,line,1,post=False)
        self.assert_rejected(lambda:self.db.post('GoodsReceipt',excess))
        self.assert_rejected(lambda:self.db.post('GoodsReceipt',first))
        self.db.check()

    def test_fractional_batch_and_multiple_returns_preserve_all_minor_units(self):
        invoice,line = self.purchase(qty=3000,price=101)
        receipt = self.add('GoodsReceipt',PurchaseInvoiceID=invoice,WarehouseID=1,ReceiptDate='2026-01-04')
        rd = self.add('GoodsReceiptDetail',GoodsReceiptID=receipt,PurchaseInvoiceDetailID=line,ReceivedQuantity=3000)
        for qty in (333,667,2000):
            self.add('InventoryBatch',ProductID=1,GoodsReceiptDetailID=rd,Quantity=qty)
        self.db.post('GoodsReceipt',receipt)
        sale,sl = self.sale(qty=3000,price=151)
        self.assertEqual(self.stock(),0)
        for qty in (333,667,2000):
            ret = self.add('SalesReturn',SalesInvoiceID=sale,WarehouseID=1,ReturnDate='2026-01-06',Reason='partial demo')
            self.add('SalesReturnDetail',SalesReturnID=ret,SalesInvoiceDetailID=sl,Quantity=qty)
            self.db.post('SalesReturn',ret)
        self.assertEqual(self.stock(),3000)
        self.assertEqual(self.db.scalar('SELECT sum(CostAmount) FROM BatchStock'),303)
        self.assertEqual(self.db.scalar("SELECT sum(CASE WHEN TransactionType='IN' THEN Amount ELSE -Amount END) FROM FinancialTransaction"),0)
        self.db.check()

    def test_freight_complete_allocation_and_unreceived_cost(self):
        invoice,line = self.purchase(qty=3000,price=100)
        freight = self.add('PurchaseFreight',PurchaseInvoiceID=invoice,Amount=101,FreightDate='2026-01-03',Description='transport',Treatment='INVENTORY')
        allocation = self.add('FreightAllocation',FreightID=freight,PurchaseInvoiceDetailID=line,AllocatedAmount=100,AllocationBasis='QUANTITY')
        self.assert_rejected(lambda:self.db.post('PurchaseFreight',freight))
        self.db.conn.execute('UPDATE FreightAllocation SET AllocatedAmount=101 WHERE FreightAllocationID=?',(allocation,))
        self.db.post('PurchaseFreight',freight)
        batches = [self.receipt(invoice,line,1000)[2] for _ in range(3)]
        self.assertEqual([self.db.get('InventoryBatch',b)['TotalCost'] for b in batches],[134,133,134])
        self.assertEqual(sum(self.db.get('InventoryBatch',b)['TotalCost'] for b in batches),401)
        self.assertEqual(self.db.scalar('SELECT sum(Debit-Credit) FROM JournalEntryDetail WHERE AccountID=2'),0)
        late = self.add('PurchaseFreight',PurchaseInvoiceID=invoice,Amount=1,FreightDate='2026-01-06',Description='late',Treatment='INVENTORY')
        self.add('FreightAllocation',FreightID=late,PurchaseInvoiceDetailID=line,AllocatedAmount=1,AllocationBasis='MANUAL')
        self.assert_rejected(lambda:self.db.post('PurchaseFreight',late))
        self.db.check()

    def test_freight_expense_eligibility_and_wrong_invoice(self):
        invoice,line = self.purchase()
        other,otherline = self.purchase()
        f = self.add('PurchaseFreight',PurchaseInvoiceID=invoice,Amount=10,FreightDate='2026-01-03',Description='transport',Treatment='INVENTORY')
        self.assert_rejected(lambda:self.add('FreightAllocation',FreightID=f,PurchaseInvoiceDetailID=otherline,AllocatedAmount=10,AllocationBasis='VALUE'))
        self.assert_rejected(lambda:self.add('PurchaseFreight',PurchaseInvoiceID=invoice,Amount=10,FreightDate='2026-01-03',Description='transport',Treatment='EXPENSE'))
        exp = self.add('PurchaseFreight',PurchaseInvoiceID=other,Amount=10,FreightDate='2026-01-03',Description='eligible demo expense',Treatment='EXPENSE',ExpenseEligible=1,EligibilityReason='Fictional non-acquisition service')
        self.assert_rejected(lambda:self.add('FreightAllocation',FreightID=exp,PurchaseInvoiceDetailID=otherline,AllocatedAmount=10,AllocationBasis='MANUAL'))
        self.db.post('PurchaseFreight',exp)
        self.assertEqual(self.expense_debit(7),10)

    def test_receipt_batch_product_and_quantity_validation(self):
        invoice,line = self.purchase()
        other,otherline = self.purchase()
        r = self.add('GoodsReceipt',PurchaseInvoiceID=invoice,WarehouseID=1,ReceiptDate='2026-01-04')
        self.assert_rejected(lambda:self.add('GoodsReceiptDetail',GoodsReceiptID=r,PurchaseInvoiceDetailID=otherline,ReceivedQuantity=1000))
        rd = self.add('GoodsReceiptDetail',GoodsReceiptID=r,PurchaseInvoiceDetailID=line,ReceivedQuantity=1000)
        self.assert_rejected(lambda:self.add('InventoryBatch',ProductID=2,GoodsReceiptDetailID=rd,Quantity=1000))
        self.add('InventoryBatch',ProductID=1,GoodsReceiptDetailID=rd,Quantity=500)
        self.assert_rejected(lambda:self.db.post('GoodsReceipt',r))
        self.add('InventoryBatch',ProductID=1,GoodsReceiptDetailID=rd,Quantity=500)
        self.db.post('GoodsReceipt',r)
        self.assertEqual(self.stock(),1000)

    def test_cash_and_credit_sales_split_receipt_with_advance(self):
        self.stocked()
        cash,_ = self.sale(qty=1000)
        credit1,_ = self.sale(qty=2000,credit=True)
        credit2,_ = self.sale(qty=1000,credit=True)
        self.assertEqual(self.db.scalar("SELECT count(*) FROM FinancialTransaction WHERE SourceType='SalesInvoice'"),1)
        receipt = self.add('CustomerReceipt',CustomerID=1,FinancialAccountID=1,ReceiptDate='2026-01-06',Amount=700,PaymentMethod='CASH')
        self.add('ReceiptAllocation',ReceiptID=receipt,SalesInvoiceID=credit1,AllocatedAmount=400)
        self.add('ReceiptAllocation',ReceiptID=receipt,SalesInvoiceID=credit2,AllocatedAmount=200)
        self.db.post('CustomerReceipt',receipt)
        self.assertEqual(700-self.db.scalar('SELECT sum(AllocatedAmount) FROM ReceiptAllocation WHERE ReceiptID=?',(receipt,)),100)
        self.assertEqual(self.db.allocated('Sales',credit1),400)
        self.assertEqual(self.stock(),6000)
        self.assert_rejected(lambda:self.db.post('CustomerReceipt',receipt))
        self.db.check()

    def test_receipt_limits_party_and_required_financial_account(self):
        self.stocked()
        sale,_ = self.sale(credit=True)
        wrong = self.add('CustomerReceipt',CustomerID=2,FinancialAccountID=1,ReceiptDate='2026-01-06',Amount=100,PaymentMethod='CASH')
        self.assert_rejected(lambda:self.add('ReceiptAllocation',ReceiptID=wrong,SalesInvoiceID=sale,AllocatedAmount=100))
        missing = self.add('CustomerReceipt',CustomerID=1,ReceiptDate='2026-01-06',Amount=100,PaymentMethod='CASH')
        self.assert_rejected(lambda:self.db.post('CustomerReceipt',missing))
        p = self.add('CustomerReceipt',CustomerID=1,FinancialAccountID=1,ReceiptDate='2026-01-06',Amount=100,PaymentMethod='CASH')
        self.add('ReceiptAllocation',ReceiptID=p,SalesInvoiceID=sale,AllocatedAmount=101)
        self.assert_rejected(lambda:self.db.post('CustomerReceipt',p))
        p2 = self.add('CustomerReceipt',CustomerID=1,FinancialAccountID=1,ReceiptDate='2026-01-06',Amount=300,PaymentMethod='CASH')
        self.add('ReceiptAllocation',ReceiptID=p2,SalesInvoiceID=sale,AllocatedAmount=201)
        self.assert_rejected(lambda:self.db.post('CustomerReceipt',p2))

    def test_supplier_payment_limits_and_party(self):
        invoice,_ = self.purchase()
        bad = self.add('SupplierPayment',SupplierID=2,FinancialAccountID=1,PaymentDate='2026-01-03',Amount=100,PaymentMethod='BANK')
        self.assert_rejected(lambda:self.add('SupplierPaymentAllocation',SupplierPaymentID=bad,PurchaseInvoiceID=invoice,AllocatedAmount=100))
        payment = self.add('SupplierPayment',SupplierID=1,FinancialAccountID=2,PaymentDate='2026-01-03',Amount=1100,PaymentMethod='BANK')
        allocation = self.add('SupplierPaymentAllocation',SupplierPaymentID=payment,PurchaseInvoiceID=invoice,AllocatedAmount=1001)
        self.assert_rejected(lambda:self.db.post('SupplierPayment',payment))
        self.db.conn.execute('UPDATE SupplierPaymentAllocation SET AllocatedAmount=1000 WHERE AllocationID=?',(allocation,))
        self.db.post('SupplierPayment',payment)
        self.assertEqual(self.db.allocated('Purchase',invoice),1000)
        self.assertEqual(self.db.scalar('SELECT FinancialAccountID FROM FinancialTransaction WHERE SourceType=\'SupplierPayment\''),2)

    def test_partial_transfer_and_in_transit_cost(self):
        self.stocked()
        transfer = self.add('StockTransfer',FromWarehouseID=1,ToWarehouseID=2,TransferDate='2026-01-06')
        detail = self.add('StockTransferDetail',TransferID=transfer,ProductID=1,Quantity=6000)
        self.db.post('StockTransfer',transfer)
        self.assertEqual((self.stock(1),self.stock(2)),(4000,0))
        for qty in (2000,4000):
            receipt = self.add('StockTransferReceipt',TransferID=transfer,ReceiptDate='2026-01-07')
            self.add('StockTransferReceiptDetail',TransferReceiptID=receipt,TransferDetailID=detail,ReceivedQuantity=qty)
            self.db.post('StockTransferReceipt',receipt)
            if qty==2000:
                self.assertEqual(self.db.scalar('SELECT sum(Debit-Credit) FROM JournalEntryDetail WHERE AccountID=11'),400)
        self.assertEqual((self.stock(1),self.stock(2)),(4000,6000))
        self.assertEqual(self.db.scalar('SELECT sum(Debit-Credit) FROM JournalEntryDetail WHERE AccountID=11'),0)
        excess = self.add('StockTransferReceipt',TransferID=transfer,ReceiptDate='2026-01-08')
        self.add('StockTransferReceiptDetail',TransferReceiptID=excess,TransferDetailID=detail,ReceivedQuantity=1)
        self.assert_rejected(lambda:self.db.post('StockTransferReceipt',excess))
        self.assert_rejected(lambda:self.db.post('StockTransfer',transfer))
        self.db.check()

    def test_transfer_wrong_source_and_negative_stock_roll_back(self):
        self.stocked(qty=1000)
        t1 = self.add('StockTransfer',FromWarehouseID=1,ToWarehouseID=2,TransferDate='2026-01-06')
        td = self.add('StockTransferDetail',TransferID=t1,ProductID=1,Quantity=1001)
        self.assert_rejected(lambda:self.db.post('StockTransfer',t1))
        t2 = self.add('StockTransfer',FromWarehouseID=1,ToWarehouseID=3,TransferDate='2026-01-06')
        receipt = self.add('StockTransferReceipt',TransferID=t2,ReceiptDate='2026-01-07')
        self.assert_rejected(lambda:self.add('StockTransferReceiptDetail',TransferReceiptID=receipt,TransferDetailID=td,ReceivedQuantity=1))
        sale,_ = self.sale(qty=1001,post=False)
        self.assert_rejected(lambda:self.db.post('SalesInvoice',sale))
        self.assertEqual(self.stock(),1000)

    def test_sales_return_original_batch_cost_and_limits(self):
        _,_,batch = self.stocked()
        sale,line = self.sale(qty=2000,credit=True)
        r = self.add('SalesReturn',SalesInvoiceID=sale,WarehouseID=1,ReturnDate='2026-01-06',Reason='demo')
        self.add('SalesReturnDetail',SalesReturnID=r,SalesInvoiceDetailID=line,Quantity=1000)
        self.db.post('SalesReturn',r)
        self.assertEqual(self.stock(),9000)
        self.assertEqual(self.db.scalar('SELECT CostAmount FROM BatchStock WHERE WarehouseID=1 AND BatchID=?',(batch,)),900)
        excess = self.add('SalesReturn',SalesInvoiceID=sale,WarehouseID=1,ReturnDate='2026-01-07',Reason='demo')
        self.add('SalesReturnDetail',SalesReturnID=excess,SalesInvoiceDetailID=line,Quantity=1001)
        self.assert_rejected(lambda:self.db.post('SalesReturn',excess))
        self.db.check()

    def test_cash_return_refund_and_settled_credit_return_rejected(self):
        self.stocked()
        cash,line = self.sale()
        r = self.add('SalesReturn',SalesInvoiceID=cash,WarehouseID=1,ReturnDate='2026-01-06',Reason='demo')
        self.add('SalesReturnDetail',SalesReturnID=r,SalesInvoiceDetailID=line,Quantity=1000)
        self.db.post('SalesReturn',r)
        self.assertEqual(self.db.scalar("SELECT Amount FROM FinancialTransaction WHERE SourceType='SalesReturn' AND TransactionType='OUT'"),200)
        credit,line = self.sale(credit=True)
        p = self.add('CustomerReceipt',CustomerID=1,FinancialAccountID=1,ReceiptDate='2026-01-06',Amount=200,PaymentMethod='CASH')
        self.add('ReceiptAllocation',ReceiptID=p,SalesInvoiceID=credit,AllocatedAmount=200)
        self.db.post('CustomerReceipt',p)
        r2 = self.add('SalesReturn',SalesInvoiceID=credit,WarehouseID=1,ReturnDate='2026-01-07',Reason='demo')
        self.add('SalesReturnDetail',SalesReturnID=r2,SalesInvoiceDetailID=line,Quantity=1)
        # One thousandth can round to zero; choose a quantity producing an actual credit.
        self.db.conn.execute('UPDATE SalesReturnDetail SET Quantity=1000 WHERE SalesReturnID=?',(r2,))
        self.assert_rejected(lambda:self.db.post('SalesReturn',r2))

    def test_purchase_return_received_quantity_and_landed_cost_difference(self):
        invoice,line = self.purchase()
        f = self.add('PurchaseFreight',PurchaseInvoiceID=invoice,Amount=100,FreightDate='2026-01-03',Description='transport',Treatment='INVENTORY')
        self.add('FreightAllocation',FreightID=f,PurchaseInvoiceDetailID=line,AllocatedAmount=100,AllocationBasis='VALUE')
        self.db.post('PurchaseFreight',f)
        self.receipt(invoice,line,3000)
        r = self.add('PurchaseReturn',PurchaseInvoiceID=invoice,WarehouseID=1,ReturnDate='2026-01-06',Reason='demo')
        self.add('PurchaseReturnDetail',PurchaseReturnID=r,PurchaseInvoiceDetailID=line,Quantity=1000)
        self.db.post('PurchaseReturn',r)
        self.assertEqual(self.stock(),2000)
        self.assertEqual(self.expense_debit(12),10)
        excess = self.add('PurchaseReturn',PurchaseInvoiceID=invoice,WarehouseID=1,ReturnDate='2026-01-07',Reason='demo')
        self.add('PurchaseReturnDetail',PurchaseReturnID=excess,PurchaseInvoiceDetailID=line,Quantity=2001)
        self.assert_rejected(lambda:self.db.post('PurchaseReturn',excess))

    def test_expense_accrual_payment_and_overpayment(self):
        expense = self.add('Expense',BranchID=1,ExpenseCategoryID=1,ExpenseDate='2026-01-02',Amount=500,Description='demo')
        self.db.post('Expense',expense)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM FinancialTransaction'),0)
        for amount in (200,300):
            payment = self.add('ExpensePayment',ExpenseRef=expense,FinancialAccountID=1,PaymentDate='2026-01-03',Amount=amount)
            self.db.post('ExpensePayment',payment)
        self.assertEqual(self.expense_debit(7),500)
        over = self.add('ExpensePayment',ExpenseRef=expense,FinancialAccountID=1,PaymentDate='2026-01-03',Amount=1)
        self.assert_rejected(lambda:self.db.post('ExpensePayment',over))
        paid = self.add('Expense',BranchID=1,ExpenseCategoryID=1,FinancialAccountID=2,ExpenseDate='2026-01-03',Amount=100,Description='paid demo')
        self.db.post('Expense',paid)
        self.assertEqual(self.expense_debit(7),600)
        self.assertEqual(self.db.scalar("SELECT count(*) FROM ExpensePayment WHERE Status='POSTED'"),3)
        self.db.check()

    def test_payroll_accrual_split_salary_no_double_expense(self):
        payroll = self.add('Payroll',BranchID=1,PayrollMonth=1,PayrollYear=2026,CreatedDate='2026-01-25')
        detail = self.add('PayrollDetail',PayrollID=payroll,EmployeeID=1,BasicSalary=100000,Allowances=10000,Deductions=5000,NetSalary=105000)
        self.assert_rejected(lambda:self.add('PayrollDetail',PayrollID=payroll,EmployeeID=2,BasicSalary=1,NetSalary=1))
        self.db.post('Payroll',payroll)
        for amount in (50000,55000):
            p = self.add('SalaryPayment',PayrollDetailID=detail,FinancialAccountID=2,PaymentDate='2026-01-26',Amount=amount,PaymentMethod='BANK')
            self.db.post('SalaryPayment',p)
        self.assertEqual(self.expense_debit(8),105000)
        over = self.add('SalaryPayment',PayrollDetailID=detail,FinancialAccountID=2,PaymentDate='2026-01-26',Amount=1,PaymentMethod='BANK')
        self.assert_rejected(lambda:self.db.post('SalaryPayment',over))

    def test_delivery_fee_expense_and_payment(self):
        self.stocked()
        sale,_ = self.sale()
        delivery = self.add('Delivery',SalesInvoiceID=sale,EmployeeID=1,DeliveryAddress='fictional',ExpectedDate='2026-01-06',ActualDate='2026-01-06',DeliveryFee=50)
        self.db.post('Delivery',delivery)
        expense = self.add('DeliveryExpense',DeliveryID=delivery,FinancialAccountID=1,ExpenseType='demo fuel',Amount=20,ExpenseDate='2026-01-06')
        self.db.post('DeliveryExpense',expense)
        self.assertEqual(self.expense_debit(7),20)
        self.assertEqual(self.db.scalar("SELECT count(*) FROM FinancialTransaction WHERE SourceType='ExpensePayment'"),1)
        self.db.check()

    def test_credit_delivery_fee_is_collectable_and_free_delivery_has_no_journal(self):
        self.stocked()
        sale,_ = self.sale(credit=True)
        for fee in (50,0):
            delivery = self.add('Delivery',SalesInvoiceID=sale,EmployeeID=1,DeliveryAddress='fictional',ExpectedDate='2026-01-06',ActualDate='2026-01-06',DeliveryFee=fee)
            eid = self.db.post('Delivery',delivery)
            if fee==0:
                self.assertEqual(self.db.get('PostingEvent',eid)['HasFinancialEffect'],0)
                self.assertEqual(self.db.scalar('SELECT count(*) FROM JournalEntry WHERE EventID=?',(eid,)),0)
        payment = self.add('CustomerReceipt',CustomerID=1,FinancialAccountID=1,ReceiptDate='2026-01-07',Amount=250,PaymentMethod='CASH')
        self.add('ReceiptAllocation',ReceiptID=payment,SalesInvoiceID=sale,AllocatedAmount=250)
        self.db.post('CustomerReceipt',payment)
        self.db.check()

    def test_financial_transfer_two_legs_without_income_or_expense(self):
        transfer = self.add('FinancialTransfer',FromAccountID=1,ToAccountID=2,TransferDate='2026-01-06',Amount=500)
        self.db.post('FinancialTransfer',transfer)
        self.assertEqual({(r['FinancialAccountID'],r['TransactionType'],r['Amount']) for r in self.db.rows('SELECT * FROM FinancialTransaction')}, {(1,'OUT',500),(2,'IN',500)})
        self.assertEqual(self.expense_debit(7),0)
        self.assert_rejected(lambda:self.db.post('FinancialTransfer',transfer))

    def asset(self):
        asset = self.add('FixedAsset',BranchID=1,AccountID=19,AssetName='demo fixture',PurchaseDate='2026-01-01',Cost=12000,UsefulLifeMonths=12,SalvageValue=0,FinancialAccountID=2)
        self.db.post('FixedAsset',asset)
        return asset

    def test_depreciation_disposal_and_duplicate_period(self):
        asset = self.asset()
        dep = self.add('AssetDepreciation',AssetID=asset,AccountingPeriodID=1,Amount=1000,DepreciationDate='2026-01-31')
        self.db.post('AssetDepreciation',dep)
        self.assertEqual(self.expense_debit(13),1000)
        self.assert_rejected(lambda:self.add('AssetDepreciation',AssetID=asset,AccountingPeriodID=1,Amount=1000,DepreciationDate='2026-01-31'))
        wrong = self.add('AssetDepreciation',AssetID=asset,AccountingPeriodID=2,Amount=1001,DepreciationDate='2026-02-28')
        self.assert_rejected(lambda:self.db.post('AssetDepreciation',wrong))
        disposal = self.add('AssetDisposal',AssetID=asset,DisposalDate='2026-02-01',Reason='demo disposal',SaleProceeds=10000,FinancialAccountID=2)
        self.db.post('AssetDisposal',disposal)
        self.assertEqual(self.expense_debit(16),1000)
        self.db.conn.execute('UPDATE AssetDepreciation SET Amount=1000 WHERE DepreciationID=?',(wrong,))
        self.assert_rejected(lambda:self.db.post('AssetDepreciation',wrong))
        self.db.check()

    def test_depreciation_cumulative_rounding_preserves_salvage_value(self):
        asset = self.add('FixedAsset',BranchID=1,AccountID=19,AssetName='tiny demo asset',PurchaseDate='2026-01-01',Cost=2,UsefulLifeMonths=3,SalvageValue=1,FinancialAccountID=2)
        self.db.post('FixedAsset',asset)
        amounts = []
        for period,day in ((1,'2026-01-31'),(2,'2026-02-28'),(3,'2026-03-31')):
            amount = self.db.depreciation_amount(asset)
            dep = self.add('AssetDepreciation',AssetID=asset,AccountingPeriodID=period,Amount=amount,DepreciationDate=day)
            self.db.post('AssetDepreciation',dep)
            amounts.append(amount)
        self.assertEqual(amounts,[0,1,0])
        self.assertEqual(sum(amounts),1)
        over = self.add('AssetDepreciation',AssetID=asset,AccountingPeriodID=4,Amount=0,DepreciationDate='2026-04-30')
        self.assert_rejected(lambda:self.db.post('AssetDepreciation',over))
        self.db.check()

    def test_inventory_count_adjustment_stale_and_immutable_effects(self):
        _,_,batch = self.stocked()
        count = self.add('InventoryCount',WarehouseID=1,CountDate='2026-01-06')
        detail = self.add('InventoryCountDetail',InventoryCountID=count,BatchID=batch,SystemQuantity=10000,ActualQuantity=9000)
        self.db.freeze_count(count)
        adjustment = self.add('InventoryAdjustment',InventoryCountID=count,AdjustmentDate='2026-01-06',Reason='demo count difference')
        self.add('InventoryAdjustmentDetail',AdjustmentID=adjustment,InventoryCountDetailID=detail,QuantityDifference=-1000)
        self.db.post('InventoryAdjustment',adjustment)
        self.assertEqual(self.stock(),9000)
        self.assertEqual(self.expense_debit(12),100)
        self.assert_rejected(lambda:self.db.conn.execute('UPDATE InventoryMovement SET Quantity=1'))
        self.assert_rejected(lambda:self.db.conn.execute('DELETE FROM InventoryMovement'))
        stale = self.add('InventoryCount',WarehouseID=1,CountDate='2026-01-07')
        self.add('InventoryCountDetail',InventoryCountID=stale,BatchID=batch,SystemQuantity=10000,ActualQuantity=9000)
        self.assert_rejected(lambda:self.db.freeze_count(stale))
        self.db.check()

    def test_unbalanced_closed_period_account_and_date_rejected(self):
        self.assert_rejected(lambda:self.db.manual_entry('2026-01-01',[(17,100,0),(20,0,99)],'unbalanced'))
        self.assert_rejected(lambda:self.db.manual_entry('2026-01-01',[(21,100,0),(20,0,100)],'disabled'))
        self.assert_rejected(lambda:self.db.manual_entry('2027-01-01',[(17,100,0),(20,0,100)],'outside year'))
        self.db.conn.execute("UPDATE AccountingPeriod SET Status='CLOSED' WHERE AccountingPeriodID=1")
        self.assert_rejected(lambda:self.db.manual_entry('2026-01-01',[(17,100,0),(20,0,100)],'closed period'))
        self.db.conn.execute("UPDATE AccountingPeriod SET Status='OPEN' WHERE AccountingPeriodID=1")
        self.db.conn.execute("UPDATE FinancialYear SET Status='CLOSED' WHERE FinancialYearID=1")
        self.assert_rejected(lambda:self.db.manual_entry('2026-01-01',[(17,100,0),(20,0,100)],'closed year'))
        self.assert_rejected(lambda:self.add('PurchaseInvoice',SupplierID=1,InvoiceDate='2026-02-30'))
        self.assert_rejected(lambda:self.add('AccountingPeriod',FinancialYearID=1,Name='overlap',StartDate='2026-01-15',EndDate='2026-02-15'))

    def test_posted_journal_immutable_and_explicit_reversal(self):
        jid = self.db.manual_entry('2026-01-01',[(17,1000,0),(20,0,1000)],'demo opening')
        self.assert_rejected(lambda:self.db.conn.execute('UPDATE JournalEntry SET Description=\'tamper\' WHERE JournalEntryID=?',(jid,)))
        self.assert_rejected(lambda:self.db.conn.execute('UPDATE JournalEntryDetail SET Debit=1 WHERE JournalEntryID=? AND Debit>0',(jid,)))
        self.assert_rejected(lambda:self.db.conn.execute('DELETE FROM JournalEntryDetail WHERE JournalEntryID=?',(jid,)))
        reversal = self.db.manual_entry('2026-01-02',[(17,0,1000),(20,1000,0)],'documented correction',jid)
        self.assertEqual(self.db.get('JournalEntry',reversal)['ReversesJournalEntryID'],jid)
        self.assert_rejected(lambda:self.db.manual_entry('2026-01-02',[(17,0,1000),(20,1000,0)],'duplicate reversal',jid))
        self.db.check()

    def test_posted_lines_cannot_be_inserted_moved_or_deleted(self):
        invoice,line,batch = self.stocked()
        other,_ = self.purchase()
        self.assert_rejected(lambda:self.add('PurchaseInvoiceDetail',PurchaseInvoiceID=invoice,ProductID=1,Quantity=1,UnitPrice=1))
        self.assert_rejected(lambda:self.db.conn.execute('UPDATE PurchaseInvoiceDetail SET PurchaseInvoiceID=? WHERE PurchaseInvoiceDetailID=?',(other,line)))
        self.assert_rejected(lambda:self.db.conn.execute('DELETE FROM InventoryBatch WHERE BatchID=?',(batch,)))
        self.assert_rejected(lambda:self.db.conn.execute('UPDATE InventoryBatch SET TotalCost=1 WHERE BatchID=?',(batch,)))

    def test_source_fk_validation_and_duplicate_events(self):
        invoice,_ = self.purchase()
        self.assert_rejected(lambda:self.db._insert('PostingEvent',SourceType='PurchaseInvoice',SourceID=999,SourceEvent='POST',EventDate='2026-01-02',PurchaseInvoiceRef=999))
        self.assert_rejected(lambda:self.db._insert('PostingEvent',SourceType='PurchaseInvoice',SourceID=invoice+1,SourceEvent='POST',EventDate='2026-01-02',PurchaseInvoiceRef=invoice))
        self.assert_rejected(lambda:self.db._insert('PostingEvent',SourceType='PurchaseInvoice',SourceID=invoice,SourceEvent='POST',EventDate='2026-01-02',PurchaseInvoiceRef=invoice))
        self.assert_rejected(lambda:self.db._insert('PostingEvent',SourceType='Unknown',SourceID=1,SourceEvent='POST',EventDate='2026-01-02',PurchaseInvoiceRef=invoice))

    def test_effect_api_is_closed_and_sql_rejects_unapproved_source_and_forged_move(self):
        _,_,batch = self.stocked(qty=1000)
        sale,sl = self.sale(post=False)
        self.assert_rejected(lambda:self.add('InventoryBalance',WarehouseID=1,ProductID=2,CurrentQuantity=100))
        self.assert_rejected(lambda:self.db.conn.execute("UPDATE SalesInvoice SET Status='POSTED' WHERE SalesInvoiceID=?",(sale,)))

        def forge():
            with self.db.transaction():
                eid = self.db._event('SalesInvoice',sale,'2026-01-05')
                alloc = self.db._insert('StockAllocation',EventID=eid,BatchID=batch,WarehouseID=1,Quantity=-1000,CostAmount=-100,SalesInvoiceDetailRef=sl)
                self.db._insert('InventoryMovement',EventID=eid,StockAllocationID=alloc,ProductID=1,WarehouseID=1,BatchID=batch,
                                Quantity=-999,CostAmount=-100,MovementDate='2026-01-05T00:00:00Z',MovementType='OUT',SourceType='SalesInvoice',SourceDetailID=sl)
        self.assert_rejected(forge)

        def excessive_issue():
            with self.db.transaction():
                eid = self.db._event('SalesInvoice',sale,'2026-01-05')
                self.db._move(eid,'SalesInvoiceDetail',sl,batch,1,-1001,-101)
        self.assert_rejected(excessive_issue)

    def test_historical_settings_accounts_and_hierarchy_are_protected(self):
        invoice,line = self.purchase()
        self.assert_rejected(lambda:self.db.conn.execute("UPDATE SystemSetting SET CurrencyName='other'"))
        self.assert_rejected(lambda:self.db.conn.execute('DELETE FROM AccountingPolicy'))
        self.assert_rejected(lambda:self.db.conn.execute("UPDATE ChartOfAccounts SET AccountType='EXPENSE' WHERE AccountID=2"))
        parent = self.add('ChartOfAccounts',AccountCode='PARENT',AccountName='parent',AccountType='ASSET',IsPostingAllowed=0)
        child = self.add('ChartOfAccounts',AccountCode='CHILD',AccountName='child',AccountType='ASSET',ParentAccountID=parent)
        self.assert_rejected(lambda:self.db.conn.execute('UPDATE ChartOfAccounts SET ParentAccountID=? WHERE AccountID=?',(child,parent)))

    def test_roles_permissions_hash_and_append_only_audit(self):
        digest = hashlib.scrypt(b'fictional-test-only',salt=b'fictional-test-salt',n=16384,r=8,p=1).hex()
        user = self.add('AppUser',EmployeeID=1,Username='demo',PasswordHash='scrypt$'+digest,CreatedAt='2026-01-01T00:00:00Z')
        self.add('UserRole',UserID=user,RoleID=1)
        self.assertEqual(self.db.scalar('''SELECT count(*) FROM UserRole u JOIN RolePermission r USING(RoleID)
            JOIN Permission p USING(PermissionID) WHERE u.UserID=? AND p.PermissionCode='ACCOUNTING_REVIEW' ''',(user,)),1)
        self.assert_rejected(lambda:self.add('AppUser',EmployeeID=2,Username='DEMO',PasswordHash='scrypt$'+digest,CreatedAt='2026-01-01T00:00:00Z'))
        self.assert_rejected(lambda:self.add('AppUser',EmployeeID=2,Username='other',PasswordHash='plaintext',CreatedAt='2026-01-01T00:00:00Z'))
        self.purchase()
        self.assert_rejected(lambda:self.db.conn.execute('DELETE FROM AuditLog'))

    def test_two_connections_cannot_oversell(self):
        self.stocked(qty=1000)
        sales = [self.sale(qty=1000,post=False)[0] for _ in range(2)]
        barrier = threading.Barrier(2)
        outcomes = []
        failures = []

        def worker(ident):
            db = Database(self.path)
            try:
                self.assertEqual(db.scalar('PRAGMA foreign_keys'),1)
                barrier.wait(timeout=5)
                try:
                    db.post('SalesInvoice',ident)
                    outcomes.append('posted')
                except RuleError:
                    outcomes.append('rejected')
            except BaseException as exc:
                failures.append(exc)
            finally:
                db.close()

        threads = [threading.Thread(target=worker,args=(ident,)) for ident in sales]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
            self.assertFalse(t.is_alive())
        self.assertFalse(failures)
        self.assertCountEqual(outcomes,['posted','rejected'])
        self.assertEqual(self.stock(),0)
        self.db.check()


if __name__=='__main__':
    unittest.main()
