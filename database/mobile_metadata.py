"""Arabic presentation metadata; the authoritative fields remain SQLite PRAGMA."""
TABLE_LABELS = dict(line.split('|', 1) for line in '''SchemaMigration|إصدارات القاعدة
SystemSetting|إعدادات العملة والدقة
Branch|الفروع
Warehouse|المستودعات
Category|تصنيفات المنتجات
Product|المنتجات
Supplier|الموردون
SupplierProduct|منتجات الموردين
Customer|العملاء
ChartOfAccounts|دليل الحسابات
FinancialAccountType|أنواع الحسابات المالية
FinancialAccount|الصناديق والبنوك
AccountingPolicy|السياسة المحاسبية
FinancialYear|السنوات المالية
AccountingPeriod|الفترات المحاسبية
PurchaseInvoice|فواتير المشتريات
PurchaseInvoiceDetail|أصناف المشتريات
GoodsReceipt|استلام المشتريات
GoodsReceiptDetail|أصناف الاستلام
PurchaseFreight|شحن المشتريات
FreightAllocation|توزيع تكلفة الشحن
InventoryBatch|دفعات المنتجات والصلاحية
InventoryBalance|أرصدة المنتجات
BatchStock|أرصدة الدفعات
StockTransfer|تحويل المخزون
StockTransferDetail|أصناف التحويل
StockTransferReceipt|استلام التحويل
StockTransferReceiptDetail|أصناف استلام التحويل
InventoryCount|محاضر الجرد
InventoryCountDetail|أصناف الجرد
InventoryAdjustment|تسويات الجرد
InventoryAdjustmentDetail|فروق الجرد
SalesInvoice|فواتير المبيعات
SalesInvoiceDetail|أصناف المبيعات
CustomerReceipt|سندات قبض العملاء
ReceiptAllocation|توزيع القبض على الفواتير
SupplierPayment|سندات سداد الموردين
SupplierPaymentAllocation|توزيع السداد على المشتريات
SalesReturn|مرتجعات المبيعات
SalesReturnDetail|أصناف مرتجع البيع
PurchaseReturn|مرتجعات المشتريات
PurchaseReturnDetail|أصناف مرتجع الشراء
ExpenseCategory|تصنيفات المصروفات
Expense|المصروفات
Employee|الموظفون
Payroll|مسيرات الرواتب
PayrollDetail|تفاصيل الرواتب
SalaryPayment|سداد الرواتب
Delivery|التوصيل
DeliveryExpense|مصروفات التوصيل
FinancialTransfer|التحويل بين الصناديق والبنوك
FixedAsset|الأصول الثابتة
AssetDepreciation|إهلاك الأصول
AssetDisposal|استبعاد الأصول
ExpensePayment|سداد المصروفات المستحقة
ManualJournal|القيود اليدوية
PostingEvent|أحداث الاعتماد
JournalEntry|القيود المحاسبية
JournalEntryDetail|أسطر القيود
StockAllocation|تخصيص دفعات المخزون
InventoryMovement|حركات المخزون
FinancialTransaction|الحركات المالية
AppUser|المستخدمون
Role|الأدوار
UserRole|أدوار المستخدمين
Permission|الصلاحيات
RolePermission|صلاحيات الأدوار
AuditLog|سجل التدقيق'''.splitlines())

