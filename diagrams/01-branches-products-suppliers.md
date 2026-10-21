# الفروع والمنتجات والموردون

```mermaid
erDiagram
Branch ||--o{ Warehouse : contains
Category ||--o{ Product : classifies
Supplier ||--o{ SupplierProduct : supplies
Product ||--o{ SupplierProduct : sourced_from
Branch {
 int BranchID PK
 string Name
 string City
}
Warehouse {
 int WarehouseID PK
 string Name
 int BranchID FK "nullable for central warehouse"
}
Category {
 int CategoryID PK
 string Name
}
Product {
 int ProductID PK
 string Name
 string Unit
 int CategoryID FK
}
Supplier {
 int SupplierID PK
 string Name
 string Phone
}
SupplierProduct {
 int SupplierProductID PK
 int SupplierID FK
 int ProductID FK
}
```
