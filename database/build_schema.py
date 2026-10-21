"""Render the portable table definitions and documented SQLite guards."""
from pathlib import Path

TABLES = {}


def table(name, columns):
    TABLES[name] = columns.strip()


table('SchemaMigration', 'Version INTEGER PRIMARY KEY, AppliedAt TEXT NOT NULL')
table('SystemSetting', '''SettingID INTEGER PRIMARY KEY CHECK(SettingID=1),
 CurrencyName TEXT NOT NULL, MoneyScale INTEGER NOT NULL CHECK(MoneyScale=100),
 QuantityScale INTEGER NOT NULL CHECK(QuantityScale=1000)''')
table('Branch', 'BranchID INTEGER PRIMARY KEY, Name TEXT NOT NULL UNIQUE, City TEXT')
table('Warehouse', 'WarehouseID INTEGER PRIMARY KEY, Name TEXT NOT NULL UNIQUE, BranchID INTEGER REFERENCES Branch')
table('Category', 'CategoryID INTEGER PRIMARY KEY, Name TEXT NOT NULL UNIQUE')
table('Product', '''ProductID INTEGER PRIMARY KEY, Name TEXT NOT NULL, Unit TEXT NOT NULL,
 CategoryID INTEGER NOT NULL REFERENCES Category, UNIQUE(Name,Unit)''')
table('Supplier', 'SupplierID INTEGER PRIMARY KEY, Name TEXT NOT NULL, Phone TEXT')
table('SupplierProduct', '''SupplierProductID INTEGER PRIMARY KEY, SupplierID INTEGER NOT NULL REFERENCES Supplier,
 ProductID INTEGER NOT NULL REFERENCES Product, UNIQUE(SupplierID,ProductID)''')
table('Customer', 'CustomerID INTEGER PRIMARY KEY, Name TEXT NOT NULL, Phone TEXT, Address TEXT')
table('ChartOfAccounts', '''AccountID INTEGER PRIMARY KEY, AccountCode TEXT NOT NULL UNIQUE,
 AccountName TEXT NOT NULL, AccountType TEXT NOT NULL CHECK(AccountType IN ('ASSET','LIABILITY','EQUITY','REVENUE','EXPENSE')),
 ParentAccountID INTEGER REFERENCES ChartOfAccounts, IsPostingAllowed INTEGER NOT NULL DEFAULT 1 CHECK(IsPostingAllowed IN (0,1)),
 CHECK(ParentAccountID IS NULL OR ParentAccountID<>AccountID)''')
table('FinancialAccountType', 'AccountTypeID INTEGER PRIMARY KEY, TypeName TEXT NOT NULL UNIQUE')
table('FinancialAccount', '''FinancialAccountID INTEGER PRIMARY KEY, AccountTypeID INTEGER NOT NULL REFERENCES FinancialAccountType,
 BranchID INTEGER REFERENCES Branch, PostingAccountID INTEGER NOT NULL REFERENCES ChartOfAccounts,
 AccountName TEXT NOT NULL UNIQUE''')
table('AccountingPolicy', '''PolicyID INTEGER PRIMARY KEY CHECK(PolicyID=1),
 InventoryAccountID INTEGER NOT NULL REFERENCES ChartOfAccounts,
 ClearingAccountID INTEGER NOT NULL REFERENCES ChartOfAccounts,
 ReceivableAccountID INTEGER NOT NULL REFERENCES ChartOfAccounts,
 PayableAccountID INTEGER NOT NULL REFERENCES ChartOfAccounts,
 RevenueAccountID INTEGER NOT NULL REFERENCES ChartOfAccounts,
 CostOfSalesAccountID INTEGER NOT NULL REFERENCES ChartOfAccounts,
 ExpenseAccountID INTEGER NOT NULL REFERENCES ChartOfAccounts,
 PayrollExpenseAccountID INTEGER NOT NULL REFERENCES ChartOfAccounts,
 PayrollPayableAccountID INTEGER NOT NULL REFERENCES ChartOfAccounts,
 ExpensePayableAccountID INTEGER NOT NULL REFERENCES ChartOfAccounts,
 TransitAccountID INTEGER NOT NULL REFERENCES ChartOfAccounts,
 AdjustmentAccountID INTEGER NOT NULL REFERENCES ChartOfAccounts,
 DepreciationExpenseAccountID INTEGER NOT NULL REFERENCES ChartOfAccounts,
 AccumulatedDepreciationAccountID INTEGER NOT NULL REFERENCES ChartOfAccounts,
 DisposalGainAccountID INTEGER NOT NULL REFERENCES ChartOfAccounts,
 DisposalLossAccountID INTEGER NOT NULL REFERENCES ChartOfAccounts''')
table('FinancialYear', '''FinancialYearID INTEGER PRIMARY KEY, Name TEXT NOT NULL UNIQUE,
 StartDate TEXT NOT NULL, EndDate TEXT NOT NULL, Status TEXT NOT NULL DEFAULT 'OPEN' CHECK(Status IN ('OPEN','CLOSED')),
 CHECK(StartDate<=EndDate)''')
table('AccountingPeriod', '''AccountingPeriodID INTEGER PRIMARY KEY, FinancialYearID INTEGER NOT NULL REFERENCES FinancialYear,
 Name TEXT NOT NULL, StartDate TEXT NOT NULL, EndDate TEXT NOT NULL,
 Status TEXT NOT NULL DEFAULT 'OPEN' CHECK(Status IN ('OPEN','CLOSED')), CHECK(StartDate<=EndDate),
 UNIQUE(FinancialYearID,Name)''')
table('PurchaseInvoice', '''PurchaseInvoiceID INTEGER PRIMARY KEY, SupplierID INTEGER NOT NULL REFERENCES Supplier,
 BranchID INTEGER REFERENCES Branch, InvoiceDate TEXT NOT NULL, Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED'))''')
table('PurchaseInvoiceDetail', '''PurchaseInvoiceDetailID INTEGER PRIMARY KEY,
 PurchaseInvoiceID INTEGER NOT NULL REFERENCES PurchaseInvoice, ProductID INTEGER NOT NULL REFERENCES Product,
 Quantity INTEGER NOT NULL CHECK(Quantity>0), UnitPrice INTEGER NOT NULL CHECK(UnitPrice>0)''')
table('GoodsReceipt', '''GoodsReceiptID INTEGER PRIMARY KEY, PurchaseInvoiceID INTEGER NOT NULL REFERENCES PurchaseInvoice,
 WarehouseID INTEGER NOT NULL REFERENCES Warehouse, ReceiptDate TEXT NOT NULL,
 Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED'))''')
