-- ========== PHARMACY MANAGEMENT SYSTEM ==========

CREATE DATABASE PharmacyDB;
GO
USE PharmacyDB;
GO

-- =============     TABLES     ===============

/* -------------------------
   USERS TABLE
---------------------------*/
CREATE TABLE Users (
   Username        VARCHAR(50) PRIMARY KEY,
   FullName        VARCHAR(100),
   PasswordHash    VARCHAR(255),
   Role            VARCHAR(20),
   Active          BIT DEFAULT 1,
   Email           VARCHAR(100),
   Phone           VARCHAR(20)
);
GO
-- Seed admin user for initial login (username: admin, password: admin123)
INSERT INTO Users (Username, FullName, PasswordHash, Role, Active, Email, Phone) VALUES
('admin', 'Administrator', 'admin123', 'admin', 1, 'admin@example.com', '123456789');
GO
/* -------------------------
   SUPPLIERS TABLE
---------------------------*/
CREATE TABLE Suppliers (
   SupplierID      INT IDENTITY(1,1) PRIMARY KEY,
   Name            VARCHAR(100),
   Company         VARCHAR(100),
   Phone           VARCHAR(20),
   Email           VARCHAR(100),
   Active          BIT DEFAULT 1,
   CreatedDate     DATETIME DEFAULT GETDATE()
);
GO
/* -------------------------
   CUSTOMERS TABLE
---------------------------*/
CREATE TABLE Customers (
   CustomerID      INT IDENTITY(1,1) PRIMARY KEY,
   Name            VARCHAR(100),
   Phone           VARCHAR(20) NOT NULL UNIQUE,
   Email           VARCHAR(100) NOT NULL UNIQUE,
   CreatedDate     DATETIME DEFAULT GETDATE(),
   TotalPurchases  DECIMAL(10,2) DEFAULT 0
);
GO
/* -------------------------
   MEDICINES TABLE
---------------------------*/
CREATE TABLE Medicines (
   MedicineID      INT IDENTITY(1,1) PRIMARY KEY,
   Name            VARCHAR(100) NOT NULL UNIQUE,
   Category        VARCHAR(50),
   Quantity        INT DEFAULT 0,
   Price           DECIMAL(10,2),
   MinimumStock    INT DEFAULT 10,
   Status          VARCHAR(20),
   CreatedDate     DATETIME DEFAULT GETDATE(),
   SupplierID      INT NULL,

   FOREIGN KEY (SupplierID) REFERENCES Suppliers(SupplierID)
);
GO
/* -------------------------
   SALES TABLE (HEADER)
---------------------------*/
CREATE TABLE Sales (
   SaleID          INT IDENTITY(1,1) PRIMARY KEY,
   CustomerID      INT NULL,
   Subtotal        DECIMAL(10,2),
   Tax             DECIMAL(10,2),
   Total           DECIMAL(10,2),
   Timestamp       DATETIME DEFAULT GETDATE(),
   UserName        VARCHAR(50),

   FOREIGN KEY (CustomerID) REFERENCES Customers(CustomerID),
   FOREIGN KEY (UserName) REFERENCES Users(Username)
);
GO
/* -------------------------
   SALE ITEMS TABLE (DETAIL)
---------------------------*/
CREATE TABLE SaleItems (
   SaleItemID      INT IDENTITY PRIMARY KEY,
   SaleID          INT,
   MedicineID      INT,
   Quantity        INT,
   Price           DECIMAL(10,2),

   FOREIGN KEY (SaleID) REFERENCES Sales(SaleID),
   FOREIGN KEY (MedicineID) REFERENCES Medicines(MedicineID)
);
GO
/* -------------------------
   RETURNS TABLE
---------------------------*/
CREATE TABLE Returns (
   ReturnID          INT IDENTITY(1,1) PRIMARY KEY,
   MedicineID        INT,
   Quantity          INT,
   UnitPrice         DECIMAL(10,2),
   Amount            DECIMAL(10,2),
   SaleID            INT,
   CustomerID        INT,
   Reason            VARCHAR(255),
   Timestamp         DATETIME DEFAULT GETDATE(),
   UserName          VARCHAR(50),

   FOREIGN KEY (MedicineID) REFERENCES Medicines(MedicineID),
   FOREIGN KEY (SaleID) REFERENCES Sales(SaleID),
   FOREIGN KEY (CustomerID) REFERENCES Customers(CustomerID),
   FOREIGN KEY (UserName) REFERENCES Users(Username)
);
GO
/* -------------------------
   STOCK ADJUSTMENTS TABLE
---------------------------*/
CREATE TABLE StockAdjustments (
   AdjustmentID    INT IDENTITY(1,1) PRIMARY KEY,
   MedicineID      INT,
   OldQty          INT,
   NewQty          INT,
   ChangeQty       INT,
   SupplierID      INT,
   Reason          VARCHAR(255),
   UserName        VARCHAR(50),
   Timestamp       DATETIME DEFAULT GETDATE(),

   FOREIGN KEY (MedicineID) REFERENCES Medicines(MedicineID),
   FOREIGN KEY (SupplierID) REFERENCES Suppliers(SupplierID),
   FOREIGN KEY (UserName) REFERENCES Users(Username)
);
GO
/* -------------------------
   SETTINGS TABLE
---------------------------*/
CREATE TABLE Settings (
   pharmacy_name     VARCHAR(100) DEFAULT 'My Pharmacy',
   address           VARCHAR(255) DEFAULT '123 Main St',
   phone             VARCHAR(20) DEFAULT '555-0123',
   tax_rate          DECIMAL(5,2) DEFAULT 8.5,
   currency          VARCHAR(10) DEFAULT 'USD',
   start_maximized   BIT DEFAULT 1
);
GO
-- Insert the default application settings.
INSERT INTO Settings DEFAULT VALUES;
GO
/* -------------------------
   ACTIVITY LOG TABLE
---------------------------*/
CREATE TABLE ActivityLog (
   LogID       INT IDENTITY PRIMARY KEY,
   UserName    VARCHAR(50),
   Action      VARCHAR(200),
   LogTime     DATETIME DEFAULT GETDATE()
);
GO


--   =========  STORED PROCEDURES  ==============

/* -----------------------------
   ADD MEDICINE
------------------------------*/
CREATE PROCEDURE AddMedicine  
   @Name VARCHAR(100),  
   @Category VARCHAR(50),  
   @Quantity INT,  
   @Price DECIMAL(10,2),  
   @MinimumStock INT,  
   @SupplierID INT = NULL,
   @UserName VARCHAR(50)
