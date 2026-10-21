-- Fictional demo only. No real people, credentials or financial operations.
PRAGMA foreign_keys=ON;
BEGIN IMMEDIATE;
INSERT INTO SystemSetting VALUES(1,'DEMO',100,1000);
INSERT INTO Branch VALUES(1,'فرع تجريبي أ','مدينة افتراضية'),(2,'فرع تجريبي ب','مدينة افتراضية');
INSERT INTO Warehouse VALUES(1,'مستودع الفرع أ',1),(2,'مستودع الفرع ب',2),(3,'مستودع مركزي',NULL);
INSERT INTO Category VALUES(1,'أغذية تجريبية');
INSERT INTO Product VALUES(1,'منتج تجريبي أ','قطعة',1),(2,'منتج تجريبي ب','كيلوغرام',1);
INSERT INTO Supplier VALUES(1,'مورد افتراضي أ','DEMO-001'),(2,'مورد افتراضي ب','DEMO-002');
INSERT INTO SupplierProduct VALUES(1,1,1),(2,1,2),(3,2,1);
INSERT INTO Customer VALUES(1,'عميل افتراضي أ','DEMO-C01','عنوان افتراضي'),(2,'عميل افتراضي ب','DEMO-C02','عنوان افتراضي');
INSERT INTO ChartOfAccounts(AccountID,AccountCode,AccountName,AccountType,ParentAccountID,IsPostingAllowed) VALUES
 (1,'1000','المخزون','ASSET',NULL,1),
 (2,'1100','بضائع قيد الاستلام','ASSET',NULL,1),
 (3,'1200','ذمم العملاء والمقدمات','ASSET',NULL,1),
 (4,'2000','ذمم الموردين والمقدمات','LIABILITY',NULL,1),
 (5,'4000','المبيعات ورسوم التوصيل','REVENUE',NULL,1),
 (6,'5000','تكلفة البضاعة المباعة','EXPENSE',NULL,1),
 (7,'5100','مصروفات تشغيلية','EXPENSE',NULL,1),
 (8,'5200','مصروف الرواتب الصافية','EXPENSE',NULL,1),
 (9,'2100','رواتب مستحقة','LIABILITY',NULL,1),
 (10,'2200','مصروفات مستحقة','LIABILITY',NULL,1),
 (11,'1300','مخزون قيد النقل','ASSET',NULL,1),
 (12,'5300','فروق المخزون والمرتجعات','EXPENSE',NULL,1),
 (13,'5400','مصروف الإهلاك','EXPENSE',NULL,1),
 (14,'1400','مجمع الإهلاك','ASSET',NULL,1),
 (15,'4100','أرباح استبعاد الأصول','REVENUE',NULL,1),
 (16,'5500','خسائر استبعاد الأصول','EXPENSE',NULL,1),
 (17,'1500','الصندوق التجريبي','ASSET',NULL,1),
 (18,'1600','البنك التجريبي','ASSET',NULL,1),
 (19,'1700','الأصول الثابتة','ASSET',NULL,1),
 (20,'3000','رأس مال تجريبي','EQUITY',NULL,1),
 (21,'9000','حساب تجميعي غير قابل للترحيل','ASSET',NULL,0);
INSERT INTO FinancialAccountType VALUES(1,'CASH'),(2,'BANK');
INSERT INTO FinancialAccount VALUES(1,1,1,17,'الصندوق التجريبي'),(2,2,NULL,18,'البنك التجريبي');
INSERT INTO AccountingPolicy VALUES(1,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16);
INSERT INTO FinancialYear VALUES(1,'سنة تجريبية 2026','2026-01-01','2026-12-31','OPEN');
INSERT INTO AccountingPeriod VALUES
 (1,1,'يناير','2026-01-01','2026-01-31','OPEN'),(2,1,'فبراير','2026-02-01','2026-02-28','OPEN'),
 (3,1,'مارس','2026-03-01','2026-03-31','OPEN'),(4,1,'أبريل','2026-04-01','2026-04-30','OPEN'),
 (5,1,'مايو','2026-05-01','2026-05-31','OPEN'),(6,1,'يونيو','2026-06-01','2026-06-30','OPEN'),
 (7,1,'يوليو','2026-07-01','2026-07-31','OPEN'),(8,1,'أغسطس','2026-08-01','2026-08-31','OPEN'),
 (9,1,'سبتمبر','2026-09-01','2026-09-30','OPEN'),(10,1,'أكتوبر','2026-10-01','2026-10-31','OPEN'),
 (11,1,'نوفمبر','2026-11-01','2026-11-30','OPEN'),(12,1,'ديسمبر','2026-12-01','2026-12-31','OPEN');
INSERT INTO ExpenseCategory VALUES(1,'مصروف تجريبي');
INSERT INTO Employee VALUES(1,1,'موظف افتراضي أ','وظيفة تجريبية','2026-01-01'),(2,2,'موظف افتراضي ب','وظيفة تجريبية','2026-01-01');
INSERT INTO Role VALUES(1,'reviewer','دور تجريبي؛ المصادقة مسؤولية التطبيق');
INSERT INTO Permission VALUES(1,'مراجعة','ACCOUNTING_REVIEW','صلاحية تجريبية');
INSERT INTO RolePermission VALUES(1,1);
-- Intentionally no default login or shared demo password.
COMMIT;