table('GoodsReceiptDetail', '''GoodsReceiptDetailID INTEGER PRIMARY KEY, GoodsReceiptID INTEGER NOT NULL REFERENCES GoodsReceipt,
 PurchaseInvoiceDetailID INTEGER NOT NULL REFERENCES PurchaseInvoiceDetail,
 ReceivedQuantity INTEGER NOT NULL CHECK(ReceivedQuantity>0), UNIQUE(GoodsReceiptID,PurchaseInvoiceDetailID)''')
table('PurchaseFreight', '''FreightID INTEGER PRIMARY KEY, PurchaseInvoiceID INTEGER NOT NULL REFERENCES PurchaseInvoice,
 Amount INTEGER NOT NULL CHECK(Amount>0), FreightDate TEXT NOT NULL, Description TEXT NOT NULL,
 Treatment TEXT NOT NULL CHECK(Treatment IN ('INVENTORY','EXPENSE')),
 ExpenseEligible INTEGER NOT NULL DEFAULT 0 CHECK(ExpenseEligible IN (0,1)), EligibilityReason TEXT,
 Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED')),
 CHECK(Treatment<>'EXPENSE' OR (ExpenseEligible=1 AND length(trim(EligibilityReason))>0 AND EligibilityReason IS NOT NULL))''')
table('FreightAllocation', '''FreightAllocationID INTEGER PRIMARY KEY, FreightID INTEGER NOT NULL REFERENCES PurchaseFreight,
 PurchaseInvoiceDetailID INTEGER NOT NULL REFERENCES PurchaseInvoiceDetail,
 AllocatedAmount INTEGER NOT NULL CHECK(AllocatedAmount>=0),
 AllocationBasis TEXT NOT NULL CHECK(AllocationBasis IN ('VALUE','QUANTITY','WEIGHT','MANUAL')),
 UNIQUE(FreightID,PurchaseInvoiceDetailID)''')
table('InventoryBatch', '''BatchID INTEGER PRIMARY KEY, ProductID INTEGER NOT NULL REFERENCES Product,
 GoodsReceiptDetailID INTEGER NOT NULL REFERENCES GoodsReceiptDetail, ManufacturerLot TEXT,
 ProductionDate TEXT, ExpiryDate TEXT, Quantity INTEGER NOT NULL CHECK(Quantity>0),
 UnitCost INTEGER NOT NULL DEFAULT 0 CHECK(UnitCost>=0), TotalCost INTEGER NOT NULL DEFAULT 0 CHECK(TotalCost>=0),
 CHECK(ProductionDate IS NULL OR ExpiryDate IS NULL OR ProductionDate<=ExpiryDate)''')
table('InventoryBalance', '''WarehouseID INTEGER NOT NULL REFERENCES Warehouse, ProductID INTEGER NOT NULL REFERENCES Product,
 CurrentQuantity INTEGER NOT NULL CHECK(CurrentQuantity>=0), PRIMARY KEY(WarehouseID,ProductID)''')
table('BatchStock', '''WarehouseID INTEGER NOT NULL REFERENCES Warehouse, BatchID INTEGER NOT NULL REFERENCES InventoryBatch,
 CurrentQuantity INTEGER NOT NULL CHECK(CurrentQuantity>=0), CostAmount INTEGER NOT NULL CHECK(CostAmount>=0),
 PRIMARY KEY(WarehouseID,BatchID), CHECK(CurrentQuantity>0 OR CostAmount=0)''')
table('StockTransfer', '''TransferID INTEGER PRIMARY KEY, FromWarehouseID INTEGER NOT NULL REFERENCES Warehouse,
 ToWarehouseID INTEGER NOT NULL REFERENCES Warehouse, TransferDate TEXT NOT NULL,
 Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED')), CHECK(FromWarehouseID<>ToWarehouseID)''')
table('StockTransferDetail', '''TransferDetailID INTEGER PRIMARY KEY, TransferID INTEGER NOT NULL REFERENCES StockTransfer,
 ProductID INTEGER NOT NULL REFERENCES Product, Quantity INTEGER NOT NULL CHECK(Quantity>0), UNIQUE(TransferID,ProductID)''')
table('StockTransferReceipt', '''TransferReceiptID INTEGER PRIMARY KEY, TransferID INTEGER NOT NULL REFERENCES StockTransfer,
 ReceiptDate TEXT NOT NULL, Notes TEXT, Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED'))''')
table('StockTransferReceiptDetail', '''TransferReceiptDetailID INTEGER PRIMARY KEY,
 TransferReceiptID INTEGER NOT NULL REFERENCES StockTransferReceipt, TransferDetailID INTEGER NOT NULL REFERENCES StockTransferDetail,
 ReceivedQuantity INTEGER NOT NULL CHECK(ReceivedQuantity>0), UNIQUE(TransferReceiptID,TransferDetailID)''')
table('InventoryCount', '''InventoryCountID INTEGER PRIMARY KEY, WarehouseID INTEGER NOT NULL REFERENCES Warehouse,
 CountDate TEXT NOT NULL, Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED'))''')
table('InventoryCountDetail', '''InventoryCountDetailID INTEGER PRIMARY KEY, InventoryCountID INTEGER NOT NULL REFERENCES InventoryCount,
 BatchID INTEGER NOT NULL REFERENCES InventoryBatch, SystemQuantity INTEGER NOT NULL CHECK(SystemQuantity>=0),
 ActualQuantity INTEGER NOT NULL CHECK(ActualQuantity>=0), UNIQUE(InventoryCountID,BatchID)''')
table('InventoryAdjustment', '''AdjustmentID INTEGER PRIMARY KEY, InventoryCountID INTEGER NOT NULL UNIQUE REFERENCES InventoryCount,
 AdjustmentDate TEXT NOT NULL, Reason TEXT NOT NULL CHECK(length(trim(Reason))>0),
 Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED'))''')
table('InventoryAdjustmentDetail', '''AdjustmentDetailID INTEGER PRIMARY KEY, AdjustmentID INTEGER NOT NULL REFERENCES InventoryAdjustment,
 InventoryCountDetailID INTEGER NOT NULL UNIQUE REFERENCES InventoryCountDetail, QuantityDifference INTEGER NOT NULL CHECK(QuantityDifference<>0)''')
table('SalesInvoice', '''SalesInvoiceID INTEGER PRIMARY KEY, BranchID INTEGER NOT NULL REFERENCES Branch,
 CustomerID INTEGER REFERENCES Customer, WarehouseID INTEGER NOT NULL REFERENCES Warehouse,
 InvoiceDate TEXT NOT NULL, SaleType TEXT NOT NULL CHECK(SaleType IN ('CASH','CREDIT')),
 FinancialAccountID INTEGER REFERENCES FinancialAccount, Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED')),
 CHECK((SaleType='CREDIT' AND CustomerID IS NOT NULL AND FinancialAccountID IS NULL) OR (SaleType='CASH' AND FinancialAccountID IS NOT NULL))''')
