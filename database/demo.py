"""Build a fictional worked example; refuse to overwrite an existing file."""
from pathlib import Path
import argparse

from .engine import Database, money, quantity, require


def populate(db):
    """Call on a seeded database. All example postings commit or roll back together."""
    a = db.add
    with db.transaction():
        purchase = a('PurchaseInvoice',SupplierID=1,BranchID=1,InvoiceDate='2026-01-02')
        p1 = a('PurchaseInvoiceDetail',PurchaseInvoiceID=purchase,ProductID=1,Quantity=quantity('10'),UnitPrice=money('5'))
        p2 = a('PurchaseInvoiceDetail',PurchaseInvoiceID=purchase,ProductID=2,Quantity=quantity('2.5'),UnitPrice=money('8'))
        db.post('PurchaseInvoice',purchase)
        freight = a('PurchaseFreight',PurchaseInvoiceID=purchase,Amount=money('7'),FreightDate='2026-01-03',Description='نقل تجريبي لازم لوصول البضاعة',Treatment='INVENTORY')
        a('FreightAllocation',FreightID=freight,PurchaseInvoiceDetailID=p1,AllocatedAmount=money('5'),AllocationBasis='VALUE')
        a('FreightAllocation',FreightID=freight,PurchaseInvoiceDetailID=p2,AllocatedAmount=money('2'),AllocationBasis='VALUE')
        db.post('PurchaseFreight',freight)
        for qty in ('4','6'):
            receipt = a('GoodsReceipt',PurchaseInvoiceID=purchase,WarehouseID=1,ReceiptDate='2026-01-04')
            line = a('GoodsReceiptDetail',GoodsReceiptID=receipt,PurchaseInvoiceDetailID=p1,ReceivedQuantity=quantity(qty))
            a('InventoryBatch',ProductID=1,GoodsReceiptDetailID=line,Quantity=quantity(qty),ManufacturerLot='DEMO-FACTORY-LOT')
            db.post('GoodsReceipt',receipt)
        receipt = a('GoodsReceipt',PurchaseInvoiceID=purchase,WarehouseID=1,ReceiptDate='2026-01-04')
        line = a('GoodsReceiptDetail',GoodsReceiptID=receipt,PurchaseInvoiceDetailID=p2,ReceivedQuantity=quantity('2.5'))
        a('InventoryBatch',ProductID=2,GoodsReceiptDetailID=line,Quantity=quantity('2.5'),ManufacturerLot='DEMO-LOT-B')
        db.post('GoodsReceipt',receipt)
        sales = []
        for kind in ('CASH','CREDIT','CREDIT'):
            sale = a('SalesInvoice',BranchID=1,CustomerID=1 if kind=='CREDIT' else None,WarehouseID=1,
                     InvoiceDate='2026-01-05',SaleType=kind,FinancialAccountID=1 if kind=='CASH' else None)
            sl = a('SalesInvoiceDetail',SalesInvoiceID=sale,ProductID=1,Quantity=quantity('1'),UnitPrice=money('8'))
            db.post('SalesInvoice',sale)
            sales.append((sale,sl))
        receipt = a('CustomerReceipt',CustomerID=1,FinancialAccountID=1,ReceiptDate='2026-01-06',Amount=money('10'),PaymentMethod='CASH')
        for sale,_ in sales[1:]:
            a('ReceiptAllocation',ReceiptID=receipt,SalesInvoiceID=sale,AllocatedAmount=money('4'))
        db.post('CustomerReceipt',receipt)
        payment = a('SupplierPayment',SupplierID=1,FinancialAccountID=2,PaymentDate='2026-01-06',Amount=money('20'),PaymentMethod='BANK')
        a('SupplierPaymentAllocation',SupplierPaymentID=payment,PurchaseInvoiceID=purchase,AllocatedAmount=money('20'))
        db.post('SupplierPayment',payment)
        transfer = a('StockTransfer',FromWarehouseID=1,ToWarehouseID=2,TransferDate='2026-01-07')
        tl = a('StockTransferDetail',TransferID=transfer,ProductID=1,Quantity=quantity('2'))
        db.post('StockTransfer',transfer)
        arrival = a('StockTransferReceipt',TransferID=transfer,ReceiptDate='2026-01-08')
        a('StockTransferReceiptDetail',TransferReceiptID=arrival,TransferDetailID=tl,ReceivedQuantity=quantity('1'))
        db.post('StockTransferReceipt',arrival)
        ret = a('SalesReturn',SalesInvoiceID=sales[1][0],WarehouseID=1,ReturnDate='2026-01-09',Reason='مرتجع تجريبي')
        a('SalesReturnDetail',SalesReturnID=ret,SalesInvoiceDetailID=sales[1][1],Quantity=quantity('0.5'))
        db.post('SalesReturn',ret)
        ret = a('PurchaseReturn',PurchaseInvoiceID=purchase,WarehouseID=1,ReturnDate='2026-01-10',Reason='مرتجع تجريبي')
        a('PurchaseReturnDetail',PurchaseReturnID=ret,PurchaseInvoiceDetailID=p2,Quantity=quantity('0.5'))
        db.post('PurchaseReturn',ret)
        expense = a('Expense',BranchID=1,ExpenseCategoryID=1,FinancialAccountID=1,ExpenseDate='2026-01-10',Amount=money('3'),Description='مصروف تجريبي مدفوع')
        db.post('Expense',expense)
        payroll = a('Payroll',BranchID=1,PayrollMonth=1,PayrollYear=2026,CreatedDate='2026-01-25')
        pd = a('PayrollDetail',PayrollID=payroll,EmployeeID=1,BasicSalary=money('100'),NetSalary=money('100'))
        db.post('Payroll',payroll)
        salary = a('SalaryPayment',PayrollDetailID=pd,FinancialAccountID=2,PaymentDate='2026-01-26',Amount=money('100'),PaymentMethod='BANK')
        db.post('SalaryPayment',salary)
        asset = a('FixedAsset',BranchID=1,AccountID=19,AssetName='أصل تجريبي',PurchaseDate='2026-01-01',Cost=money('120'),UsefulLifeMonths=12,SalvageValue=0,FinancialAccountID=2)
        db.post('FixedAsset',asset)
        depreciation = a('AssetDepreciation',AssetID=asset,AccountingPeriodID=1,Amount=money('10'),DepreciationDate='2026-01-31')
        db.post('AssetDepreciation',depreciation)
        db.check()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path')
    args=parser.parse_args()
    require(not Path(args.path).exists(),'choose a new path; demo never overwrites a database')
    db=Database(args.path)
    try:
        db.migrate()
        db.seed()
        populate(db)
        print(f"Demo: {db.scalar('SELECT count(*) FROM PostingEvent')} posted events; integrity, stock and journal checks: OK")
    finally:
        db.close()


if __name__=='__main__':
    main()