AS
BEGIN
   SET NOCOUNT ON;
   
   BEGIN TRANSACTION;
    BEGIN TRY

      -- Compute status server-side (ignore provided @Status to ensure DB is authoritative)
      DECLARE @ComputedStatus VARCHAR(20);
      IF @Quantity <= 0
         SET @ComputedStatus = 'out of stock';
      ELSE IF @MinimumStock > 0 AND @Quantity < @MinimumStock
         SET @ComputedStatus = 'low stock';
      ELSE
         SET @ComputedStatus = 'ok';

      -- Insert (include SupplierID if provided)
      INSERT INTO Medicines (Name, Category, Quantity, Price, MinimumStock, Status, SupplierID)
      VALUES (@Name, @Category, @Quantity, @Price, @MinimumStock, @ComputedStatus, @SupplierID);

        -- Identity
        DECLARE @MedicineID INT;
        SET @MedicineID = SCOPE_IDENTITY();

        -- Stock adjustment
      EXEC AddStockAdjustment
         @MedicineID = @MedicineID,
         @OldQty = 0,
         @NewQty = @Quantity,
         @ChangeQty = @Quantity,
         @SupplierID = @SupplierID,
         @Reason = 'Initial stock on medicine addition',
         @UserName = @UserName;

        -- Activity Log
        DECLARE @ActionText VARCHAR(300);
        SET @ActionText =
              'Added new medicine: ' + @Name
            + ' (ID: ' + CAST(@MedicineID AS VARCHAR(10)) + ')'
            + ' with initial stock of ' + CAST(@Quantity AS VARCHAR(10));
        EXEC AddActivityLog
            @UserName = @UserName,
            @Action = @ActionText

        COMMIT TRANSACTION;

        -- Return the ID
        SELECT @MedicineID AS MedicineID;
    END TRY
   BEGIN CATCH
      ROLLBACK TRANSACTION;
      THROW;
   END CATCH
END;
GO
 
/* -----------------------------
   TOGGLE SUPPLIER STATUS
   Flips the Suppliers.Active bit and returns the new value
------------------------------*/
CREATE PROCEDURE ToggleSupplierStatus
 @SupplierID INT,
 @UserName VARCHAR(50)
AS
BEGIN
   SET NOCOUNT ON;
   BEGIN TRANSACTION;
      BEGIN TRY

      UPDATE Suppliers
      SET Active = CASE WHEN Active = 1 THEN 0 ELSE 1 END
      WHERE SupplierID = @SupplierID;

      -- Activity Log (optional: record who toggled)
      DECLARE @ActionText VARCHAR(300);
      SET @ActionText = 'Toggled active status for supplier ID: ' + CAST(@SupplierID AS VARCHAR(20));
      Exec AddActivityLog
          @UserName = @UserName,
          @Action = @ActionText;

      -- return the new active value
      SELECT Active FROM Suppliers WHERE SupplierID = @SupplierID;

      COMMIT TRANSACTION;
   END TRY
   BEGIN CATCH
      ROLLBACK TRANSACTION;
      THROW;
   END CATCH
END;
GO
/* -----------------------------
   UPDATE MEDICINE
------------------------------*/
CREATE PROCEDURE UpdateMedicine
 @MedicineID INT,
 @Name VARCHAR(100),
 @Category VARCHAR(50),
 @Quantity INT,
 @Price DECIMAL(10,2),
 @MinimumStock INT,
 @SupplierID INT = NULL,
 @UserName VARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
 BEGIN TRANSACTION;
  BEGIN TRY
   
   DECLARE @OldQty INT;
   SELECT @OldQty = Quantity FROM Medicines WHERE MedicineID = @MedicineID;
   
   -- Compute new status based on quantity and minimum stock
   DECLARE @NewStatus VARCHAR(20);
   IF @Quantity <= 0
      SET @NewStatus = 'out of stock';
   ELSE IF @MinimumStock > 0 AND @Quantity < @MinimumStock
      SET @NewStatus = 'low stock';
   ELSE
      SET @NewStatus = 'ok';

   -- Update the medicine details (status computed server-side)
   UPDATE Medicines
   SET Name=@Name,
      Category=@Category,
      Quantity=@Quantity,
      Price=@Price,
      MinimumStock=@MinimumStock,
      Status=@NewStatus,
      SupplierID=@SupplierID
   WHERE MedicineID=@MedicineID;
   
   -- Add stock adjustment if quantity changed
   IF @OldQty <> @Quantity
   BEGIN
      DECLARE @ChangeQty INT;
      SET @ChangeQty = @Quantity - @OldQty;
        EXEC AddStockAdjustment
           @MedicineID = @MedicineID,
           @OldQty = @OldQty,
           @NewQty = @Quantity,
           @ChangeQty = @ChangeQty,
           @SupplierID = @SupplierID,
           @Reason = 'Stock adjustment on medicine update',
           @UserName = @UserName;
   END
   
   -- Activity Log
   DECLARE @ActionText VARCHAR(300);
   SET @ActionText =
         'Updated medicine: ' + @Name
       + ' (ID: ' + CAST(@MedicineID AS VARCHAR(10)) + ')';
   EXEC AddActivityLog 
       @UserName = @UserName,
       @Action = @ActionText;
   COMMIT TRANSACTION;
 END TRY
 BEGIN CATCH
    ROLLBACK TRANSACTION;
    THROW;
 END CATCH
END;
GO

/* -----------------------------
   DELETE MEDICINE CASCADE
------------------------------*/
CREATE PROCEDURE DeleteMedicineCascade
 @MedicineID INT,
 @UserName VARCHAR(50)
AS
BEGIN
   SET NOCOUNT ON;
   
   BEGIN TRANSACTION;
      BEGIN TRY

      -- Delete stock adjustments first (history)
      DELETE FROM StockAdjustments WHERE MedicineID = @MedicineID;

      -- Delete returns linked to this medicine
      DELETE FROM Returns WHERE MedicineID = @MedicineID;

      -- Delete sale items referencing this medicine
      DELETE FROM SaleItems WHERE MedicineID = @MedicineID;

      -- Finally delete the medicine record
      DELETE FROM Medicines WHERE MedicineID = @MedicineID;
      -- Activity Log
      DECLARE @ActionText VARCHAR(300);
      SET @ActionText = 'Deleted medicine with ID: ' + CAST(@MedicineID AS VARCHAR(10));
      Exec AddActivityLog 
          @UserName = @UserName,
          @Action = @ActionText;

      COMMIT TRANSACTION;
   END TRY
   BEGIN CATCH
      ROLLBACK TRANSACTION;
      THROW;
   END CATCH
