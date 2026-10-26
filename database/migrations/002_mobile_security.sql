-- Mobile access-control extension. The original accounting schema stays at version 1.
BEGIN IMMEDIATE;
CREATE TABLE MobileSecurity (
 SettingID INTEGER PRIMARY KEY CHECK(SettingID=1), Version INTEGER NOT NULL CHECK(Version=1),
 Configured INTEGER NOT NULL DEFAULT 0 CHECK(Configured IN (0,1))
) STRICT;
INSERT INTO MobileSecurity VALUES(1,1,0);
CREATE TABLE MobileUserPermission (
 UserID INTEGER NOT NULL REFERENCES AppUser, PermissionID INTEGER NOT NULL REFERENCES Permission,
 Allowed INTEGER NOT NULL CHECK(Allowed IN (0,1)), PRIMARY KEY(UserID,PermissionID)
) STRICT;
CREATE TABLE MobileUserCash (
 UserID INTEGER NOT NULL REFERENCES AppUser, FinancialAccountID INTEGER NOT NULL REFERENCES FinancialAccount,
 PRIMARY KEY(UserID,FinancialAccountID)
) STRICT;
CREATE TABLE MobileRecordOwner (
 EntityName TEXT NOT NULL, RecordID INTEGER NOT NULL, UserID INTEGER NOT NULL REFERENCES AppUser,
 PRIMARY KEY(EntityName,RecordID)
) STRICT;
CREATE INDEX IX_MobileRecordOwner_User ON MobileRecordOwner(UserID,EntityName,RecordID);
COMMIT;