table('SalesInvoiceDetail', '''SalesInvoiceDetailID INTEGER PRIMARY KEY, SalesInvoiceID INTEGER NOT NULL REFERENCES SalesInvoice,
 ProductID INTEGER NOT NULL REFERENCES Product, Quantity INTEGER NOT NULL CHECK(Quantity>0), UnitPrice INTEGER NOT NULL CHECK(UnitPrice>0)''')
table('CustomerReceipt', '''ReceiptID INTEGER PRIMARY KEY, CustomerID INTEGER NOT NULL REFERENCES Customer,
 FinancialAccountID INTEGER REFERENCES FinancialAccount, ReceiptDate TEXT NOT NULL, Amount INTEGER NOT NULL CHECK(Amount>0),
 PaymentMethod TEXT NOT NULL CHECK(PaymentMethod IN ('CASH','BANK','CARD')),
 Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED')), CHECK(Status<>'POSTED' OR FinancialAccountID IS NOT NULL)''')
table('ReceiptAllocation', '''AllocationID INTEGER PRIMARY KEY, ReceiptID INTEGER NOT NULL REFERENCES CustomerReceipt,
 SalesInvoiceID INTEGER NOT NULL REFERENCES SalesInvoice, AllocatedAmount INTEGER NOT NULL CHECK(AllocatedAmount>0), UNIQUE(ReceiptID,SalesInvoiceID)''')
table('SupplierPayment', '''SupplierPaymentID INTEGER PRIMARY KEY, SupplierID INTEGER NOT NULL REFERENCES Supplier,
 FinancialAccountID INTEGER REFERENCES FinancialAccount, PaymentDate TEXT NOT NULL, Amount INTEGER NOT NULL CHECK(Amount>0),
 PaymentMethod TEXT NOT NULL CHECK(PaymentMethod IN ('CASH','BANK','CARD')),
 Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED')), CHECK(Status<>'POSTED' OR FinancialAccountID IS NOT NULL)''')
table('SupplierPaymentAllocation', '''AllocationID INTEGER PRIMARY KEY, SupplierPaymentID INTEGER NOT NULL REFERENCES SupplierPayment,
 PurchaseInvoiceID INTEGER NOT NULL REFERENCES PurchaseInvoice, AllocatedAmount INTEGER NOT NULL CHECK(AllocatedAmount>0),
 UNIQUE(SupplierPaymentID,PurchaseInvoiceID)''')
table('SalesReturn', '''SalesReturnID INTEGER PRIMARY KEY, SalesInvoiceID INTEGER NOT NULL REFERENCES SalesInvoice,
 WarehouseID INTEGER NOT NULL REFERENCES Warehouse, ReturnDate TEXT NOT NULL, Reason TEXT NOT NULL,
 Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED'))''')
table('SalesReturnDetail', '''SalesReturnDetailID INTEGER PRIMARY KEY, SalesReturnID INTEGER NOT NULL REFERENCES SalesReturn,
 SalesInvoiceDetailID INTEGER NOT NULL REFERENCES SalesInvoiceDetail, Quantity INTEGER NOT NULL CHECK(Quantity>0),
 UNIQUE(SalesReturnID,SalesInvoiceDetailID)''')
table('PurchaseReturn', '''PurchaseReturnID INTEGER PRIMARY KEY, PurchaseInvoiceID INTEGER NOT NULL REFERENCES PurchaseInvoice,
 WarehouseID INTEGER NOT NULL REFERENCES Warehouse, ReturnDate TEXT NOT NULL, Reason TEXT NOT NULL,
 Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED'))''')
table('PurchaseReturnDetail', '''PurchaseReturnDetailID INTEGER PRIMARY KEY, PurchaseReturnID INTEGER NOT NULL REFERENCES PurchaseReturn,
 PurchaseInvoiceDetailID INTEGER NOT NULL REFERENCES PurchaseInvoiceDetail, Quantity INTEGER NOT NULL CHECK(Quantity>0),
 UNIQUE(PurchaseReturnID,PurchaseInvoiceDetailID)''')
table('ExpenseCategory', 'ExpenseCategoryID INTEGER PRIMARY KEY, CategoryName TEXT NOT NULL UNIQUE')
table('Expense', '''ExpenseID INTEGER PRIMARY KEY, BranchID INTEGER NOT NULL REFERENCES Branch,
 ExpenseCategoryID INTEGER NOT NULL REFERENCES ExpenseCategory, FinancialAccountID INTEGER REFERENCES FinancialAccount,
 ExpenseDate TEXT NOT NULL, Amount INTEGER NOT NULL CHECK(Amount>0), Description TEXT NOT NULL,
 Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED')), PaidDate TEXT''')
table('Employee', '''EmployeeID INTEGER PRIMARY KEY, BranchID INTEGER NOT NULL REFERENCES Branch,
 EmployeeName TEXT NOT NULL, JobTitle TEXT, HireDate TEXT NOT NULL''')
table('Payroll', '''PayrollID INTEGER PRIMARY KEY, BranchID INTEGER NOT NULL REFERENCES Branch,
 PayrollMonth INTEGER NOT NULL CHECK(PayrollMonth BETWEEN 1 AND 12), PayrollYear INTEGER NOT NULL CHECK(PayrollYear BETWEEN 1900 AND 9999),
 Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED')), CreatedDate TEXT NOT NULL,
 UNIQUE(BranchID,PayrollMonth,PayrollYear)''')
table('PayrollDetail', '''PayrollDetailID INTEGER PRIMARY KEY, PayrollID INTEGER NOT NULL REFERENCES Payroll,
 EmployeeID INTEGER NOT NULL REFERENCES Employee, BasicSalary INTEGER NOT NULL CHECK(BasicSalary>=0),
 Allowances INTEGER NOT NULL DEFAULT 0 CHECK(Allowances>=0), Deductions INTEGER NOT NULL DEFAULT 0 CHECK(Deductions>=0),
 NetSalary INTEGER NOT NULL CHECK(NetSalary>0 AND NetSalary=BasicSalary+Allowances-Deductions), UNIQUE(PayrollID,EmployeeID)''')
