"""Controlled posting API. Public operations own an IMMEDIATE SQLite transaction.

Never expose the connection as a user-facing SQL endpoint. See database/README.md
for the split between SQL constraints and cross-document service validation.
"""
from contextlib import contextmanager
from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import argparse
import json
import sqlite3

from .build_schema import TABLES, SOURCES

ROOT = Path(__file__).parent
MAX_INT = 2**63 - 1
EFFECT_TABLES = {'PostingEvent','JournalEntry','JournalEntryDetail','StockAllocation',
                 'InventoryMovement','FinancialTransaction','AuditLog','SchemaMigration',
                 'InventoryBalance','BatchStock'}


class RuleError(ValueError):
    """A documented accounting or stock rule rejected the operation."""


def require(condition, message):
    if not condition:
        raise RuleError(message)


def rounded(numerator, denominator):
    require(type(numerator) is int and type(denominator) is int and denominator > 0,
            'integer arithmetic with positive denominator required')
    sign = -1 if numerator < 0 else 1
    value = sign * ((abs(numerator) * 2 + denominator) // (2 * denominator))
    require(abs(value) <= MAX_INT, '64-bit amount overflow')
    return value


def scaled(value, scale):
    """Convert a decimal string, never a binary float, using HALF_UP."""
    require(isinstance(value, (str, Decimal, int)) and not isinstance(value, bool), 'use decimal text, not float')
    number = Decimal(value) * scale
    require(number.is_finite(), 'finite decimal required')
    result = int(number.to_integral_value(rounding=ROUND_HALF_UP))
    require(abs(result) <= MAX_INT, '64-bit amount overflow')
    return result


def money(value):
    return scaled(value, 100)


def quantity(value):
    return scaled(value, 1000)


def line_amount(qty, price):
    return rounded(qty * price, 1000)


class Database:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, isolation_level=None, timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA foreign_keys=ON')
        self.conn.execute('PRAGMA busy_timeout=10000')
        require(self.scalar('PRAGMA foreign_keys') == 1, 'foreign keys must be enabled')
        self._depth = 0
        # Optional local application actor; CLI/imported legacy entries remain NULL.
        self.actor_user_id = None

    def close(self):
        self.conn.close()

    @contextmanager
    def transaction(self):
        level = self._depth
        savepoint = f'posting_{level}'
        self.conn.execute(f'SAVEPOINT {savepoint}' if level else 'BEGIN IMMEDIATE')
        self._depth += 1
        try:
            yield
            self.conn.execute(f'RELEASE {savepoint}' if level else 'COMMIT')
        except BaseException:
            if self.conn.in_transaction:
                if level:
                    self.conn.execute(f'ROLLBACK TO {savepoint}')
                    self.conn.execute(f'RELEASE {savepoint}')
                else:
                    self.conn.execute('ROLLBACK')
            raise
        finally:
            self._depth -= 1

    def migrate(self):
        require(not self.conn.in_transaction, 'migration requires its own transaction')
        exists = self.scalar("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='SchemaMigration'")
        if exists:
            require(self.scalar('SELECT max(Version) FROM SchemaMigration') == 1, 'unsupported schema version')
            return
        try:
            self.conn.executescript((ROOT / 'migrations/001_initial.sql').read_text())
        except BaseException:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise

    def seed(self):
        require(not self.conn.in_transaction, 'seed requires its own transaction')
        try:
            self.conn.executescript((ROOT / 'seed.sql').read_text())
        except BaseException:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise

    def scalar(self, sql, args=()):
        row = self.conn.execute(sql, args).fetchone()
        return None if row is None else row[0]

    def rows(self, sql, args=()):
        return self.conn.execute(sql, args).fetchall()

    def get(self, table, ident):
        require(table in TABLES, 'unknown table')
        pk = TABLES[table].split()[0]
        row = self.conn.execute(f'SELECT * FROM {table} WHERE {pk}=?', (ident,)).fetchone()
        require(row is not None, f'{table} does not exist')
        return row

    def add(self, table, **values):
        """Create a draft or master record; amounts and quantities are already scaled."""
        require(table not in EFFECT_TABLES, 'effects and balances may only be created by posting')
        return self._insert(table, **values)

    def _insert(self, table, **values):
        require(table in TABLES, 'unknown table')
        columns = {r[1] for r in self.rows(f'PRAGMA table_info({table})')}
        require(values and set(values) <= columns, 'unknown column')
        require(all(not isinstance(v, float) for v in values.values()), 'float values are not accepted')
        with self.transaction():
            return self.conn.execute(f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join('?' for _ in values)})",
                                     tuple(values.values())).lastrowid

    def policy(self, name):
        return self.get('AccountingPolicy', 1)[name + 'AccountID']

    def financial(self, ident):
        require(ident is not None, 'financial account required for settlement')
        row = self.get('FinancialAccount', ident)
        require(self.get('ChartOfAccounts', row['PostingAccountID'])['IsPostingAllowed'] == 1, 'financial posting account disabled')
        return row['PostingAccountID']

    def require_posted(self, table, ident):
        row = self.get(table, ident)
        require(row['Status'] == 'POSTED', f'{table} must be posted first')
        return row

    def _event(self, table, ident, day, event='POST'):
        require(self.get(table, ident)['Status'] == 'DRAFT' or event == 'PAY', 'already posted')
        return self._insert('PostingEvent', SourceType=table, SourceID=ident, SourceEvent=event,
                        EventDate=day, **{table + 'Ref': ident})

    def _journal(self, eid, lines, description, reverses=None):
        event = self.get('PostingEvent', eid)
        lines = [(a, d, c) for a, d, c in lines if d or c]
        if not lines:
            self.conn.execute('UPDATE PostingEvent SET HasFinancialEffect=0 WHERE EventID=?', (eid,))
            return None
        require(all(type(d) is int and type(c) is int and 0 <= d <= MAX_INT and 0 <= c <= MAX_INT
                    and ((d > 0 and c == 0) or (c > 0 and d == 0)) for _, d, c in lines), 'invalid journal amounts')
        require(sum(d for _, d, _ in lines) <= MAX_INT and sum(c for _, _, c in lines) <= MAX_INT, 'journal overflow')
        periods = self.rows('''SELECT p.AccountingPeriodID,p.FinancialYearID FROM AccountingPeriod p
            JOIN FinancialYear y USING(FinancialYearID) WHERE ? BETWEEN p.StartDate AND p.EndDate
            AND ? BETWEEN y.StartDate AND y.EndDate AND p.Status='OPEN' AND y.Status='OPEN' ''',
                            (event['EventDate'], event['EventDate']))
        require(len(periods) == 1, 'one open matching accounting period required')
        period = periods[0]
        jid = self._insert('JournalEntry', FinancialYearID=period['FinancialYearID'],
                       AccountingPeriodID=period['AccountingPeriodID'], EntryDate=event['EventDate'],
                       EntryNumber=f'EV-{eid}', Description=description, SourceType=event['SourceType'],
                       SourceID=event['SourceID'], SourceEvent=event['SourceEvent'], EventID=eid,
                       ReversesJournalEntryID=reverses)
        for account, debit, credit in lines:
            self._insert('JournalEntryDetail', JournalEntryID=jid, AccountID=account, Debit=debit, Credit=credit)
        self.conn.execute("UPDATE JournalEntry SET Status='POSTED' WHERE JournalEntryID=?", (jid,))
        return jid

    def _cash(self, eid, account, amount, direction):
        if amount == 0:
            return
        self.financial(account)
        e = self.get('PostingEvent', eid)
        self._insert('FinancialTransaction', FinancialAccountID=account, SourceType=e['SourceType'],
                 SourceID=e['SourceID'], SourceEvent=e['SourceEvent'], TransactionDate=e['EventDate'],
                 TransactionType=direction, Amount=amount, Description=e['SourceType'], EventID=eid)

    def _move(self, eid, detail_table, detail_id, batch, warehouse, qty, cost, original=None):
        bid = self.get('InventoryBatch', batch)
        allocation = self._insert('StockAllocation', EventID=eid, BatchID=batch, WarehouseID=warehouse,
                              Quantity=qty, CostAmount=cost, OriginalAllocationID=original,
                              **{detail_table + 'Ref': detail_id})
        event = self.get('PostingEvent', eid)
        self._insert('InventoryMovement', ProductID=bid['ProductID'], WarehouseID=warehouse, BatchID=batch,
                 MovementType='IN' if qty > 0 else 'OUT', Quantity=qty, CostAmount=cost,
                 MovementDate=event['EventDate'] + 'T00:00:00Z', SourceType=event['SourceType'],
                 SourceDetailID=detail_id, EventID=eid, StockAllocationID=allocation)
        return allocation

    def _take(self, eid, detail_table, detail_id, warehouse, product, qty, purchase_line=None):
        require(qty > 0, 'positive issue quantity required')
        stock = self.rows('''SELECT s.*,b.ProductID,r.PurchaseInvoiceDetailID FROM BatchStock s
            JOIN InventoryBatch b USING(BatchID) JOIN GoodsReceiptDetail r USING(GoodsReceiptDetailID)
            WHERE s.WarehouseID=? AND b.ProductID=? AND s.CurrentQuantity>0 ORDER BY s.BatchID''',
                          (warehouse, product))
        total = 0
        for s in stock:
            if purchase_line is not None and s['PurchaseInvoiceDetailID'] != purchase_line:
                continue
            used = min(qty, s['CurrentQuantity'])
            cost = rounded(s['CostAmount'] * used, s['CurrentQuantity'])
            self._move(eid, detail_table, detail_id, s['BatchID'], warehouse, -used, -cost)
            total += cost
            qty -= used
            if qty == 0:
                return total
        raise RuleError('insufficient stock for requested issue')

    def _finish(self, table, ident, eid, lines):
        jid = self._journal(eid, lines, f'{table} #{ident}')
        if table in ('AssetDepreciation', 'AssetDisposal'):
            self.conn.execute(f'UPDATE {table} SET JournalEntryID=? WHERE {SOURCES[table]}=?', (jid, ident))
        self.conn.execute("UPDATE PostingEvent SET Status='POSTED' WHERE EventID=?", (eid,))
        self.conn.execute(f"UPDATE {table} SET Status='POSTED' WHERE {SOURCES[table]}=?", (ident,))
        self._insert('AuditLog', UserID=self.actor_user_id, ActionType='POST', EntityName=table, AffectedRecordID=ident,
                 NewValues=json.dumps({'EventID': eid, 'JournalEntryID': jid}),
                 ActionAt=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
        return eid

    def post(self, table, ident):
        """Validate, cost, move, settle and post an existing draft atomically."""
        require(table in SOURCES and table != 'ManualJournal', 'unsupported document')
        with self.transaction():
            doc = self.get(table, ident)
            require(doc['Status'] == 'DRAFT', 'already posted')
            day_column = {'PurchaseInvoice':'InvoiceDate', 'PurchaseFreight':'FreightDate', 'GoodsReceipt':'ReceiptDate',
                'StockTransfer':'TransferDate','StockTransferReceipt':'ReceiptDate','InventoryAdjustment':'AdjustmentDate',
                'SalesInvoice':'InvoiceDate','SalesReturn':'ReturnDate','PurchaseReturn':'ReturnDate',
                'CustomerReceipt':'ReceiptDate','SupplierPayment':'PaymentDate','Expense':'ExpenseDate',
                'Payroll':'CreatedDate','SalaryPayment':'PaymentDate','Delivery':'ActualDate',
                'DeliveryExpense':'ExpenseDate','FinancialTransfer':'TransferDate','FixedAsset':'PurchaseDate',
                'AssetDepreciation':'DepreciationDate','AssetDisposal':'DisposalDate','ExpensePayment':'PaymentDate'}[table]
            day = doc[day_column]
            require(day is not None, 'posting date required')
            eid = self._event(table, ident, day)
            lines = getattr(self, '_post_' + table)(doc, eid)
            result = self._finish(table, ident, eid, lines)
            if table in ('Expense', 'DeliveryExpense') and doc['FinancialAccountID'] is not None:
                payment = self.add('ExpensePayment', **{('ExpenseRef' if table == 'Expense' else 'DeliveryExpenseRef'): ident},
                                   FinancialAccountID=doc['FinancialAccountID'], Amount=doc['Amount'],
                                   PaymentDate=doc['PaidDate'] or day)
                self.post('ExpensePayment', payment)
            return result

    def _lines(self, table, fk, ident):
        rows = self.rows(f'SELECT * FROM {table} WHERE {fk}=? ORDER BY 1', (ident,))
        require(rows, 'document must contain at least one line')
        return rows

    def _post_PurchaseInvoice(self, d, eid):
        lines = self._lines('PurchaseInvoiceDetail', 'PurchaseInvoiceID', d['PurchaseInvoiceID'])
        amount = sum(line_amount(r['Quantity'], r['UnitPrice']) for r in lines)
        require(amount > 0, 'invoice rounds to zero')
        return [(self.policy('Clearing'), amount, 0), (self.policy('Payable'), 0, amount)]

    def _post_PurchaseFreight(self, d, eid):
        invoice = self.require_posted('PurchaseInvoice', d['PurchaseInvoiceID'])
        require(d['FreightDate'] >= invoice['InvoiceDate'], 'freight precedes invoice')
        require(not self.scalar("SELECT count(*) FROM GoodsReceipt WHERE PurchaseInvoiceID=? AND Status='POSTED'", (d['PurchaseInvoiceID'],)),
                'freight must be approved before first receipt; late revaluation is unsupported')
        allocations = self.rows('SELECT * FROM FreightAllocation WHERE FreightID=?', (d['FreightID'],))
        require(all(self.get('PurchaseInvoiceDetail',a['PurchaseInvoiceDetailID'])['PurchaseInvoiceID']==d['PurchaseInvoiceID'] for a in allocations), 'freight invoice mismatch')
        if d['Treatment'] == 'INVENTORY':
            require(allocations and sum(a['AllocatedAmount'] for a in allocations) == d['Amount'], 'freight must be fully allocated')
            account = self.policy('Clearing')
        else:
            require(d['ExpenseEligible'] == 1 and d['EligibilityReason'] and not allocations, 'expense freight is ineligible or allocated')
            account = self.policy('Expense')
        return [(account, d['Amount'], 0), (self.policy('Payable'), 0, d['Amount'])]

    def _post_GoodsReceipt(self, d, eid):
        inv = self.require_posted('PurchaseInvoice', d['PurchaseInvoiceID'])
        wh = self.get('Warehouse', d['WarehouseID'])
        require(inv['BranchID'] is None or wh['BranchID'] == inv['BranchID'], 'receipt warehouse branch mismatch')
        require(d['ReceiptDate'] >= inv['InvoiceDate'], 'receipt precedes invoice')
        require(not self.scalar("SELECT count(*) FROM PurchaseFreight WHERE PurchaseInvoiceID=? AND Status='DRAFT'", (d['PurchaseInvoiceID'],)), 'approve freight before receipt')
        total = 0
        for r in self._lines('GoodsReceiptDetail', 'GoodsReceiptID', d['GoodsReceiptID']):
            p = self.get('PurchaseInvoiceDetail', r['PurchaseInvoiceDetailID'])
            require(p['PurchaseInvoiceID'] == d['PurchaseInvoiceID'], 'receipt invoice mismatch')
            prev = self.scalar('''SELECT COALESCE(sum(r.ReceivedQuantity),0) FROM GoodsReceiptDetail r
                JOIN GoodsReceipt g USING(GoodsReceiptID) WHERE r.PurchaseInvoiceDetailID=? AND g.Status='POSTED' ''', (p['PurchaseInvoiceDetailID'],))
            require(prev + r['ReceivedQuantity'] <= p['Quantity'], 'receipt exceeds purchase quantity')
            batches = self._lines('InventoryBatch', 'GoodsReceiptDetailID', r['GoodsReceiptDetailID'])
            require(sum(b['Quantity'] for b in batches) == r['ReceivedQuantity'], 'batch quantities must equal receipt')
            freight = self.scalar('''SELECT COALESCE(sum(a.AllocatedAmount),0) FROM FreightAllocation a
                JOIN PurchaseFreight f USING(FreightID) WHERE a.PurchaseInvoiceDetailID=? AND f.Status='POSTED' ''', (p['PurchaseInvoiceDetailID'],))
            full_cost = line_amount(p['Quantity'], p['UnitPrice']) + freight
            cumulative = prev
            for b in batches:
                require(b['ProductID'] == p['ProductID'], 'batch product mismatch')
                cost = rounded(full_cost * (cumulative + b['Quantity']), p['Quantity']) - rounded(full_cost * cumulative, p['Quantity'])
                unit_cost = rounded(cost * 1000, b['Quantity'])
                self.conn.execute('UPDATE InventoryBatch SET TotalCost=?,UnitCost=? WHERE BatchID=?', (cost, unit_cost, b['BatchID']))
                self._move(eid, 'GoodsReceiptDetail', r['GoodsReceiptDetailID'], b['BatchID'], d['WarehouseID'], b['Quantity'], cost)
                total += cost
                cumulative += b['Quantity']
        return [(self.policy('Inventory'), total, 0), (self.policy('Clearing'), 0, total)]

    def _post_SalesInvoice(self, d, eid):
        wh = self.get('Warehouse', d['WarehouseID'])
        require(wh['BranchID'] == d['BranchID'], 'sales warehouse branch mismatch')
        total = cost = 0
        for r in self._lines('SalesInvoiceDetail', 'SalesInvoiceID', d['SalesInvoiceID']):
            total += line_amount(r['Quantity'], r['UnitPrice'])
            cost += self._take(eid, 'SalesInvoiceDetail', r['SalesInvoiceDetailID'], d['WarehouseID'], r['ProductID'], r['Quantity'])
        require(total > 0, 'invoice rounds to zero')
        account = self.financial(d['FinancialAccountID']) if d['SaleType'] == 'CASH' else self.policy('Receivable')
        if d['SaleType'] == 'CASH':
            self._cash(eid, d['FinancialAccountID'], total, 'IN')
        return [(account, total, 0), (self.policy('Revenue'), 0, total),
                (self.policy('CostOfSales'), cost, 0), (self.policy('Inventory'), 0, cost)]

    def _post_StockTransfer(self, d, eid):
        total = 0
        for r in self._lines('StockTransferDetail', 'TransferID', d['TransferID']):
            total += self._take(eid, 'StockTransferDetail', r['TransferDetailID'], d['FromWarehouseID'], r['ProductID'], r['Quantity'])
        return [(self.policy('Transit'), total, 0), (self.policy('Inventory'), 0, total)]

    def _post_StockTransferReceipt(self, d, eid):
        transfer = self.require_posted('StockTransfer', d['TransferID'])
        require(d['ReceiptDate'] >= transfer['TransferDate'], 'transfer receipt precedes shipment')
        total = 0
        for r in self._lines('StockTransferReceiptDetail', 'TransferReceiptID', d['TransferReceiptID']):
            source = self.get('StockTransferDetail', r['TransferDetailID'])
            require(source['TransferID'] == d['TransferID'], 'transfer detail mismatch')
            previous = self.scalar('''SELECT COALESCE(sum(x.ReceivedQuantity),0) FROM StockTransferReceiptDetail x
                JOIN StockTransferReceipt h USING(TransferReceiptID) WHERE x.TransferDetailID=? AND h.Status='POSTED' ''', (source['TransferDetailID'],))
            require(previous + r['ReceivedQuantity'] <= source['Quantity'], 'transfer receipt exceeds shipment')
            remaining = r['ReceivedQuantity']
            shipped = self.rows('SELECT * FROM StockAllocation WHERE StockTransferDetailRef=? ORDER BY StockAllocationID', (source['TransferDetailID'],))
            for s in shipped:
                used, used_cost = self.conn.execute('''SELECT COALESCE(sum(Quantity),0),COALESCE(sum(CostAmount),0)
                    FROM StockAllocation WHERE OriginalAllocationID=? AND StockTransferReceiptDetailRef IS NOT NULL''', (s['StockAllocationID'],)).fetchone()
                available = -s['Quantity'] - used
                qty = min(remaining, available)
                if qty <= 0:
                    continue
                cost = rounded((-s['CostAmount'] - used_cost) * qty, available)
                self._move(eid, 'StockTransferReceiptDetail', r['TransferReceiptDetailID'], s['BatchID'], transfer['ToWarehouseID'], qty, cost, s['StockAllocationID'])
                total += cost
                remaining -= qty
                if not remaining:
                    break
            require(remaining == 0, 'shipment allocation missing')
        return [(self.policy('Inventory'), total, 0), (self.policy('Transit'), 0, total)]

    def invoice_total(self, kind, ident):
        require(kind in ('Sales','Purchase'), 'unknown invoice kind')
        key = kind + 'InvoiceID'
        value = sum(line_amount(r['Quantity'], r['UnitPrice']) for r in self.rows(f'SELECT * FROM {kind}InvoiceDetail WHERE {key}=?', (ident,)))
        if kind == 'Purchase':
            value += self.scalar("SELECT COALESCE(sum(Amount),0) FROM PurchaseFreight WHERE PurchaseInvoiceID=? AND Status='POSTED'", (ident,))
        else:
            value += self.scalar("SELECT COALESCE(sum(DeliveryFee),0) FROM Delivery WHERE SalesInvoiceID=? AND Status='POSTED'", (ident,))
        returned = 0
        for line in self.rows(f'SELECT * FROM {kind}InvoiceDetail WHERE {key}=?', (ident,)):
            qty = self.scalar(f'''SELECT COALESCE(sum(r.Quantity),0) FROM {kind}ReturnDetail r JOIN {kind}Return h
                USING({kind}ReturnID) WHERE r.{kind}InvoiceDetailID=? AND h.Status='POSTED' ''', (line[kind+'InvoiceDetailID'],))
            returned += rounded(line_amount(line['Quantity'], line['UnitPrice']) * qty, line['Quantity'])
        return value - returned

    def allocated(self, kind, ident):
        if kind == 'Sales':
            return self.scalar('''SELECT COALESCE(sum(a.AllocatedAmount),0) FROM ReceiptAllocation a
                JOIN CustomerReceipt p USING(ReceiptID) WHERE a.SalesInvoiceID=? AND p.Status='POSTED' ''', (ident,))
        return self.scalar('''SELECT COALESCE(sum(a.AllocatedAmount),0) FROM SupplierPaymentAllocation a
            JOIN SupplierPayment p USING(SupplierPaymentID) WHERE a.PurchaseInvoiceID=? AND p.Status='POSTED' ''', (ident,))

    def _settlement(self, d, eid, kind):
        customer = kind == 'Sales'
        table, key, allocation, party = ('CustomerReceipt','ReceiptID','ReceiptAllocation','CustomerID') if customer else ('SupplierPayment','SupplierPaymentID','SupplierPaymentAllocation','SupplierID')
        rows = self.rows(f'SELECT * FROM {allocation} WHERE {key}=?', (d[key],))
        require(sum(a['AllocatedAmount'] for a in rows) <= d['Amount'], 'allocations exceed payment amount')
        for a in rows:
            inv = self.require_posted(kind + 'Invoice', a[kind + 'InvoiceID'])
            require(inv[party] == d[party], 'settlement party mismatch')
            require(d['ReceiptDate' if customer else 'PaymentDate'] >= inv['InvoiceDate'], 'settlement allocation precedes invoice')
            require(not customer or inv['SaleType'] == 'CREDIT', 'cash invoice cannot be allocated again')
            require(a['AllocatedAmount'] + self.allocated(kind, a[kind + 'InvoiceID']) <= self.invoice_total(kind, a[kind + 'InvoiceID']), 'allocation exceeds invoice outstanding')
        financial = self.financial(d['FinancialAccountID'])
        self._cash(eid, d['FinancialAccountID'], d['Amount'], 'IN' if customer else 'OUT')
        return [(financial, d['Amount'], 0), (self.policy('Receivable'), 0, d['Amount'])] if customer else [(self.policy('Payable'), d['Amount'], 0), (financial, 0, d['Amount'])]

    def _post_CustomerReceipt(self, d, eid):
        return self._settlement(d, eid, 'Sales')

    def _post_SupplierPayment(self, d, eid):
        return self._settlement(d, eid, 'Purchase')

    def _return(self, d, eid, kind):
        customer = kind == 'Sales'
        ikey, rkey, dkey = kind+'InvoiceID', kind+'ReturnID', kind+'InvoiceDetailID'
        invoice = self.require_posted(kind+'Invoice', d[ikey])
        require(d['ReturnDate'] >= invoice['InvoiceDate'], 'return precedes invoice')
        total = cost_total = 0
        for r in self._lines(kind+'ReturnDetail', rkey, d[rkey]):
            line = self.get(kind+'InvoiceDetail', r[dkey])
            require(line[ikey] == d[ikey], 'return invoice mismatch')
            prev = self.scalar(f'''SELECT COALESCE(sum(r.Quantity),0) FROM {kind}ReturnDetail r
                JOIN {kind}Return h USING({rkey}) WHERE r.{dkey}=? AND h.Status='POSTED' ''', (line[dkey],))
            limit = line['Quantity'] if customer else self.scalar('''SELECT COALESCE(sum(r.ReceivedQuantity),0) FROM GoodsReceiptDetail r
                JOIN GoodsReceipt h USING(GoodsReceiptID) WHERE r.PurchaseInvoiceDetailID=? AND h.Status='POSTED' ''', (line[dkey],))
            require(prev + r['Quantity'] <= limit, 'return exceeds eligible quantity')
            full_amount = line_amount(line['Quantity'], line['UnitPrice'])
            amount = rounded(full_amount * (prev + r['Quantity']), line['Quantity']) - rounded(full_amount * prev, line['Quantity'])
            total += amount
            if customer:
                require(d['WarehouseID'] == invoice['WarehouseID'], 'sales return warehouse mismatch')
                remaining = r['Quantity']
                for source in self.rows('SELECT * FROM StockAllocation WHERE SalesInvoiceDetailRef=? ORDER BY StockAllocationID', (line[dkey],)):
                    used, old_cost = self.conn.execute('''SELECT COALESCE(sum(Quantity),0),COALESCE(sum(CostAmount),0)
                        FROM StockAllocation WHERE OriginalAllocationID=? AND SalesReturnDetailRef IS NOT NULL''', (source['StockAllocationID'],)).fetchone()
                    available = -source['Quantity'] - used
                    qty = min(remaining, available)
                    if qty <= 0:
                        continue
                    cost = rounded((-source['CostAmount'] - old_cost) * qty, available)
                    self._move(eid, 'SalesReturnDetail', r['SalesReturnDetailID'], source['BatchID'], d['WarehouseID'], qty, cost, source['StockAllocationID'])
                    cost_total += cost
                    remaining -= qty
                    if not remaining:
                        break
                require(remaining == 0, 'original sale allocations missing')
            else:
                cost_total += self._take(eid, 'PurchaseReturnDetail', r['PurchaseReturnDetailID'], d['WarehouseID'], line['ProductID'], r['Quantity'], line[dkey])
        require(self.allocated(kind, d[ikey]) <= self.invoice_total(kind, d[ikey]) - total, 'return requires prior settlement correction')
        if customer:
            # Cash refunds are explicit cash outflow back to the same account.
            account = self.financial(invoice['FinancialAccountID']) if invoice['SaleType']=='CASH' else self.policy('Receivable')
            if invoice['SaleType']=='CASH':
                self._cash(eid, invoice['FinancialAccountID'], total, 'OUT')
            return [(self.policy('Revenue'), total, 0), (account, 0, total),
                    (self.policy('Inventory'), cost_total, 0), (self.policy('CostOfSales'), 0, cost_total)]
        # Freight stays payable; unrecovered landed cost is a documented return expense.
        difference = cost_total - total
        lines = [(self.policy('Payable'), total, 0), (self.policy('Inventory'), 0, cost_total)]
        if difference:
            lines.append((self.policy('Adjustment'), max(difference,0), max(-difference,0)))
        return lines

    def _post_SalesReturn(self, d, eid):
        return self._return(d, eid, 'Sales')

    def _post_PurchaseReturn(self, d, eid):
        return self._return(d, eid, 'Purchase')

    def freeze_count(self, ident):
        with self.transaction():
            d = self.get('InventoryCount', ident)
            require(d['Status'] == 'DRAFT', 'count already frozen')
            for line in self._lines('InventoryCountDetail','InventoryCountID',ident):
                current = self.scalar('SELECT CurrentQuantity FROM BatchStock WHERE WarehouseID=? AND BatchID=?', (d['WarehouseID'],line['BatchID'])) or 0
                require(current == line['SystemQuantity'], 'stale inventory count')
            self.conn.execute("UPDATE InventoryCount SET Status='POSTED' WHERE InventoryCountID=?", (ident,))

    def _post_InventoryAdjustment(self, d, eid):
        count = self.require_posted('InventoryCount', d['InventoryCountID'])
        require(d['AdjustmentDate'] >= count['CountDate'], 'adjustment precedes count')
        total = 0
        lines = self._lines('InventoryAdjustmentDetail','AdjustmentID',d['AdjustmentID'])
        changed = {r['InventoryCountDetailID'] for r in self.rows('SELECT * FROM InventoryCountDetail WHERE InventoryCountID=? AND ActualQuantity<>SystemQuantity', (d['InventoryCountID'],))}
        require({r['InventoryCountDetailID'] for r in lines} == changed, 'all count differences must be adjusted together')
        for r in lines:
            c = self.get('InventoryCountDetail',r['InventoryCountDetailID'])
            require(c['InventoryCountID'] == d['InventoryCountID'], 'adjustment count mismatch')
            diff = c['ActualQuantity'] - c['SystemQuantity']
            require(diff == r['QuantityDifference'], 'incorrect count difference')
            stock = self.rows('SELECT * FROM BatchStock WHERE WarehouseID=? AND BatchID=?', (count['WarehouseID'],c['BatchID']))
            current = stock[0]['CurrentQuantity'] if stock else 0
            require(current == c['SystemQuantity'], 'stock changed since count')
            b = self.get('InventoryBatch',c['BatchID'])
            cost = rounded((stock[0]['CostAmount'] if stock and current else b['TotalCost']) * diff, current or b['Quantity'])
            self._move(eid,'InventoryAdjustmentDetail',r['AdjustmentDetailID'],c['BatchID'],count['WarehouseID'],diff,cost)
            total += cost
        return [(self.policy('Inventory'),max(total,0),max(-total,0)), (self.policy('Adjustment'),max(-total,0),max(total,0))]

    def _post_Expense(self, d, eid):
        return [(self.policy('Expense'),d['Amount'],0), (self.policy('ExpensePayable'),0,d['Amount'])]

    def _post_DeliveryExpense(self, d, eid):
        self.require_posted('Delivery',d['DeliveryID'])
        return self._post_Expense(d,eid)

    def _post_ExpensePayment(self, d, eid):
        table, ident, ref = ('Expense',d['ExpenseRef'],'ExpenseRef') if d['ExpenseRef'] is not None else ('DeliveryExpense',d['DeliveryExpenseRef'],'DeliveryExpenseRef')
        source = self.require_posted(table,ident)
        require(d['PaymentDate'] >= source['ExpenseDate'], 'payment precedes expense')
        paid = self.scalar(f"SELECT COALESCE(sum(Amount),0) FROM ExpensePayment WHERE {ref}=? AND Status='POSTED'", (ident,))
        require(paid+d['Amount'] <= source['Amount'], 'expense overpayment')
        self._cash(eid,d['FinancialAccountID'],d['Amount'],'OUT')
        return [(self.policy('ExpensePayable'),d['Amount'],0),(self.financial(d['FinancialAccountID']),0,d['Amount'])]

    def _post_Payroll(self, d, eid):
        total = 0
        for r in self._lines('PayrollDetail','PayrollID',d['PayrollID']):
            require(self.get('Employee',r['EmployeeID'])['BranchID'] == d['BranchID'], 'payroll employee branch mismatch')
            total += r['NetSalary']
        return [(self.policy('PayrollExpense'),total,0),(self.policy('PayrollPayable'),0,total)]

    def _post_SalaryPayment(self, d, eid):
        r = self.get('PayrollDetail',d['PayrollDetailID'])
        payroll = self.require_posted('Payroll',r['PayrollID'])
        require(d['PaymentDate'] >= payroll['CreatedDate'], 'payment precedes payroll')
        paid = self.scalar("SELECT COALESCE(sum(Amount),0) FROM SalaryPayment WHERE PayrollDetailID=? AND Status='POSTED'", (d['PayrollDetailID'],))
        require(paid+d['Amount'] <= r['NetSalary'], 'salary overpayment')
        self._cash(eid,d['FinancialAccountID'],d['Amount'],'OUT')
        return [(self.policy('PayrollPayable'),d['Amount'],0),(self.financial(d['FinancialAccountID']),0,d['Amount'])]

    def _post_Delivery(self, d, eid):
        sale = self.require_posted('SalesInvoice',d['SalesInvoiceID'])
        require(self.get('Employee',d['EmployeeID'])['BranchID'] == sale['BranchID'], 'delivery employee branch mismatch')
        require(d['ActualDate'] >= sale['InvoiceDate'], 'delivery precedes sale')
        amount = d['DeliveryFee']
        if sale['SaleType']=='CASH':
            self._cash(eid,sale['FinancialAccountID'],amount,'IN')
            account = self.financial(sale['FinancialAccountID'])
        else:
            account = self.policy('Receivable')
        return [(account,amount,0),(self.policy('Revenue'),0,amount)]

    def _post_FinancialTransfer(self, d, eid):
        debit, credit = self.financial(d['ToAccountID']), self.financial(d['FromAccountID'])
        self._cash(eid,d['FromAccountID'],d['Amount'],'OUT')
        self._cash(eid,d['ToAccountID'],d['Amount'],'IN')
        return [(debit,d['Amount'],0),(credit,0,d['Amount'])]

    def _post_FixedAsset(self, d, eid):
        require(self.get('ChartOfAccounts',d['AccountID'])['AccountType']=='ASSET', 'asset account required')
        self._cash(eid,d['FinancialAccountID'],d['Cost'],'OUT')
        return [(d['AccountID'],d['Cost'],0),(self.financial(d['FinancialAccountID']),0,d['Cost'])]

    def depreciation_amount(self, asset):
        a = self.require_posted('FixedAsset',asset)
        previous = self.scalar("SELECT COALESCE(sum(Amount),0) FROM AssetDepreciation WHERE AssetID=? AND Status='POSTED'", (asset,))
        count = self.scalar("SELECT count(*) FROM AssetDepreciation WHERE AssetID=? AND Status='POSTED'", (asset,))
        require(count < a['UsefulLifeMonths'], 'asset fully depreciated')
        return rounded((a['Cost']-a['SalvageValue'])*(count+1),a['UsefulLifeMonths']) - previous

    def _post_AssetDepreciation(self, d, eid):
        asset = self.require_posted('FixedAsset',d['AssetID'])
        require(not self.scalar("SELECT count(*) FROM AssetDisposal WHERE AssetID=? AND Status='POSTED'", (d['AssetID'],)), 'asset disposed')
        require(d['DepreciationDate'] >= asset['PurchaseDate'], 'depreciation precedes purchase')
        p = self.get('AccountingPeriod',d['AccountingPeriodID'])
        require(p['StartDate'] <= d['DepreciationDate'] <= p['EndDate'], 'depreciation period mismatch')
        start, end = date.fromisoformat(p['StartDate']),date.fromisoformat(p['EndDate'])
        require(start.day==1 and start.year==end.year and start.month==end.month and end.day==monthrange(end.year,end.month)[1], 'depreciation needs a calendar month period')
        count = self.scalar("SELECT count(*) FROM AssetDepreciation WHERE AssetID=? AND Status='POSTED'", (d['AssetID'],))
        purchase = date.fromisoformat(asset['PurchaseDate'])
        require(start.year*12+start.month == purchase.year*12+purchase.month+count, 'depreciation must follow consecutive months from purchase')
        require(d['Amount'] == self.depreciation_amount(d['AssetID']), 'incorrect straight line depreciation')
        return [(self.policy('DepreciationExpense'),d['Amount'],0),(self.policy('AccumulatedDepreciation'),0,d['Amount'])]

    def _post_AssetDisposal(self, d, eid):
        a = self.require_posted('FixedAsset',d['AssetID'])
        require(d['DisposalDate'] >= a['PurchaseDate'], 'disposal precedes purchase')
        dep = self.scalar("SELECT COALESCE(sum(Amount),0) FROM AssetDepreciation WHERE AssetID=? AND Status='POSTED'", (d['AssetID'],))
        latest = self.scalar("SELECT max(DepreciationDate) FROM AssetDepreciation WHERE AssetID=? AND Status='POSTED'", (d['AssetID'],))
        require(latest is None or d['DisposalDate'] >= latest, 'disposal precedes depreciation')
        gain = d['SaleProceeds'] - (a['Cost']-dep)
        lines=[(a['AccountID'],0,a['Cost']), (self.policy('AccumulatedDepreciation'),dep,0)]
        if d['SaleProceeds']:
            self._cash(eid,d['FinancialAccountID'],d['SaleProceeds'],'IN')
            lines.append((self.financial(d['FinancialAccountID']),d['SaleProceeds'],0))
        if gain:
            lines.append((self.policy('DisposalGain') if gain>0 else self.policy('DisposalLoss'),max(-gain,0),max(gain,0)))
        return lines

    def manual_entry(self, day, lines, description, reversal_of=None):
        with self.transaction():
            require(len(lines)>=2 and any(d>0 for _,d,_ in lines), 'manual entry needs positive debit and at least two lines')
            if reversal_of is not None:
                original = self.require_posted('JournalEntry',reversal_of)
                require(original['SourceType']=='ManualJournal', 'business document reversal needs a dedicated subledger correction')
                require(day >= original['EntryDate'], 'reversal precedes original')
                expected = [(r['AccountID'],r['Credit'],r['Debit']) for r in self.rows('SELECT * FROM JournalEntryDetail WHERE JournalEntryID=? ORDER BY JournalEntryDetailID', (reversal_of,))]
                require(list(lines)==expected, 'reversal must exactly reverse original')
            mid = self.add('ManualJournal',EntryDate=day,Description=description)
            eid = self._event('ManualJournal',mid,day)
            jid = self._journal(eid,lines,description,reversal_of)
            self.conn.execute("UPDATE PostingEvent SET Status='POSTED' WHERE EventID=?", (eid,))
            self.conn.execute("UPDATE ManualJournal SET Status='POSTED' WHERE ManualJournalID=?", (mid,))
            self._insert('AuditLog',UserID=self.actor_user_id,ActionType='POST',EntityName='ManualJournal',AffectedRecordID=mid,
                     NewValues=json.dumps({'EventID':eid,'JournalEntryID':jid,'Reverses':reversal_of}),
                     ActionAt=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
            return jid

    def check(self):
        require(self.scalar('PRAGMA integrity_check')=='ok', 'SQLite integrity failure')
        require(not self.rows('PRAGMA foreign_key_check'), 'foreign key violation')
        require(not self.rows('''SELECT WarehouseID,ProductID FROM (
            SELECT WarehouseID,ProductID,CurrentQuantity q FROM InventoryBalance
            UNION ALL SELECT s.WarehouseID,b.ProductID,-s.CurrentQuantity FROM BatchStock s JOIN InventoryBatch b USING(BatchID))
            GROUP BY WarehouseID,ProductID HAVING sum(q)<>0'''), 'inventory and batch balance mismatch')
        require(not self.rows('''SELECT j.JournalEntryID FROM JournalEntry j JOIN JournalEntryDetail d USING(JournalEntryID)
            WHERE j.Status='POSTED' GROUP BY j.JournalEntryID HAVING sum(d.Debit)<>sum(d.Credit) OR count(*)<2 OR sum(d.Debit)<=0'''), 'unbalanced posted journal')
        require(not self.rows("SELECT EventID FROM PostingEvent WHERE Status<>'POSTED'"), 'incomplete posting event')
        require(not self.rows('''SELECT WarehouseID,BatchID FROM (
            SELECT WarehouseID,BatchID,CurrentQuantity q,CostAmount c FROM BatchStock
            UNION ALL SELECT WarehouseID,BatchID,-Quantity,-CostAmount FROM InventoryMovement)
            GROUP BY WarehouseID,BatchID HAVING sum(q)<>0 OR sum(c)<>0'''), 'stock does not match movement ledger')
        require(not self.rows('''WITH expected AS (
            SELECT t.EventID,f.PostingAccountID AccountID,sum(CASE WHEN t.TransactionType='IN' THEN t.Amount ELSE -t.Amount END) amount
            FROM FinancialTransaction t JOIN FinancialAccount f USING(FinancialAccountID) GROUP BY t.EventID,f.PostingAccountID)
            SELECT e.EventID FROM expected e WHERE e.amount<>(SELECT COALESCE(sum(d.Debit-d.Credit),0)
            FROM JournalEntry j JOIN JournalEntryDetail d USING(JournalEntryID) WHERE j.EventID=e.EventID AND d.AccountID=e.AccountID)'''), 'financial transaction does not match journal')


def main():
    parser=argparse.ArgumentParser(description='Initialize and verify the demo SQLite database')
    parser.add_argument('path')
    parser.add_argument('--seed',action='store_true')
    args=parser.parse_args()
    db=Database(args.path)
    try:
        db.migrate()
        if args.seed:
            db.seed()
        db.check()
        print('SQLite migration and integrity checks: OK')
    finally:
        db.close()


if __name__=='__main__':
    main()