END;
GO

/* -----------------------------
   CREATE SALE (HEADER)
------------------------------*/
CREATE PROCEDURE CreateSale
 @CustomerID INT,
 @Subtotal DECIMAL(10,2),
 @Tax DECIMAL(10,2),
 @Total DECIMAL(10,2),
 @UserName VARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
 BEGIN TRANSACTION;
  BEGIN TRY

    INSERT INTO Sales (CustomerID, Subtotal, Tax, Total, UserName)
    VALUES (@CustomerID, @Subtotal, @Tax, @Total, @UserName);

    -- return the generated identity value
   SELECT SCOPE_IDENTITY() AS SaleID;

    COMMIT TRANSACTION;
 END TRY
 BEGIN CATCH
    ROLLBACK TRANSACTION;
    THROW;
 END CATCH
END;
GO

/* -----------------------------
   ADD SALE ITEM
------------------------------*/
CREATE PROCEDURE AddSaleItem
 @SaleID INT,
 @MedicineID INT,
 @Quantity INT,
 @Price DECIMAL(10,2),
 @UserName VARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;
 BEGIN TRANSACTION;
  BEGIN TRY


    -- Read current quantity
    DECLARE @OldQty INT;
    SELECT @OldQty = Quantity FROM Medicines WHERE MedicineID = @MedicineID;
    IF @OldQty IS NULL
    BEGIN
       ROLLBACK TRANSACTION;
       THROW 51001, 'Medicine not found.', 1;
    END
    -- Ensure requested quantity does not exceed available stock
    IF @Quantity > @OldQty
    BEGIN
       ROLLBACK TRANSACTION;
       THROW 51000, 'Insufficient stock for the requested medicine.', 1;
    END

    DECLARE @NewQty INT = @OldQty - @Quantity;

    -- Insert sale item
    INSERT INTO SaleItems (SaleID, MedicineID, Quantity, Price)
    VALUES (@SaleID, @MedicineID, @Quantity, @Price);

    -- Record stock adjustment using centralized proc (it will update Medicines.Quantity)
    DECLARE @ChangeQty INT = @NewQty - @OldQty; -- negative value
    DECLARE @Reason VARCHAR(255) = 'Sale: ' + CAST(@SaleID AS VARCHAR(20));

    EXEC AddStockAdjustment
        @MedicineID = @MedicineID,
        @OldQty = @OldQty,
        @NewQty = @NewQty,
        @ChangeQty = @ChangeQty,
        @SupplierID = NULL,
        @Reason = @Reason,
        @UserName = @UserName;

    COMMIT TRANSACTION;
 END TRY
 BEGIN CATCH
    ROLLBACK TRANSACTION;
    THROW;
 END CATCH
END;
GO

/* -----------------------------
   CUSTOMER MANAGEMENT
------------------------------*/
CREATE PROCEDURE AddCustomer
 @Name VARCHAR(100),
 @Phone VARCHAR(20),
 @Email VARCHAR(100),
 @UserName VARCHAR(50)
AS
BEGIN
   SET NOCOUNT ON;
   -- Server-side validation: Phone and Email must be non-NULL and non-empty
   IF @Phone IS NULL OR TRIM(@Phone) = '' OR @Email IS NULL OR TRIM(@Email) = ''
   BEGIN
      THROW 51006, 'Phone and Email are required and cannot be empty.', 1;
   END
   BEGIN TRANSACTION;
   BEGIN TRY  
      INSERT INTO Customers (Name, Phone, Email)
      VALUES (@Name, @Phone, @Email);
      --Activity Log 
      DECLARE @ActionText VARCHAR(300);
      SET @ActionText = 'Added new customer: ' + @Name;
      Exec AddActivityLog 
          @UserName = @UserName,
          @Action = @ActionText;


      -- return generated CustomerID
      SELECT SCOPE_IDENTITY() AS CustomerID;

      COMMIT TRANSACTION;
   END TRY
   BEGIN CATCH
      ROLLBACK TRANSACTION;
      THROW;
   END CATCH
END;
GO

CREATE PROCEDURE UpdateCustomer
 @CustomerID INT,
 @Name VARCHAR(100),
 @Phone VARCHAR(20),
 @Email VARCHAR(100),
 @UserName VARCHAR(50)
AS
BEGIN
   SET NOCOUNT ON;
   UPDATE Customers
   SET Name = @Name,
      Phone = @Phone,
      Email = @Email
   WHERE CustomerID = @CustomerID;
   --Activity Log
   DECLARE @ActionText VARCHAR(300);
   SET @ActionText = 'Updated customer: ' + @Name + ' (ID: ' + CAST(@CustomerID AS VARCHAR(10)) + ')';
   Exec AddActivityLog 
       @UserName = @UserName,
       @Action = @ActionText;
END;
GO

CREATE PROCEDURE DeleteCustomer
 @CustomerID INT,
 @UserName VARCHAR(50)
AS
BEGIN
   SET NOCOUNT ON;
BEGIN TRANSACTION;
  BEGIN TRY
    

    -- Null out references to this customer in other tables so deletes succeed
    UPDATE Sales SET CustomerID = NULL WHERE CustomerID = @CustomerID;
    UPDATE Returns SET CustomerID = NULL WHERE CustomerID = @CustomerID;

    -- Delete the customer record
    DELETE FROM Customers WHERE CustomerID = @CustomerID;

    -- Activity Log
    DECLARE @ActionText VARCHAR(300);
    SET @ActionText = 'Deleted customer with ID: ' + CAST(@CustomerID AS VARCHAR(10));
    Exec AddActivityLog 
        @UserName = @UserName,
        @Action = @ActionText;

    COMMIT TRANSACTION;
 END TRY
 BEGIN CATCH
    ROLLBACK TRANSACTION;
    THROW;
 END CATCH
END;
GO

