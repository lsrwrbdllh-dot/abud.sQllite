# المشتريات والاستلام والشحن

```mermaid
erDiagram
Supplier ||--o{ PurchaseInvoice : issues
Branch o|--o{ PurchaseInvoice : purchases_for
PurchaseInvoice ||--|{ PurchaseInvoiceDetail : includes
Product ||--o{ PurchaseInvoiceDetail : purchased
PurchaseInvoice ||--o{ GoodsReceipt : received_in
Warehouse ||--o{ GoodsReceipt : receives
GoodsReceipt ||--|{ GoodsReceiptDetail : contains
PurchaseInvoiceDetail ||--o{ GoodsReceiptDetail : fulfills
PurchaseInvoice ||--o{ PurchaseFreight : freight
PurchaseFreight ||--o{ FreightAllocation : allocated_to
PurchaseInvoiceDetail ||--o{ FreightAllocation : cost_added
PurchaseInvoice {
 int PurchaseInvoiceID PK
 int SupplierID FK
 int BranchID FK "optional"
 date InvoiceDate
}
PurchaseInvoiceDetail {
 int PurchaseInvoiceDetailID PK
 int PurchaseInvoiceID FK
 int ProductID FK
 decimal Quantity
 decimal UnitPrice
}
GoodsReceipt {
 int GoodsReceiptID PK
 int PurchaseInvoiceID FK
 int WarehouseID FK
 date ReceiptDate
}
GoodsReceiptDetail {
 int GoodsReceiptDetailID PK
 int GoodsReceiptID FK
 int PurchaseInvoiceDetailID FK
 decimal ReceivedQuantity
}
PurchaseFreight {
 int FreightID PK
 int PurchaseInvoiceID FK
 decimal Amount
 date FreightDate
 string Description
 string Treatment "inventory_or_expense"
}
FreightAllocation {
 int FreightAllocationID PK
 int FreightID FK
 int PurchaseInvoiceDetailID FK
 decimal AllocatedAmount
 string AllocationBasis "value_quantity_weight_manual"
}
```

**ضوابط:** في معالجة INVENTORY يجب أن يساوي مجموع التوزيع تكلفة الشحن، وأن تكون الأسطر ضمن فاتورة الشحن نفسها. في EXPENSE لا توجد أسطر توزيع. راجع [قواعد التنفيذ](../docs/implementation-rules.md).