table('SalaryPayment', '''SalaryPaymentID INTEGER PRIMARY KEY, PayrollDetailID INTEGER NOT NULL REFERENCES PayrollDetail,
 FinancialAccountID INTEGER REFERENCES FinancialAccount, PaymentDate TEXT NOT NULL, Amount INTEGER NOT NULL CHECK(Amount>0),
 PaymentMethod TEXT NOT NULL CHECK(PaymentMethod IN ('CASH','BANK','CARD')),
 Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED')), CHECK(Status<>'POSTED' OR FinancialAccountID IS NOT NULL)''')
table('Delivery', '''DeliveryID INTEGER PRIMARY KEY, SalesInvoiceID INTEGER NOT NULL REFERENCES SalesInvoice,
 EmployeeID INTEGER NOT NULL REFERENCES Employee, DeliveryAddress TEXT NOT NULL, ExpectedDate TEXT NOT NULL,
 ActualDate TEXT, Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED')),
 DeliveryFee INTEGER NOT NULL DEFAULT 0 CHECK(DeliveryFee>=0)''')
table('DeliveryExpense', '''DeliveryExpenseID INTEGER PRIMARY KEY, DeliveryID INTEGER NOT NULL REFERENCES Delivery,
 FinancialAccountID INTEGER REFERENCES FinancialAccount, ExpenseType TEXT NOT NULL, Amount INTEGER NOT NULL CHECK(Amount>0),
 ExpenseDate TEXT NOT NULL, Notes TEXT, PaidDate TEXT,
 Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED'))''')
table('FinancialTransfer', '''TransferID INTEGER PRIMARY KEY, FromAccountID INTEGER NOT NULL REFERENCES FinancialAccount,
 ToAccountID INTEGER NOT NULL REFERENCES FinancialAccount, TransferDate TEXT NOT NULL, Amount INTEGER NOT NULL CHECK(Amount>0), Notes TEXT,
 Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED')), CHECK(FromAccountID<>ToAccountID)''')
table('FixedAsset', '''AssetID INTEGER PRIMARY KEY, BranchID INTEGER NOT NULL REFERENCES Branch,
 AccountID INTEGER NOT NULL REFERENCES ChartOfAccounts, AssetName TEXT NOT NULL, PurchaseDate TEXT NOT NULL,
 Cost INTEGER NOT NULL CHECK(Cost>0), UsefulLifeMonths INTEGER NOT NULL CHECK(UsefulLifeMonths>0),
 SalvageValue INTEGER NOT NULL DEFAULT 0 CHECK(SalvageValue>=0 AND SalvageValue<Cost),
 FinancialAccountID INTEGER NOT NULL REFERENCES FinancialAccount,
 Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED'))''')
table('AssetDepreciation', '''DepreciationID INTEGER PRIMARY KEY, AssetID INTEGER NOT NULL REFERENCES FixedAsset,
 AccountingPeriodID INTEGER NOT NULL REFERENCES AccountingPeriod, JournalEntryID INTEGER UNIQUE REFERENCES JournalEntry,
 Amount INTEGER NOT NULL CHECK(Amount>=0), DepreciationDate TEXT NOT NULL,
 Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED')), UNIQUE(AssetID,AccountingPeriodID)''')
table('AssetDisposal', '''DisposalID INTEGER PRIMARY KEY, AssetID INTEGER NOT NULL UNIQUE REFERENCES FixedAsset,
 JournalEntryID INTEGER UNIQUE REFERENCES JournalEntry, DisposalDate TEXT NOT NULL, Reason TEXT NOT NULL,
 SaleProceeds INTEGER NOT NULL CHECK(SaleProceeds>=0), FinancialAccountID INTEGER REFERENCES FinancialAccount,
 Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED')), CHECK(SaleProceeds=0 OR FinancialAccountID IS NOT NULL)''')

table('ExpensePayment', '''ExpensePaymentID INTEGER PRIMARY KEY, ExpenseRef INTEGER REFERENCES Expense(ExpenseID),
 DeliveryExpenseRef INTEGER REFERENCES DeliveryExpense(DeliveryExpenseID), FinancialAccountID INTEGER NOT NULL REFERENCES FinancialAccount,
 PaymentDate TEXT NOT NULL, Amount INTEGER NOT NULL CHECK(Amount>0),
 Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED')),
 CHECK((ExpenseRef IS NOT NULL)+(DeliveryExpenseRef IS NOT NULL)=1)''')
table('ManualJournal', '''ManualJournalID INTEGER PRIMARY KEY, EntryDate TEXT NOT NULL,
 Description TEXT NOT NULL CHECK(length(trim(Description))>0),
 Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED'))''')

# Exactly one typed FK makes the source a real referential relationship.
SOURCES = {
 'PurchaseInvoice':'PurchaseInvoiceID', 'PurchaseFreight':'FreightID', 'GoodsReceipt':'GoodsReceiptID',
 'StockTransfer':'TransferID', 'StockTransferReceipt':'TransferReceiptID', 'InventoryAdjustment':'AdjustmentID',
 'SalesInvoice':'SalesInvoiceID', 'SalesReturn':'SalesReturnID', 'PurchaseReturn':'PurchaseReturnID',
 'CustomerReceipt':'ReceiptID', 'SupplierPayment':'SupplierPaymentID', 'Expense':'ExpenseID', 'Payroll':'PayrollID',
 'SalaryPayment':'SalaryPaymentID', 'Delivery':'DeliveryID', 'DeliveryExpense':'DeliveryExpenseID',
 'FinancialTransfer':'TransferID', 'FixedAsset':'AssetID', 'AssetDepreciation':'DepreciationID', 'AssetDisposal':'DisposalID',
 'ExpensePayment':'ExpensePaymentID','ManualJournal':'ManualJournalID'
}
source_columns = ',\n'.join(f'{t}Ref INTEGER REFERENCES {t}({pk})' for t, pk in SOURCES.items())
one_source = '+'.join(f'({t}Ref IS NOT NULL)' for t in SOURCES)
table('PostingEvent', f'''EventID INTEGER PRIMARY KEY, SourceType TEXT NOT NULL, SourceID INTEGER NOT NULL,
 SourceEvent TEXT NOT NULL CHECK(SourceEvent IN ('POST','PAY')), EventDate TEXT NOT NULL,
 HasFinancialEffect INTEGER NOT NULL DEFAULT 1 CHECK(HasFinancialEffect IN (0,1)),
 Status TEXT NOT NULL DEFAULT 'PREPARING' CHECK(Status IN ('PREPARING','POSTED')),
 {source_columns}, CHECK({one_source}=1), UNIQUE(SourceType,SourceID,SourceEvent)''')