/* -----------------------------
   ADD RETURN
------------------------------*/
CREATE PROCEDURE AddReturn
 @MedicineID INT,
 @Quantity INT,
 @UnitPrice DECIMAL(10,2),
 @Amount DECIMAL(10,2),
 @SaleID INT,
 @CustomerID INT,
 @Reason VARCHAR(255),
 @UserName VARCHAR(50)
AS
BEGIN
   SET NOCOUNT ON;
BEGIN TRANSACTION;
 BEGIN TRY
    

    -- Validate return quantity
    IF @Quantity <= 0
    BEGIN
       ROLLBACK TRANSACTION;
       THROW 51003, 'Return quantity must be positive.', 1;
    END

    -- If linked to a sale, ensure the return quantity does not exceed the sold quantity
    IF @SaleID IS NOT NULL
    BEGIN
       DECLARE @SoldQty INT;
       SELECT @SoldQty = ISNULL(SUM(Quantity),0) FROM SaleItems WHERE SaleID = @SaleID AND MedicineID = @MedicineID;
       IF @SoldQty = 0
       BEGIN
          ROLLBACK TRANSACTION;
          THROW 51004, 'No sold quantity found for this sale and medicine.', 1;
       END
       IF @Quantity > @SoldQty
       BEGIN
          ROLLBACK TRANSACTION;
          THROW 51005, 'Return quantity exceeds the sold quantity for this sale item.', 1;
       END
    END

    -- Insert return and capture new ReturnID
    INSERT INTO Returns
    (MedicineID, Quantity, UnitPrice, Amount, SaleID, CustomerID, Reason, UserName)
    VALUES
    (@MedicineID, @Quantity, @UnitPrice, @Amount,
     @SaleID, @CustomerID, @Reason, @UserName);

   DECLARE @ReturnID INT = SCOPE_IDENTITY();

    -- Read current medicine quantity and compute new quantity
    DECLARE @OldQty INT;
    SELECT @OldQty = Quantity FROM Medicines WHERE MedicineID = @MedicineID;
    IF @OldQty IS NULL
    BEGIN
       ROLLBACK TRANSACTION;
       THROW 51002, 'Medicine not found for return.', 1;
    END

    DECLARE @NewQty INT = @OldQty + @Quantity;

    -- Record stock adjustment using centralized proc (it will update Medicines.Quantity)
    DECLARE @ChangeQty INT = @NewQty - @OldQty; -- positive for returns
    DECLARE @AdjReason VARCHAR(255) = 'Return: ' + CAST(@ReturnID AS VARCHAR(20));

    IF @Reason IS NOT NULL AND LTRIM(RTRIM(@Reason)) <> ''
       SET @AdjReason = @AdjReason + ' - ' + @Reason;

    EXEC AddStockAdjustment
        @MedicineID = @MedicineID,
        @OldQty = @OldQty,
        @NewQty = @NewQty,
        @ChangeQty = @ChangeQty,
        @SupplierID = NULL,
        @Reason = @AdjReason,
        @UserName = @UserName;

   -- If this return is linked to a sale, reduce the sold quantity and update sale totals
   IF @SaleID IS NOT NULL
   BEGIN
      -- Subtract returned quantity from the sale item (don't let it go negative)
      UPDATE SaleItems
      SET Quantity = CASE WHEN Quantity > @Quantity THEN Quantity - @Quantity ELSE 0 END
      WHERE SaleID = @SaleID AND MedicineID = @MedicineID;

      -- Remove any sale items that now have zero quantity
      DELETE FROM SaleItems WHERE SaleID = @SaleID AND MedicineID = @MedicineID AND Quantity = 0;

      -- Recalculate sale totals (subtotal, tax, total) based on remaining sale items
      DECLARE @newSubtotal DECIMAL(18,2) = 0;
      DECLARE @taxRate DECIMAL(5,2) = 0;
      DECLARE @newTax DECIMAL(18,2) = 0;
      DECLARE @newTotal DECIMAL(18,2) = 0;

      SELECT @newSubtotal = ISNULL(SUM(Quantity * Price), 0) FROM SaleItems WHERE SaleID = @SaleID;
      SELECT TOP 1 @taxRate = ISNULL(tax_rate, 0) FROM Settings;
      SET @newTax = ROUND(@newSubtotal * @taxRate / 100.0, 2);
      SET @newTotal = @newSubtotal + @newTax;

      UPDATE Sales
      SET Subtotal = @newSubtotal,
         Tax = @newTax,
         Total = @newTotal
      WHERE SaleID = @SaleID;
   END
   --Activity Log
   DECLARE @ActionText VARCHAR(300);
   SET @ActionText = 'Added return with ID: ' + CAST(@ReturnID AS VARCHAR(10));
   Exec AddActivityLog 
       @UserName = @UserName,
       @Action = @ActionText;
   -- return generated ReturnID
   SELECT @ReturnID AS ReturnID;

    COMMIT TRANSACTION;
 END TRY
 BEGIN CATCH
    ROLLBACK TRANSACTION;
    THROW;
 END CATCH
END;
GO

/* -----------------------------
   STOCK ADJUSTMENT
------------------------------*/
CREATE PROCEDURE AddStockAdjustment
 @MedicineID INT,
 @OldQty INT,
 @NewQty INT,
 @ChangeQty INT,
 @SupplierID INT,
 @Reason VARCHAR(255),
 @UserName VARCHAR(50)
AS
BEGIN
   SET NOCOUNT ON;
 BEGIN TRANSACTION;
 BEGIN TRY

    INSERT INTO StockAdjustments
    (MedicineID, OldQty, NewQty, ChangeQty, SupplierID, Reason, UserName)
    VALUES
    (@MedicineID, @OldQty, @NewQty, @ChangeQty, @SupplierID, @Reason, @UserName);

    -- Apply the new quantity to Medicines table
    UPDATE Medicines
    SET Quantity = @NewQty
    WHERE MedicineID = @MedicineID;

    -- Recompute and persist medicine status based on new quantity and minimum stock
    DECLARE @MinStock INT;
    DECLARE @NewStatus VARCHAR(20);
    SELECT @MinStock = MinimumStock FROM Medicines WHERE MedicineID = @MedicineID;
    IF @NewQty <= 0
       SET @NewStatus = 'out of stock';
    ELSE IF @MinStock IS NOT NULL AND @MinStock > 0 AND @NewQty < @MinStock
       SET @NewStatus = 'low stock';
    ELSE
       SET @NewStatus = 'ok';

    UPDATE Medicines
    SET Status = @NewStatus
    WHERE MedicineID = @MedicineID;

    -- return generated AdjustmentID
   SELECT SCOPE_IDENTITY() AS AdjustmentID;

    COMMIT TRANSACTION;
 END TRY
 BEGIN CATCH
    ROLLBACK TRANSACTION;
    THROW;
 END CATCH
END;
GO

/* -----------------------------
   GET MEDICINE BY ID
------------------------------*/
CREATE PROCEDURE GetMedicineByID
 @MedicineID INT
AS
BEGIN
   SET NOCOUNT ON;
   SELECT Name, Category, Quantity, MinimumStock, Price, Status, SupplierID, SupplierName
   FROM vw_Medicines
   WHERE MedicineID = @MedicineID;
END;
GO

/* -----------------------------
   GET SETTINGS (SINGLE ROW)
------------------------------*/
CREATE PROCEDURE GetSettings
AS
BEGIN
   SET NOCOUNT ON;
   SELECT pharmacy_name, address, phone, tax_rate, currency, start_maximized FROM Settings;
END;
GO

/* -----------------------------
   UPDATE SETTINGS (UPSERT)
------------------------------*/
CREATE PROCEDURE UpdateSettings
 @pharmacy_name VARCHAR(100),
 @address VARCHAR(255),
 @phone VARCHAR(20),
 @tax_rate DECIMAL(5,2),
 @currency VARCHAR(10),
 @start_maximized BIT
AS
BEGIN
   SET NOCOUNT ON;
   BEGIN TRY
      IF EXISTS (SELECT 1 FROM Settings)
      BEGIN
         UPDATE Settings
         SET pharmacy_name = @pharmacy_name,
             address = @address,
             phone = @phone,
             tax_rate = @tax_rate,
             currency = @currency,
             start_maximized = @start_maximized;
      END
      ELSE
      BEGIN
         INSERT INTO Settings (pharmacy_name, address, phone, tax_rate, currency, start_maximized)
         VALUES (@pharmacy_name, @address, @phone, @tax_rate, @currency, @start_maximized);
      END
   END TRY
   BEGIN CATCH
      THROW;
   END CATCH
END;
GO

/* -----------------------------
   GET ALL USERS
------------------------------*/
CREATE PROCEDURE GetAllUsers
AS
BEGIN
   SET NOCOUNT ON;
   SELECT Username, FullName, PasswordHash, Role, Active, Email, Phone FROM vw_Users;
END;
GO

/* -----------------------------
   GET ACTIVITY LOG
------------------------------*/
CREATE PROCEDURE GetActivityLog
AS
BEGIN
   SET NOCOUNT ON;
    SELECT LogID, UserName, Action, LogTime FROM vw_ActivityLog;
END;
GO

/* -----------------------------
   ADD ACTIVITY LOG ENTRY
------------------------------*/
CREATE PROCEDURE AddActivityLog
 @UserName VARCHAR(50),
 @Action VARCHAR(200)
AS
BEGIN
   SET NOCOUNT ON;
   INSERT INTO ActivityLog (UserName, Action) VALUES (@UserName, @Action);
   SELECT SCOPE_IDENTITY() AS LogID;
END;
GO

/* -----------------------------
   TOGGLE USER STATUS
------------------------------*/
CREATE PROCEDURE ToggleUserStatus
 @Username VARCHAR(50)
AS
BEGIN
   SET NOCOUNT ON;
   BEGIN TRANSACTION;
   BEGIN TRY
      

      UPDATE Users
      SET Active = CASE WHEN Active = 1 THEN 0 ELSE 1 END
      WHERE Username = @Username;
      --Activity Log
      DECLARE @ActionText VARCHAR(300);
      SET @ActionText = 'Toggled active status for user: ' + @Username;
      Exec AddActivityLog 
          @UserName = 'admin',
          @Action = @ActionText;

      -- return the new active value
      SELECT Active FROM Users WHERE Username = @Username;

      COMMIT TRANSACTION;
   END TRY
   BEGIN CATCH
      ROLLBACK TRANSACTION;
      THROW;
   END CATCH
END;
GO

/* -----------------------------
   SUPPLIER MANAGEMENT
------------------------------*/
CREATE PROCEDURE AddSupplier
 @Name VARCHAR(100),
 @Company VARCHAR(100),
 @Phone VARCHAR(20),
 @Email VARCHAR(100),
 @Active BIT,
 @UserName VARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
BEGIN TRANSACTION;
 BEGIN TRY
    

    INSERT INTO Suppliers (Name, Company, Phone, Email, Active)
    VALUES (@Name, @Company, @Phone, @Email, @Active);
   --Activity Log
   DECLARE @ActionText VARCHAR(300);
   SET @ActionText = 'Added new supplier: ' + @Name;
   Exec AddActivityLog 
       @UserName = @UserName,
       @Action = @ActionText;

    -- return generated SupplierID
   SELECT SCOPE_IDENTITY() AS SupplierID;

    COMMIT TRANSACTION;
 END TRY
 BEGIN CATCH
    ROLLBACK TRANSACTION;
    THROW;
 END CATCH
END;
GO

CREATE PROCEDURE UpdateSupplier
 @SupplierID INT,
 @Name VARCHAR(100),
 @Company VARCHAR(100),
 @Phone VARCHAR(20),
 @Email VARCHAR(100),
 @Active BIT,
 @UserName VARCHAR(50)
AS
BEGIN
   SET NOCOUNT ON;
 UPDATE Suppliers
 SET Name = @Name,
    Company = @Company,
    Phone = @Phone,
    Email = @Email,
    Active = @Active
 WHERE SupplierID = @SupplierID;
   --Activity Log
   DECLARE @ActionText VARCHAR(300);
   SET @ActionText = 'Updated supplier: ' + @Name + ' (ID: ' + CAST(@SupplierID AS VARCHAR(10)) + ')';
   Exec AddActivityLog 
       @UserName = @UserName,
       @Action = @ActionText;
END;
GO

CREATE PROCEDURE DeleteSupplier
 @SupplierID INT,
 @UserName VARCHAR(50)
AS
BEGIN
   SET NOCOUNT ON;
BEGIN TRANSACTION;
 BEGIN TRY
    

    -- Null out references to this supplier so delete can proceed
    UPDATE Medicines SET SupplierID = NULL WHERE SupplierID = @SupplierID;
    UPDATE StockAdjustments SET SupplierID = NULL WHERE SupplierID = @SupplierID;

    -- Delete the supplier
    DELETE FROM Suppliers WHERE SupplierID = @SupplierID;

    -- Activity Log
    DECLARE @ActionText VARCHAR(300);
    SET @ActionText = 'Deleted supplier with ID: ' + CAST(@SupplierID AS VARCHAR(10));
    Exec AddActivityLog 
        @UserName = @UserName,
        @Action = @ActionText;

    COMMIT TRANSACTION;
 END TRY
 BEGIN CATCH
    ROLLBACK TRANSACTION;
    THROW;
 END CATCH
END;
GO

/* -----------------------------
   USER MANAGEMENT
------------------------------*/
CREATE PROCEDURE AddUser
 @Username VARCHAR(50),
 @FullName VARCHAR(100),
 @PasswordHash VARCHAR(255),
 @Role VARCHAR(20),
 @Active BIT = 1,
 @Email VARCHAR(100),
 @Phone VARCHAR(20)
AS
BEGIN
   SET NOCOUNT ON;
 INSERT INTO Users (Username, FullName, PasswordHash, Role, Active, Email, Phone)
 VALUES (@Username, @FullName, @PasswordHash, @Role, @Active, @Email, @Phone);
   --Activity Log
   DECLARE @ActionText VARCHAR(300);
   SET @ActionText = 'Added new user: ' + @Username;
   Exec AddActivityLog 
       @UserName = 'admin',
       @Action = @ActionText;
END;
GO

CREATE PROCEDURE UpdateUser
 @Username VARCHAR(50),
 @FullName VARCHAR(100) = NULL,
 @PasswordHash VARCHAR(255) = NULL,
 @Role VARCHAR(20) = NULL,
 @Active BIT = NULL,
 @Email VARCHAR(100) = NULL,
 @Phone VARCHAR(20) = NULL
AS
BEGIN
   SET NOCOUNT ON;
 UPDATE Users
 SET FullName = COALESCE(@FullName, FullName),
    PasswordHash = COALESCE(@PasswordHash, PasswordHash),
    Role = COALESCE(@Role, Role),
    Active = COALESCE(@Active, Active),
    Email = COALESCE(@Email, Email),
    Phone = COALESCE(@Phone, Phone)
 WHERE Username = @Username;
   --Activity Log
   DECLARE @ActionText VARCHAR(300);
   SET @ActionText = 'Updated user: ' + @Username;
   Exec AddActivityLog 
       @UserName = 'admin',
       @Action = @ActionText;
END;
GO

CREATE PROCEDURE DeleteUser
 @Username VARCHAR(50)
AS
BEGIN
   SET NOCOUNT ON;
BEGIN TRANSACTION;
 BEGIN TRY
    

    -- Ensure a placeholder 'removed' user exists so foreign keys remain valid
    IF NOT EXISTS (SELECT 1 FROM Users WHERE Username = 'removed')
    BEGIN
       INSERT INTO Users (Username, FullName, PasswordHash, Role, Active, Email, Phone)
       VALUES ('removed', 'Removed User', '', 'system', 0, '', '');
    END

    -- Replace references to the user in other tables with the placeholder
    UPDATE Sales SET UserName = 'removed' WHERE UserName = @Username;
    UPDATE Returns SET UserName = 'removed' WHERE UserName = @Username;
    UPDATE StockAdjustments SET UserName = 'removed' WHERE UserName = @Username;
    UPDATE ActivityLog SET UserName = 'removed' WHERE UserName = @Username;

    -- Now safe to delete the user record
    DELETE FROM Users WHERE Username = @Username;

    -- Activity Log
    DECLARE @ActionText VARCHAR(300);
    SET @ActionText = 'Deleted user: ' + @Username;
    Exec AddActivityLog 
        @UserName = 'admin',
        @Action = @ActionText;

    COMMIT TRANSACTION;
 END TRY
 BEGIN CATCH
    ROLLBACK TRANSACTION;
    THROW;
 END CATCH
END;
GO

/* -----------------------------
   READ / REPORT PROCEDURES
------------------------------*/

CREATE PROCEDURE GetAllMedicines
AS
BEGIN
   SET NOCOUNT ON;
   SELECT MedicineID, Name, Category, Quantity, Price, MinimumStock, Status, CreatedDate, SupplierID, SupplierName
   FROM vw_Medicines;
END;
GO

CREATE PROCEDURE GetAllCustomers
AS
BEGIN
   SET NOCOUNT ON;
   SELECT CustomerID, Name, Phone, Email, CreatedDate, TotalPurchases
   FROM vw_Customers;
END;
GO

/* -----------------------------
   GET CUSTOMER BY ID
------------------------------*/
CREATE PROCEDURE GetCustomerByID
 @CustomerID INT
AS
BEGIN
   SET NOCOUNT ON;
   SELECT CustomerID, Name, Phone, Email, CreatedDate, TotalPurchases
   FROM Customers
   WHERE CustomerID = @CustomerID;
END;
GO

CREATE PROCEDURE GetAllSuppliers
AS
BEGIN
   SET NOCOUNT ON;
   SELECT SupplierID, Name, Company, Phone, Email, Active, CreatedDate
   FROM vw_Suppliers;
END;
GO

CREATE PROCEDURE GetAllSales
AS
BEGIN
   SET NOCOUNT ON;
   SELECT SaleID, CustomerID, CustomerName, Subtotal, Tax, Total, Timestamp, UserName, UserFullName
   FROM vw_Sales_WithInfo;
END;
GO

/* -----------------------------
   GET ALL SALE DETAILS
------------------------------*/
CREATE PROCEDURE GetAllSaleDetails
AS
BEGIN
   SET NOCOUNT ON;
   SELECT SaleID, MedicineID, MedicineName, Quantity, Price
   FROM vw_Sales_Details;
END;
GO

/* -----------------------------
   DASHBOARD STATS
------------------------------*/
CREATE PROCEDURE GetDashboardStats
AS
BEGIN
   SET NOCOUNT ON;
   SELECT
     (SELECT COUNT(*) FROM Medicines) AS total_medicines,
     (SELECT COUNT(*) FROM Medicines WHERE Quantity < ISNULL(MinimumStock, 0)) AS low_stock,
     (SELECT COUNT(*) FROM Sales WHERE CONVERT(date, [Timestamp]) = CONVERT(date, GETDATE())) AS today_sales_count,
     (SELECT ISNULL(SUM(Total),0) FROM Sales WHERE CONVERT(date, [Timestamp]) = CONVERT(date, GETDATE())) AS today_revenue;
END;
GO

CREATE PROCEDURE GetSaleByID
 @SaleID INT
AS
BEGIN
   SET NOCOUNT ON;
   SELECT SaleID, CustomerID, CustomerName, Subtotal, Tax, Total, Timestamp, UserName, UserFullName
   FROM vw_Sales_WithInfo
   WHERE SaleID = @SaleID;

   SELECT SaleItemID, MedicineID, Quantity, Price
   FROM SaleItems
   WHERE SaleID = @SaleID;
END;
GO

CREATE PROCEDURE GetStockAdjustments
AS
BEGIN
   SET NOCOUNT ON;
   SELECT AdjustmentID, MedicineID, MedicineName, OldQty, NewQty, ChangeQty, SupplierID, SupplierName, Reason, UserName, UserFullName, Timestamp
   FROM vw_StockAdjustments_Detailed;
END;
GO

CREATE PROCEDURE GetAllReturns
AS
BEGIN
   SET NOCOUNT ON;
   SELECT ReturnID, SaleID, MedicineID, MedicineName, Quantity, UnitPrice, Amount, CustomerID, CustomerName, Reason, Timestamp, UserName
   FROM vw_Returns_Detailed;
END;
GO

/* ============================================
   =============     VIEWS     ================
   ============================================ */

/* -----------------------------
   VIEW: ALL MEDICINES WITH STATUS
------------------------------*/
CREATE VIEW vw_Medicines AS
SELECT 
   m.MedicineID, 
   m.Name, 
   m.Category, 
   m.Quantity, 
   m.Price, 
   m.MinimumStock, 
   m.Status, 
   m.CreatedDate,
   m.SupplierID,
   ISNULL(s.Name, 'unknown') AS SupplierName
FROM Medicines m
LEFT JOIN Suppliers s ON m.SupplierID = s.SupplierID;
GO

/* -----------------------------
   VIEW: ALL CUSTOMERS WITH DETAILS
------------------------------*/
CREATE VIEW vw_Customers AS
SELECT 
    CustomerID, 
    Name, 
    Phone, 
    Email, 
    CreatedDate, 
    TotalPurchases
FROM Customers;
GO

/* -----------------------------
   VIEW: ALL SUPPLIERS WITH STATUS
------------------------------*/
CREATE VIEW vw_Suppliers AS
SELECT 
    SupplierID, 
    Name, 
    Company, 
    Phone, 
    Email, 
    Active, 
    CreatedDate
FROM Suppliers;
GO

/* -----------------------------
   VIEW: ALL USERS WITH DETAILS
------------------------------*/
CREATE VIEW vw_Users AS
SELECT 
    Username, 
    FullName, 
    PasswordHash, 
    Role, 
    Active, 
    Email, 
    Phone
FROM Users;
GO

/* -----------------------------
   VIEW: ACTIVITY LOG
------------------------------*/
CREATE VIEW vw_ActivityLog AS
SELECT 
    LogID, 
    UserName, 
    Action, 
    LogTime
FROM ActivityLog;
GO

/* ----------------------------------
   JOINED / DETAILED VIEWS USING JOINS
-----------------------------------*/

CREATE VIEW vw_Sales_Details AS
SELECT
   si.SaleItemID,
   si.SaleID,
   si.MedicineID,
   ISNULL(m.Name, '') AS MedicineName,
   si.Quantity,
   si.Price,
   (si.Quantity * si.Price) AS LineTotal
FROM SaleItems si
LEFT JOIN Medicines m ON si.MedicineID = m.MedicineID;
GO

CREATE VIEW vw_Sales_WithInfo AS
SELECT
   s.SaleID,
   s.CustomerID,
   ISNULL(c.Name, 'Walk-in Customer') AS CustomerName,
   s.Subtotal,
   s.Tax,
   s.Total,
   s.Timestamp,
   s.UserName,
   ISNULL(u.FullName, '') AS UserFullName
FROM Sales s
LEFT JOIN Customers c ON s.CustomerID = c.CustomerID
LEFT JOIN Users u ON s.UserName = u.Username;
GO

CREATE VIEW vw_Returns_Detailed AS
SELECT
   r.ReturnID,
   r.SaleID,
   r.MedicineID,
   ISNULL(m.Name, '') AS MedicineName,
   r.Quantity,
   r.UnitPrice,
   r.Amount,
   r.CustomerID,
   ISNULL(c.Name, 'Walk-in Customer') AS CustomerName,
   r.Reason,
   r.Timestamp,
   r.UserName
FROM Returns r
LEFT JOIN Medicines m ON r.MedicineID = m.MedicineID
LEFT JOIN Customers c ON r.CustomerID = c.CustomerID;
GO

CREATE VIEW vw_StockAdjustments_Detailed AS
SELECT
   sa.AdjustmentID,
   sa.MedicineID,
   ISNULL(m.Name, '') AS MedicineName,
   sa.OldQty,
   sa.NewQty,
   sa.ChangeQty,
   sa.SupplierID,
   ISNULL(sup.Name, 'unknown') AS SupplierName,
   sa.Reason,
   sa.UserName,
   ISNULL(u.FullName, '') AS UserFullName,
   sa.Timestamp
FROM StockAdjustments sa
LEFT JOIN Medicines m ON sa.MedicineID = m.MedicineID
LEFT JOIN Suppliers sup ON sa.SupplierID = sup.SupplierID
LEFT JOIN Users u ON sa.UserName = u.Username;
GO

/* ============================================
   =============     INDEXES     ==============
   ============================================ */

CREATE INDEX IX_Sales_Timestamp ON Sales([Timestamp]);
CREATE INDEX IX_Sales_CustomerID ON Sales(CustomerID);
CREATE INDEX IX_SaleItems_SaleID ON SaleItems(SaleID);
CREATE INDEX IX_SaleItems_MedicineID ON SaleItems(MedicineID);
CREATE INDEX IX_Returns_MedicineID ON Returns(MedicineID);
CREATE INDEX IX_Returns_SaleID ON Returns(SaleID);
CREATE INDEX IX_Returns_CustomerID ON Returns(CustomerID);
CREATE INDEX IX_StockAdj_MedicineID ON StockAdjustments(MedicineID);
CREATE INDEX IX_StockAdj_SupplierID ON StockAdjustments(SupplierID);
CREATE INDEX IX_StockAdj_UserName ON StockAdjustments(UserName);
CREATE INDEX IX_Medicines_Quantity ON Medicines(Quantity);
CREATE INDEX IX_Medicines_Name ON Medicines(Name);
CREATE INDEX IX_Medicines_Category ON Medicines(Category);
CREATE INDEX IX_Users_Role ON Users(Role);
CREATE INDEX IX_ActivityLog_LogTime ON ActivityLog(LogTime);
GO
/* ----------------------------------
   REPORTS - simple stored procedures
-----------------------------------*/

CREATE PROCEDURE GetSalesReport
 @period VARCHAR(10) = 'today'  -- accepted: 'today','week','month'
AS
BEGIN
   SET NOCOUNT ON;
   DECLARE @start DATETIME;
   IF LOWER(@period) = 'today'
      SET @start = CONVERT(DATE, GETDATE());
   ELSE IF LOWER(@period) = 'week'
      SET @start = DATEADD(day, -7, GETDATE());
   ELSE
      SET @start = DATEADD(day, -30, GETDATE());

   SELECT SaleID, CustomerID, CustomerName, Subtotal, Tax, Total, [Timestamp]
   FROM vw_Sales_WithInfo
   WHERE [Timestamp] >= @start
   ORDER BY [Timestamp] DESC;
END;
GO

CREATE PROCEDURE GetStockReportSummary
AS
BEGIN
   SET NOCOUNT ON;
   SELECT
     (SELECT COUNT(*) FROM Medicines) AS total_medicines,
     (SELECT ISNULL(SUM(CAST(Quantity AS BIGINT) * CAST(Price AS DECIMAL(18,2))),0) FROM Medicines) AS total_value,
     (SELECT COUNT(*) FROM Medicines WHERE Quantity < ISNULL(MinimumStock, 0)) AS low_stock_count;
END;
GO

CREATE PROCEDURE GetLowStockItems
AS
BEGIN
   SET NOCOUNT ON;
   SELECT MedicineID, Name, Category, Quantity, MinimumStock, Price
   FROM vw_Medicines
   WHERE Quantity < ISNULL(MinimumStock, 0)
   ORDER BY (MinimumStock - Quantity) DESC;
END;
GO

/* -----------------------------
   SEARCH PROCEDURES
   Provide server-side search to improve performance for large datasets.
   These procedures perform simple LIKE matches against relevant columns.
------------------------------*/
CREATE PROCEDURE SearchMedicines
 @Query VARCHAR(200)
AS
BEGIN
   SET NOCOUNT ON;
   DECLARE @q VARCHAR(210) = '%' + TRIM(ISNULL(@Query, '')) + '%';
   SELECT MedicineID, Name, Category, Quantity, Price, MinimumStock, Status, CreatedDate
   FROM vw_Medicines
   WHERE Name LIKE @q OR Category LIKE @q OR CAST(MedicineID AS VARCHAR(20)) LIKE @q
   ORDER BY Name;
END;
GO

CREATE PROCEDURE SearchCustomers
 @Query VARCHAR(200)
AS
BEGIN
   SET NOCOUNT ON;
   DECLARE @q VARCHAR(210) = '%' + TRIM(ISNULL(@Query, '')) + '%';
   SELECT CustomerID, Name, Phone, Email, CreatedDate, TotalPurchases
   FROM vw_Customers
   WHERE Name LIKE @q OR Phone LIKE @q OR Email LIKE @q OR CAST(CustomerID AS VARCHAR(20)) LIKE @q
   ORDER BY Name;
END;
GO

CREATE PROCEDURE SearchSuppliers
 @Query VARCHAR(200)
AS
BEGIN
   SET NOCOUNT ON;
   DECLARE @q VARCHAR(210) = '%' + TRIM(ISNULL(@Query, '')) + '%';
   SELECT SupplierID, Name, Company, Phone, Email, Active, CreatedDate
   FROM vw_Suppliers
   WHERE Name LIKE @q OR Company LIKE @q OR Phone LIKE @q OR Email LIKE @q OR CAST(SupplierID AS VARCHAR(20)) LIKE @q
   ORDER BY Name;
END;
GO

CREATE PROCEDURE SearchUsers
 @Query VARCHAR(200)
AS
BEGIN
   SET NOCOUNT ON;
   DECLARE @q VARCHAR(210) = '%' + TRIM(ISNULL(@Query, '')) + '%';
   SELECT Username, FullName, PasswordHash, Role, Active, Email, Phone
   FROM vw_Users
   WHERE Username LIKE @q OR FullName LIKE @q OR Email LIKE @q OR Phone LIKE @q
   ORDER BY Username;
END;
GO

CREATE PROCEDURE GetCustomersReport
AS
BEGIN
   SET NOCOUNT ON;
   -- First resultset: summary
   SELECT COUNT(*) AS total_customers, ISNULL(SUM(TotalPurchases),0) AS total_purchases
   FROM Customers;

   -- Second resultset: top customers by spending
   SELECT TOP 10 CustomerID, Name, TotalPurchases
   FROM Customers
   ORDER BY TotalPurchases DESC;
END;
GO


-----------------------------------------------
--  TRIGGERS TO ENFORCE DATA INTEGRITY
-----------------------------------------------
--Trigger to display the total number of medicines after insert, update, delete
CREATE TRIGGER UpdateMedicineCount
ON Medicines
AFTER INSERT, UPDATE, DELETE
AS
BEGIN
      DECLARE @total_medicines INT;
      SELECT @total_medicines = COUNT(*) FROM Medicines;
   
      PRINT 'Total Medicines in Inventory: ' + CAST(@total_medicines AS VARCHAR(10));
   END;
GO
--Trigger to prevent deletion of database
CREATE TRIGGER PreventDatabaseDeletion
ON ALL SERVER
FOR DROP_DATABASE
AS
BEGIN
    RAISERROR('Database deletion is not allowed.', 16, 1);
    ROLLBACK;
END;
GO
--Trigger to prevent drop tables
CREATE TRIGGER PreventTableDrop
ON DATABASE
FOR DROP_TABLE
AS
BEGIN
    RAISERROR('Table drop is not allowed.', 16, 1);
    ROLLBACK;
END;
GO
-----------------------------------------------
-- END OF SCRIPT
-----------------------------------------------