GROUPS = {
 'البيع والعملاء': 'Customer SalesInvoice SalesInvoiceDetail CustomerReceipt ReceiptAllocation SalesReturn SalesReturnDetail Delivery DeliveryExpense',
 'الشراء والموردون': 'Supplier SupplierProduct PurchaseInvoice PurchaseInvoiceDetail PurchaseFreight FreightAllocation GoodsReceipt GoodsReceiptDetail PurchaseReturn PurchaseReturnDetail SupplierPayment SupplierPaymentAllocation',
 'المخزون والفروع': 'Branch Warehouse Category Product InventoryBatch InventoryBalance BatchStock StockTransfer StockTransferDetail StockTransferReceipt StockTransferReceiptDetail InventoryCount InventoryCountDetail InventoryAdjustment InventoryAdjustmentDetail InventoryMovement StockAllocation',
 'الأموال والمحاسبة': 'FinancialAccountType FinancialAccount FinancialTransfer FinancialTransaction ChartOfAccounts ManualJournal JournalEntry JournalEntryDetail PostingEvent AccountingPolicy SystemSetting FinancialYear AccountingPeriod',
 'المصروفات والرواتب': 'ExpenseCategory Expense ExpensePayment Employee Payroll PayrollDetail SalaryPayment',
 'الأصول الثابتة': 'FixedAsset AssetDepreciation AssetDisposal',
 'المستخدمون والسجلات': 'AppUser Role UserRole Permission RolePermission AuditLog SchemaMigration',
}
LABELS = dict(line.split('|', 1) for line in '''Name|الاسم
City|المدينة
Unit|الوحدة
Phone|الهاتف
Address|العنوان
AccountCode|رمز الحساب
AccountName|اسم الحساب
AccountType|نوع الحساب
IsPostingAllowed|يسمح بالترحيل
TypeName|اسم النوع
StartDate|تاريخ البداية
EndDate|تاريخ النهاية
Status|الحالة
InvoiceDate|تاريخ الفاتورة
Quantity|الكمية
UnitPrice|سعر الوحدة
ReceiptDate|تاريخ الاستلام أو القبض
ReceivedQuantity|الكمية المستلمة
Amount|المبلغ
FreightDate|تاريخ الشحن
Description|الوصف
Treatment|معالجة الشحن
ExpenseEligible|مؤهل للمعالجة كمصروف
EligibilityReason|سبب أهلية المصروف
AllocatedAmount|المبلغ الموزع
AllocationBasis|أساس التوزيع
ManufacturerLot|رقم تشغيلة المصنع
ProductionDate|تاريخ الإنتاج
ExpiryDate|تاريخ الصلاحية
UnitCost|تكلفة الوحدة
TotalCost|إجمالي التكلفة
CurrentQuantity|الكمية الحالية
CostAmount|قيمة التكلفة
TransferDate|تاريخ التحويل
Notes|الملاحظات
CountDate|تاريخ الجرد
SystemQuantity|الكمية المسجلة
ActualQuantity|الكمية الفعلية
AdjustmentDate|تاريخ التسوية
Reason|السبب
QuantityDifference|فرق الكمية
SaleType|نوع البيع
PaymentMethod|طريقة الدفع
ReturnDate|تاريخ المرتجع
CategoryName|اسم التصنيف
ExpenseDate|تاريخ المصروف
PaidDate|تاريخ السداد
EmployeeName|اسم الموظف
JobTitle|المسمى الوظيفي
HireDate|تاريخ التوظيف
PayrollMonth|شهر الراتب
PayrollYear|سنة الراتب
CreatedDate|تاريخ الإنشاء
BasicSalary|الراتب الأساسي
Allowances|البدلات
Deductions|الاستقطاعات
NetSalary|صافي الراتب
PaymentDate|تاريخ السداد
DeliveryAddress|عنوان التوصيل
ExpectedDate|التاريخ المتوقع
ActualDate|التاريخ الفعلي
DeliveryFee|رسوم التوصيل
ExpenseType|نوع المصروف
AssetName|اسم الأصل
PurchaseDate|تاريخ الشراء
Cost|التكلفة
UsefulLifeMonths|العمر الإنتاجي بالأشهر
SalvageValue|القيمة التخريدية
DepreciationDate|تاريخ الإهلاك
DisposalDate|تاريخ الاستبعاد
SaleProceeds|متحصلات البيع
EntryDate|تاريخ القيد
SourceType|نوع المصدر
SourceID|رقم المصدر
SourceEvent|حدث المصدر
EventDate|تاريخ الحدث
HasFinancialEffect|له أثر مالي
EntryNumber|رقم القيد
Debit|مدين
Credit|دائن
MovementType|نوع الحركة
MovementDate|تاريخ حركة المخزون
SourceDetailID|رقم سطر المصدر
TransactionDate|تاريخ الحركة المالية
TransactionType|اتجاه الحركة
Username|اسم المستخدم
PasswordHash|كلمة المرور المحفوظة
IsActive|نشط
CreatedAt|وقت الإنشاء
RoleName|اسم الدور
PermissionName|اسم الصلاحية
PermissionCode|رمز الصلاحية
ActionType|الإجراء
EntityName|المستند
AffectedRecordID|رقم السجل
OldValues|البيانات السابقة
NewValues|البيانات الجديدة
ActionAt|وقت الإجراء
Version|الإصدار
AppliedAt|تاريخ تطبيق الإصدار
CurrencyName|اسم العملة
MoneyScale|مقياس المبلغ
QuantityScale|مقياس الكمية'''.splitlines())
MONEY = set('UnitPrice Amount AllocatedAmount UnitCost TotalCost CostAmount BasicSalary Allowances Deductions NetSalary DeliveryFee Cost SalvageValue SaleProceeds Debit Credit'.split())
QUANTITIES = set('Quantity ReceivedQuantity CurrentQuantity SystemQuantity ActualQuantity QuantityDifference'.split())
AUTO = {
 'SystemSetting': {'MoneyScale','QuantityScale'},
 'InventoryBatch': {'UnitCost','TotalCost'},
 'AssetDepreciation': {'Amount','JournalEntryID'},
 'AssetDisposal': {'JournalEntryID'},
 'InventoryCountDetail': {'SystemQuantity'},
 'InventoryAdjustmentDetail': {'QuantityDifference'},
 'PayrollDetail': {'NetSalary'},
 'AppUser': {'CreatedAt'},
}
ENUM_LABELS = {'DRAFT':'مسودة','POSTED':'معتمد','OPEN':'مفتوح','CLOSED':'مغلق',
 'CASH':'نقدي','CREDIT':'آجل','BANK':'بنك','CARD':'بطاقة','IN':'إضافة','OUT':'صرف',
 'INVENTORY':'تحميل على المخزون','EXPENSE':'مصروف','VALUE':'القيمة','QUANTITY':'الكمية',
 'WEIGHT':'الوزن','MANUAL':'يدوي','ASSET':'أصول','LIABILITY':'التزامات',
 'EQUITY':'حقوق ملكية','REVENUE':'إيرادات','POST':'اعتماد','PAY':'سداد'}

def field_label(name, foreign=None):
    if name in LABELS:
        return LABELS[name]
    if foreign:
        prefix = 'من: ' if name.startswith('From') else 'إلى: ' if name.startswith('To') else ''
        return prefix + TABLE_LABELS[foreign]
    if name.endswith('ID'):
        return 'رقم السجل'
    return name