table('JournalEntry', '''JournalEntryID INTEGER PRIMARY KEY, FinancialYearID INTEGER NOT NULL REFERENCES FinancialYear,
 AccountingPeriodID INTEGER NOT NULL REFERENCES AccountingPeriod, EntryDate TEXT NOT NULL, EntryNumber TEXT NOT NULL UNIQUE,
 Description TEXT NOT NULL, Status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(Status IN ('DRAFT','POSTED')),
 SourceType TEXT NOT NULL, SourceID INTEGER NOT NULL, SourceEvent TEXT NOT NULL,
 EventID INTEGER NOT NULL UNIQUE REFERENCES PostingEvent, ReversesJournalEntryID INTEGER UNIQUE REFERENCES JournalEntry,
 UNIQUE(SourceType,SourceID,SourceEvent)''')
table('JournalEntryDetail', '''JournalEntryDetailID INTEGER PRIMARY KEY, JournalEntryID INTEGER NOT NULL REFERENCES JournalEntry,
 AccountID INTEGER NOT NULL REFERENCES ChartOfAccounts, Debit INTEGER NOT NULL DEFAULT 0 CHECK(Debit>=0),
 Credit INTEGER NOT NULL DEFAULT 0 CHECK(Credit>=0), CHECK((Debit>0 AND Credit=0) OR (Credit>0 AND Debit=0))''')
detail_refs={'GoodsReceiptDetail':'GoodsReceiptDetailID','SalesInvoiceDetail':'SalesInvoiceDetailID',
 'SalesReturnDetail':'SalesReturnDetailID','PurchaseReturnDetail':'PurchaseReturnDetailID',
 'StockTransferDetail':'TransferDetailID','StockTransferReceiptDetail':'TransferReceiptDetailID',
 'InventoryAdjustmentDetail':'AdjustmentDetailID'}
table('StockAllocation', f'''StockAllocationID INTEGER PRIMARY KEY, EventID INTEGER NOT NULL REFERENCES PostingEvent,
 BatchID INTEGER NOT NULL REFERENCES InventoryBatch, WarehouseID INTEGER NOT NULL REFERENCES Warehouse,
 Quantity INTEGER NOT NULL CHECK(Quantity<>0), CostAmount INTEGER NOT NULL,
 OriginalAllocationID INTEGER REFERENCES StockAllocation,
 {','.join(f'{t}Ref INTEGER REFERENCES {t}({pk})' for t,pk in detail_refs.items())},
 CHECK({'+'.join(f'({t}Ref IS NOT NULL)' for t in detail_refs)}=1),
 CHECK((Quantity>0 AND CostAmount>=0) OR (Quantity<0 AND CostAmount<=0))''')
table('InventoryMovement', '''InventoryMovementID INTEGER PRIMARY KEY, ProductID INTEGER NOT NULL REFERENCES Product,
 WarehouseID INTEGER NOT NULL REFERENCES Warehouse, BatchID INTEGER NOT NULL REFERENCES InventoryBatch,
 MovementType TEXT NOT NULL CHECK(MovementType IN ('IN','OUT')), Quantity INTEGER NOT NULL CHECK(Quantity<>0),
 CostAmount INTEGER NOT NULL, MovementDate TEXT NOT NULL, SourceType TEXT NOT NULL, SourceDetailID INTEGER NOT NULL,
 EventID INTEGER NOT NULL REFERENCES PostingEvent, StockAllocationID INTEGER NOT NULL UNIQUE REFERENCES StockAllocation,
 CHECK((MovementType='IN' AND Quantity>0 AND CostAmount>=0) OR (MovementType='OUT' AND Quantity<0 AND CostAmount<=0))''')
table('FinancialTransaction', '''TransactionID INTEGER PRIMARY KEY, FinancialAccountID INTEGER NOT NULL REFERENCES FinancialAccount,
 SourceType TEXT NOT NULL, SourceID INTEGER NOT NULL, SourceEvent TEXT NOT NULL,
 TransactionDate TEXT NOT NULL, TransactionType TEXT NOT NULL CHECK(TransactionType IN ('IN','OUT')),
 Amount INTEGER NOT NULL CHECK(Amount>0), Description TEXT NOT NULL, EventID INTEGER NOT NULL REFERENCES PostingEvent,
 UNIQUE(EventID,FinancialAccountID), UNIQUE(SourceType,SourceID,SourceEvent,FinancialAccountID)''')
table('AppUser', '''UserID INTEGER PRIMARY KEY, EmployeeID INTEGER NOT NULL UNIQUE REFERENCES Employee,
 Username TEXT NOT NULL COLLATE NOCASE UNIQUE, PasswordHash TEXT NOT NULL CHECK(length(PasswordHash)>=40 AND
 (PasswordHash GLOB 'scrypt$*' OR PasswordHash GLOB 'pbkdf2_sha256$*' OR PasswordHash GLOB '$argon2id$*' OR PasswordHash GLOB '$2b$*')),
 IsActive INTEGER NOT NULL DEFAULT 1 CHECK(IsActive IN (0,1)), CreatedAt TEXT NOT NULL''')
table('Role', 'RoleID INTEGER PRIMARY KEY, RoleName TEXT NOT NULL UNIQUE, Description TEXT')
table('UserRole', 'UserID INTEGER NOT NULL REFERENCES AppUser, RoleID INTEGER NOT NULL REFERENCES Role, PRIMARY KEY(UserID,RoleID)')
table('Permission', 'PermissionID INTEGER PRIMARY KEY, PermissionName TEXT NOT NULL, PermissionCode TEXT NOT NULL UNIQUE, Description TEXT')
table('RolePermission', 'RoleID INTEGER NOT NULL REFERENCES Role, PermissionID INTEGER NOT NULL REFERENCES Permission, PRIMARY KEY(RoleID,PermissionID)')
table('AuditLog', '''AuditLogID INTEGER PRIMARY KEY, UserID INTEGER REFERENCES AppUser, ActionType TEXT NOT NULL,
 EntityName TEXT NOT NULL, AffectedRecordID INTEGER NOT NULL, OldValues TEXT, NewValues TEXT, ActionAt TEXT NOT NULL''')


def build():
    sql = ['-- Generated by database/build_schema.py; do not hand edit.\n-- All money: integer minor units. All quantities: integer thousandths.\nPRAGMA foreign_keys=ON;\nBEGIN IMMEDIATE;']
    for name, cols in TABLES.items():
        sql.append(f'CREATE TABLE {name} (\n {cols}\n) STRICT;')
        # Index every foreign key, including optional source and source-detail FKs.
        import re
        for col in re.findall(r'(\w+) INTEGER(?: NOT NULL)?(?: UNIQUE)? REFERENCES', cols):
            sql.append(f'CREATE INDEX IX_{name}_{col} ON {name}({col});')
        for col in re.findall(r'(\w*(?:Date|At)) TEXT', cols):
            # Canonical date/time validation: strftime alone accepts invalid calendar days.
            if col.endswith('At') or col == 'MovementDate':
                condition = f"NEW.{col} IS NOT NULL AND (length(NEW.{col})<>20 OR strftime('%Y-%m-%dT%H:%M:%SZ',NEW.{col},'+0 seconds') IS NOT NEW.{col})"
            else:
                condition = f"NEW.{col} IS NOT NULL AND (length(NEW.{col})<>10 OR date(NEW.{col},'+0 days') IS NOT NEW.{col})"
            for op in ('INSERT','UPDATE'):
                sql.append(f"CREATE TRIGGER Date_{name}_{col}_{op} BEFORE {op} ON {name} WHEN {condition} BEGIN SELECT RAISE(ABORT,'invalid ISO date'); END;")

    def guard(name, timing, table_name, condition, message):
        sql.append(f"CREATE TRIGGER {name} {timing} ON {table_name} WHEN {condition} BEGIN SELECT RAISE(ABORT,'{message}'); END;")

    # Immutable effects and posted document snapshots.
    for name in ('InventoryMovement','StockAllocation','FinancialTransaction','AuditLog'):
        for op in ('UPDATE','DELETE'):
            guard(f'Immutable_{name}_{op}', f'BEFORE {op}', name, '1', 'immutable effect')
    for name in (*SOURCES, 'InventoryCount', 'JournalEntry', 'PostingEvent'):
        for op in ('UPDATE','DELETE'):
            guard(f'Posted_{name}_{op}',f'BEFORE {op}',name,"OLD.Status='POSTED'",'posted document is immutable')
        guard(f'Draft_{name}', 'BEFORE INSERT', name, "NEW.Status='POSTED'", 'insert draft then post')
    for child, parent, fk in (
        ('PurchaseInvoiceDetail','PurchaseInvoice','PurchaseInvoiceID'),('GoodsReceiptDetail','GoodsReceipt','GoodsReceiptID'),
        ('FreightAllocation','PurchaseFreight','FreightID'),('InventoryBatch','GoodsReceiptDetail','GoodsReceiptDetailID'),
        ('StockTransferDetail','StockTransfer','TransferID'),('StockTransferReceiptDetail','StockTransferReceipt','TransferReceiptID'),
        ('InventoryCountDetail','InventoryCount','InventoryCountID'),('InventoryAdjustmentDetail','InventoryAdjustment','AdjustmentID'),
        ('SalesInvoiceDetail','SalesInvoice','SalesInvoiceID'),('SalesReturnDetail','SalesReturn','SalesReturnID'),
        ('PurchaseReturnDetail','PurchaseReturn','PurchaseReturnID'),('ReceiptAllocation','CustomerReceipt','ReceiptID'),
        ('SupplierPaymentAllocation','SupplierPayment','SupplierPaymentID'),('PayrollDetail','Payroll','PayrollID'),
        ('JournalEntryDetail','JournalEntry','JournalEntryID')):
        if child=='InventoryBatch':
            query="SELECT g.Status FROM GoodsReceiptDetail d JOIN GoodsReceipt g USING(GoodsReceiptID) WHERE d.GoodsReceiptDetailID={alias}.GoodsReceiptDetailID"
        else:
            pk = 'FreightID' if parent=='PurchaseFreight' else fk
            query=f'SELECT Status FROM {parent} WHERE {pk}={{alias}}.{fk}'
        for op in ('INSERT','UPDATE','DELETE'):
            aliases = ('NEW','OLD') if op=='UPDATE' else (('OLD',) if op=='DELETE' else ('NEW',))
            cond=' OR '.join(f"({query.format(alias=a)})='POSTED'" for a in aliases)
            guard(f'Freeze_{child}_{op}',f'BEFORE {op}',child,cond,'posted parent lines are immutable')

    source_match=' OR '.join(f"(NEW.SourceType='{t}' AND NEW.SourceID=NEW.{t}Ref)" for t in SOURCES)
    for op in ('INSERT','UPDATE'):
        guard(f'Event_source_{op}',f'BEFORE {op}','PostingEvent',f'NOT COALESCE(({source_match}),0)','source FK mismatch')
    for name in ('JournalEntry','FinancialTransaction'):
        for op in ('INSERT','UPDATE'):
            guard(f'Source_{name}_{op}',f'BEFORE {op}',name,
                  "NOT EXISTS(SELECT 1 FROM PostingEvent e WHERE e.EventID=NEW.EventID AND e.Status='PREPARING' AND e.SourceType=NEW.SourceType AND e.SourceID=NEW.SourceID AND e.SourceEvent=NEW.SourceEvent)", 'event source mismatch or sealed')
    for name in ('StockAllocation','InventoryMovement'):
        guard(f'Open_{name}','BEFORE INSERT',name,"(SELECT Status FROM PostingEvent WHERE EventID=NEW.EventID)<>'PREPARING'",'event is sealed')
    guard('Journal_balance','BEFORE UPDATE OF Status','JournalEntry',
          "NEW.Status='POSTED' AND ((SELECT count(*) FROM JournalEntryDetail WHERE JournalEntryID=NEW.JournalEntryID)<2 OR (SELECT COALESCE(sum(Debit),0) FROM JournalEntryDetail WHERE JournalEntryID=NEW.JournalEntryID)<=0 OR (SELECT COALESCE(sum(Debit-Credit),0) FROM JournalEntryDetail WHERE JournalEntryID=NEW.JournalEntryID)<>0)", 'unbalanced journal')
    guard('Journal_period','BEFORE UPDATE OF Status','JournalEntry',
          "NEW.Status='POSTED' AND NOT EXISTS(SELECT 1 FROM AccountingPeriod p JOIN FinancialYear y USING(FinancialYearID) WHERE p.AccountingPeriodID=NEW.AccountingPeriodID AND y.FinancialYearID=NEW.FinancialYearID AND p.Status='OPEN' AND y.Status='OPEN' AND NEW.EntryDate BETWEEN p.StartDate AND p.EndDate AND NEW.EntryDate BETWEEN y.StartDate AND y.EndDate)", 'closed or mismatched period')
    guard('Journal_accounts','BEFORE UPDATE OF Status','JournalEntry',
          "NEW.Status='POSTED' AND EXISTS(SELECT 1 FROM JournalEntryDetail d JOIN ChartOfAccounts a USING(AccountID) WHERE d.JournalEntryID=NEW.JournalEntryID AND a.IsPostingAllowed<>1)", 'account does not allow posting')
    guard('Event_seal','BEFORE UPDATE OF Status','PostingEvent',
          "NEW.Status='POSTED' AND ((NEW.HasFinancialEffect=1 AND NOT EXISTS(SELECT 1 FROM JournalEntry j WHERE j.EventID=NEW.EventID AND j.Status='POSTED')) OR (NEW.HasFinancialEffect=0 AND EXISTS(SELECT 1 FROM JournalEntry j WHERE j.EventID=NEW.EventID)) OR EXISTS(SELECT 1 FROM StockAllocation a WHERE a.EventID=NEW.EventID AND NOT EXISTS(SELECT 1 FROM InventoryMovement m WHERE m.StockAllocationID=a.StockAllocationID)))", 'incomplete posting event')
    for t, pk in SOURCES.items():
        guard(f'Approval_{t}','BEFORE UPDATE OF Status',t,
              f"NEW.Status='POSTED' AND NOT EXISTS(SELECT 1 FROM PostingEvent e WHERE e.SourceType='{t}' AND e.SourceID=NEW.{pk} AND e.SourceEvent='POST' AND e.Status='POSTED')", 'post through accounting service')

    # Source detail -> header -> event checks, plus batch/product checks.
    detail_headers={'GoodsReceiptDetail':('GoodsReceipt','GoodsReceiptID'),
      'SalesInvoiceDetail':('SalesInvoice','SalesInvoiceID'),'SalesReturnDetail':('SalesReturn','SalesReturnID'),
      'PurchaseReturnDetail':('PurchaseReturn','PurchaseReturnID'),'StockTransferDetail':('StockTransfer','TransferID'),
      'StockTransferReceiptDetail':('StockTransferReceipt','TransferReceiptID'),
      'InventoryAdjustmentDetail':('InventoryAdjustment','AdjustmentID')}
    checks=[]
    for dt,(ht,hpk) in detail_headers.items():
        checks.append(f"(NEW.{dt}Ref IS NOT NULL AND EXISTS(SELECT 1 FROM {dt} d JOIN PostingEvent e ON e.SourceID=d.{hpk} AND e.SourceType='{ht}' WHERE d.{detail_refs[dt]}=NEW.{dt}Ref AND e.EventID=NEW.EventID))")
    guard('Allocation_source','BEFORE INSERT','StockAllocation','NOT ('+' OR '.join(checks)+')','allocation source mismatch')
    guard('Movement_allocation','BEFORE INSERT','InventoryMovement',
          "NOT EXISTS(SELECT 1 FROM StockAllocation a JOIN InventoryBatch b USING(BatchID) JOIN PostingEvent e USING(EventID) WHERE a.StockAllocationID=NEW.StockAllocationID AND a.EventID=NEW.EventID AND a.BatchID=NEW.BatchID AND a.WarehouseID=NEW.WarehouseID AND a.Quantity=NEW.Quantity AND a.CostAmount=NEW.CostAmount AND b.ProductID=NEW.ProductID AND e.SourceType=NEW.SourceType AND NEW.SourceDetailID=COALESCE(a.GoodsReceiptDetailRef,a.SalesInvoiceDetailRef,a.SalesReturnDetailRef,a.PurchaseReturnDetailRef,a.StockTransferDetailRef,a.StockTransferReceiptDetailRef,a.InventoryAdjustmentDetailRef))", 'movement allocation mismatch')
    guard('Movement_stock','BEFORE INSERT','InventoryMovement',
          "NEW.Quantity<0 AND NOT EXISTS(SELECT 1 FROM BatchStock WHERE WarehouseID=NEW.WarehouseID AND BatchID=NEW.BatchID AND CurrentQuantity>=-NEW.Quantity AND CostAmount>=-NEW.CostAmount)", 'insufficient batch stock')
    sql.append('''CREATE TRIGGER Apply_movement AFTER INSERT ON InventoryMovement BEGIN
      INSERT INTO BatchStock(WarehouseID,BatchID,CurrentQuantity,CostAmount)
      SELECT NEW.WarehouseID,NEW.BatchID,NEW.Quantity,NEW.CostAmount WHERE NEW.Quantity>0
      ON CONFLICT(WarehouseID,BatchID) DO UPDATE SET CurrentQuantity=CurrentQuantity+excluded.CurrentQuantity,CostAmount=CostAmount+excluded.CostAmount;
      UPDATE BatchStock SET CurrentQuantity=CurrentQuantity+NEW.Quantity,CostAmount=CostAmount+NEW.CostAmount
      WHERE WarehouseID=NEW.WarehouseID AND BatchID=NEW.BatchID AND NEW.Quantity<0;
      INSERT INTO InventoryBalance(WarehouseID,ProductID,CurrentQuantity)
      SELECT NEW.WarehouseID,NEW.ProductID,NEW.Quantity WHERE NEW.Quantity>0
      ON CONFLICT(WarehouseID,ProductID) DO UPDATE SET CurrentQuantity=CurrentQuantity+excluded.CurrentQuantity;
      UPDATE InventoryBalance SET CurrentQuantity=CurrentQuantity+NEW.Quantity
      WHERE WarehouseID=NEW.WarehouseID AND ProductID=NEW.ProductID AND NEW.Quantity<0;
    END;''')
    # Enforce parent ownership early, even while drafting.
    relations={
      'GoodsReceiptDetail': "(SELECT PurchaseInvoiceID FROM GoodsReceipt WHERE GoodsReceiptID=NEW.GoodsReceiptID) IS NOT (SELECT PurchaseInvoiceID FROM PurchaseInvoiceDetail WHERE PurchaseInvoiceDetailID=NEW.PurchaseInvoiceDetailID)",
      'FreightAllocation': "NOT EXISTS(SELECT 1 FROM PurchaseFreight f JOIN PurchaseInvoiceDetail d USING(PurchaseInvoiceID) WHERE f.FreightID=NEW.FreightID AND d.PurchaseInvoiceDetailID=NEW.PurchaseInvoiceDetailID AND f.Treatment='INVENTORY')",
      'InventoryBatch': "NOT EXISTS(SELECT 1 FROM GoodsReceiptDetail r JOIN PurchaseInvoiceDetail d USING(PurchaseInvoiceDetailID) WHERE r.GoodsReceiptDetailID=NEW.GoodsReceiptDetailID AND d.ProductID=NEW.ProductID)",
      'StockTransferReceiptDetail': "(SELECT TransferID FROM StockTransferReceipt WHERE TransferReceiptID=NEW.TransferReceiptID) IS NOT (SELECT TransferID FROM StockTransferDetail WHERE TransferDetailID=NEW.TransferDetailID)",
      'SalesReturnDetail': "(SELECT SalesInvoiceID FROM SalesReturn WHERE SalesReturnID=NEW.SalesReturnID) IS NOT (SELECT SalesInvoiceID FROM SalesInvoiceDetail WHERE SalesInvoiceDetailID=NEW.SalesInvoiceDetailID)",
      'PurchaseReturnDetail': "(SELECT PurchaseInvoiceID FROM PurchaseReturn WHERE PurchaseReturnID=NEW.PurchaseReturnID) IS NOT (SELECT PurchaseInvoiceID FROM PurchaseInvoiceDetail WHERE PurchaseInvoiceDetailID=NEW.PurchaseInvoiceDetailID)",
      'ReceiptAllocation': "NOT EXISTS(SELECT 1 FROM CustomerReceipt r JOIN SalesInvoice i USING(CustomerID) WHERE r.ReceiptID=NEW.ReceiptID AND i.SalesInvoiceID=NEW.SalesInvoiceID AND i.SaleType='CREDIT')",
      'SupplierPaymentAllocation': "NOT EXISTS(SELECT 1 FROM SupplierPayment p JOIN PurchaseInvoice i USING(SupplierID) WHERE p.SupplierPaymentID=NEW.SupplierPaymentID AND i.PurchaseInvoiceID=NEW.PurchaseInvoiceID)",
      'PayrollDetail': "(SELECT BranchID FROM Payroll WHERE PayrollID=NEW.PayrollID) IS NOT (SELECT BranchID FROM Employee WHERE EmployeeID=NEW.EmployeeID)",
      'InventoryAdjustmentDetail': "(SELECT InventoryCountID FROM InventoryAdjustment WHERE AdjustmentID=NEW.AdjustmentID) IS NOT (SELECT InventoryCountID FROM InventoryCountDetail WHERE InventoryCountDetailID=NEW.InventoryCountDetailID)"
    }
    for t, cond in relations.items():
        for op in ('INSERT','UPDATE'):
            guard(f'Ownership_{t}_{op}',f'BEFORE {op}',t,cond,'document ownership mismatch')
    for op in ('INSERT','UPDATE'):
        guard(f'Period_range_{op}',f'BEFORE {op}','AccountingPeriod',
              "NOT EXISTS(SELECT 1 FROM FinancialYear y WHERE y.FinancialYearID=NEW.FinancialYearID AND NEW.StartDate>=y.StartDate AND NEW.EndDate<=y.EndDate) OR EXISTS(SELECT 1 FROM AccountingPeriod p WHERE p.AccountingPeriodID<>NEW.AccountingPeriodID AND p.StartDate<=NEW.EndDate AND p.EndDate>=NEW.StartDate)", 'period overlap or year mismatch')
        guard(f'Year_range_{op}',f'BEFORE {op}','FinancialYear',
              'EXISTS(SELECT 1 FROM FinancialYear y WHERE y.FinancialYearID<>NEW.FinancialYearID AND y.StartDate<=NEW.EndDate AND y.EndDate>=NEW.StartDate)', 'financial years overlap')
    # Protect historical mappings; closing a period or disabling an account remains possible.
    for t, cols, cond in (
        ('FinancialYear','StartDate,EndDate', 'EXISTS(SELECT 1 FROM AccountingPeriod WHERE FinancialYearID=OLD.FinancialYearID)'),
        ('AccountingPeriod','StartDate,EndDate,FinancialYearID', 'EXISTS(SELECT 1 FROM JournalEntry WHERE AccountingPeriodID=OLD.AccountingPeriodID)'),
        ('FinancialAccount','PostingAccountID', 'EXISTS(SELECT 1 FROM FinancialTransaction WHERE FinancialAccountID=OLD.FinancialAccountID)'),
        ('SystemSetting','MoneyScale,QuantityScale,CurrencyName', 'EXISTS(SELECT 1 FROM PostingEvent)'),
        ('AccountingPolicy',','.join(c.split()[0] for c in TABLES['AccountingPolicy'].split(',')[1:]),'EXISTS(SELECT 1 FROM PostingEvent)')):
        guard(f'Historical_{t}',f'BEFORE UPDATE OF {cols}',t,cond,'historical configuration is immutable')
    for t in ('SystemSetting','AccountingPolicy'):
        guard(f'Keep_{t}','BEFORE DELETE',t,'EXISTS(SELECT 1 FROM PostingEvent)','historical configuration is immutable')
    guard('Historical_account_type','BEFORE UPDATE OF AccountType,ParentAccountID','ChartOfAccounts',
          "EXISTS(SELECT 1 FROM JournalEntryDetail d JOIN JournalEntry j USING(JournalEntryID) WHERE d.AccountID=OLD.AccountID AND j.Status='POSTED')", 'historical account classification is immutable')
    for op in ('INSERT','UPDATE'):
        guard(f'Account_cycle_{op}',f'BEFORE {op}','ChartOfAccounts',
              '''NEW.ParentAccountID IS NOT NULL AND EXISTS(WITH RECURSIVE ancestors(AccountID,ParentAccountID) AS (
                SELECT AccountID,ParentAccountID FROM ChartOfAccounts WHERE AccountID=NEW.ParentAccountID
                UNION SELECT a.AccountID,a.ParentAccountID FROM ChartOfAccounts a JOIN ancestors p ON a.AccountID=p.ParentAccountID)
                SELECT 1 FROM ancestors WHERE AccountID=NEW.AccountID)''','account hierarchy cycle')
    sql += [
        'CREATE INDEX IX_JournalEntry_Date_Status ON JournalEntry(EntryDate,Status);',
        'CREATE INDEX IX_PostingEvent_Source_Status ON PostingEvent(SourceType,SourceID,Status);',
        '''CREATE VIEW StockInTransit AS SELECT d.TransferDetailID,d.TransferID,d.ProductID,d.Quantity ShippedQuantity,
          d.Quantity-COALESCE((SELECT sum(r.ReceivedQuantity) FROM StockTransferReceiptDetail r
            JOIN StockTransferReceipt h USING(TransferReceiptID) WHERE r.TransferDetailID=d.TransferDetailID AND h.Status='POSTED'),0) RemainingQuantity
          FROM StockTransferDetail d JOIN StockTransfer t USING(TransferID) WHERE t.Status='POSTED';'''
    ]
    sql += ["INSERT INTO SchemaMigration VALUES(1,strftime('%Y-%m-%dT%H:%M:%SZ','now'));",'COMMIT;']
    return '\n\n'.join(sql)+'\n'


if __name__=='__main__':
    Path(__file__).with_name('migrations').mkdir(exist_ok=True)
    Path(__file__).with_name('migrations').joinpath('001_initial.sql').write_text(build(), encoding='utf-8')
