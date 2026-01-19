import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.font as tkfont
from datetime import datetime, timedelta
import sys
import ctypes
try:
    import pyodbc
except ImportError:
    _tmp_root = tk.Tk()
    _tmp_root.withdraw()
    messagebox.showerror("Dependency Error", "pyodbc is not installed. Please install it manually.")
    _tmp_root.destroy()
    sys.exit(1)

# Database connection setup
conn = None
cursor = None
try:
    conn = pyodbc.connect('DRIVER={SQL Server};SERVER=DESKTOP-HE9I4KD\\SQLEXPRESS;DATABASE=PharmacyDB;Trusted_Connection=yes;')
    cursor = conn.cursor()
except (pyodbc.Error, AttributeError):
    _tmp_root = tk.Tk()
    _tmp_root.withdraw()
    messagebox.showerror("Database Error", "Unable to connect to SQL Server.\nPlease ensure SQL Server is running.")
    _tmp_root.destroy()
    sys.exit(1)

class PharmacyBackend:
    def __init__(self):
        # Keep no persistent settings cache. Provide helpers to always read
        # settings from the database so the UI never relies on stale in-memory data.
        # Backwards-compatible `self.settings` remains empty.
        self.settings = {}

    def get_settings(self):
        """Read settings from DB on-demand and return a dict.
        This avoids keeping an in-memory, possibly stale, copy.
        """
        defaults = {
            'pharmacy_name': 'City Pharmacy',
            'address': '',
            'phone': '',
            'tax_rate': 0.0,
            'currency': 'USD',
            'start_maximized': True
        }
        try:
            cursor.execute("EXEC GetSettings")
            row = cursor.fetchone()
            if not row:
                return defaults
            return {
                'pharmacy_name': row[0] or defaults['pharmacy_name'],
                'address': row[1] or defaults['address'],
                'phone': row[2] or defaults['phone'],
                'tax_rate': float(row[3]) if row[3] is not None else defaults['tax_rate'],
                'currency': row[4] or defaults['currency'],
                'start_maximized': bool(row[5]) if row[5] is not None else defaults['start_maximized']
            }
        except Exception:
            return defaults

    def update_settings(self, pharmacy_name, address, phone, tax_rate, currency, start_maximized, user=None):
        """Persist settings to DB via stored procedure."""
        try:
            cursor.execute("EXEC UpdateSettings ?,?,?,?,?,?", pharmacy_name, address, phone, tax_rate, currency, 1 if start_maximized else 0)
            conn.commit()
            return True
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            return False
    
    # Helper methods to get data from database
    def get_medicines(self):
        """Get all medicines from database view"""
        results = {}
        try:
            cursor.execute("EXEC GetAllMedicines")
            rows = cursor.fetchall()
        except Exception:
            # Stored procedure missing or failed — return empty set (no inline SQL)
            rows = []

        for r in rows:
            # Normalize MedicineID to string so UI code continues to work with string keys
            mid_key = str(r[0])
            # Map columns returned by GetAllMedicines (now includes supplier columns)
            med = {
                'name': r[1] or '',
                'category': r[2] or '',
                'quantity': int(r[3] or 0),
                'price': float(r[4] or 0),
                'minimum_stock': int(r[5] or 0),
                'status': r[6] or '',
                'created_date': r[7] if len(r) > 7 else None,
                'supplier_id': str(r[8]) if (len(r) > 8 and r[8] is not None) else None,
                'supplier_name': r[9] or '' if len(r) > 9 else ''
            }
            results[mid_key] = med
        return results
    
    def get_customers(self):
        """Get all customers from database view"""
        results = {}
        try:
            cursor.execute("EXEC GetAllCustomers")
            rows = cursor.fetchall()
        except Exception:
            rows = []

        for r in rows:
            # Normalize CustomerID to string for consistent UI keys
            cid_key = str(r[0])
            results[cid_key] = {
                'name': r[1] or '',
                'phone': r[2] or '',
                'email': r[3] or '',
                'created_date': r[4] if len(r) > 4 else None,
                'total_purchases': float(r[5] or 0) if len(r) > 5 else 0
            }
        return results
    
    def get_suppliers(self):
        """Get all suppliers from database view"""
        results = {}
        try:
            cursor.execute("EXEC GetAllSuppliers")
            rows = cursor.fetchall()
        except Exception:
            rows = []

        for r in rows:
            # Normalize SupplierID to string so UI code continues to work with string keys
            sid_key = str(r[0])
            results[sid_key] = {
                'name': r[1] or '',
                'company': r[2] or '',
                'phone': r[3] or '',
                'email': r[4] or '',
                'active': bool(r[5]) if r[5] is not None else True,
                'created_date': r[6] if len(r) > 6 else None
            }
        return results
    
    def get_users(self):
        """Get all users from database view"""
        results = {}
        try:
            cursor.execute("EXEC GetAllUsers")
            rows = cursor.fetchall()
        except Exception:
            rows = []

        for r in rows:
            results[r[0]] = {
                'full_name': r[1] or '',
                'password': r[2] or '',
                'role': r[3] or '',
                'active': bool(r[4]) if r[4] is not None else True,
                'email': r[5] or '',
                'phone': r[6] or ''
            }
        return results
    
    def get_sales(self):
        """Get all sales from database view"""
        results = {}
        # Prefer stored procedure if available
        try:
            cursor.execute("EXEC GetAllSales")
            rows = cursor.fetchall()
            for r in rows:
                sale_id = r[0]
                # Normalize SaleID to string for consistent UI keys
                key = str(sale_id)
                results[key] = {
                    'customer_id': str(r[1]) if r[1] is not None else None,
                    'customer_name': r[2] or '',
                    'items': [],
                    'subtotal': float(r[3] or 0),
                    'tax': float(r[4] or 0),
                    'total': float(r[5] or 0),
                    'timestamp': r[6] if len(r) > 6 else None,
                    'user': r[7] if len(r) > 7 else None,
                    'user_fullname': r[8] if len(r) > 8 else None
                }
                
            # Populate sale items via stored procedure exposing vw_Sales_Details
            try:
                cursor.execute("EXEC GetAllSaleDetails")
                detail_rows = cursor.fetchall()
            except Exception:
                detail_rows = []
            for dr in detail_rows:
                sid = dr[0]
                sid_key = str(sid)
                if sid_key in results:
                    # support both shapes (with MedicineName) and without
                    if len(dr) >= 5:
                        mid = dr[1]
                        mname = dr[2]
                        qty = int(dr[3] or 0)
                        price = float(dr[4] or 0)
                    else:
                        mid = dr[1]
                        mname = ''
                        qty = int(dr[2] or 0)
                        price = float(dr[3] or 0)
                    results[sid_key]['items'].append({'medicine_id': str(mid), 'medicine_name': mname, 'quantity': qty, 'price': price})
        except Exception:
            # Stored procedure failed — return empty results (no inline SQL fallback)
            return results
        return results
    
    def get_returns(self):
        """Get all returns from the detailed view (includes medicine/customer names)"""
        results = {}
        # Prefer stored procedure if available
        try:
            cursor.execute("EXEC GetAllReturns")
            rows = cursor.fetchall()
        except Exception:
            rows = []

        for r in rows:
            # When using base table fallback the column order differs; handle both shapes
            if len(r) >= 12:
                rid = str(r[0])
                results[rid] = {
                    'sale_id': r[1] or None,
                    'medicine_id': r[2] or None,
                    'medicine_name': r[3] or '',
                    'quantity': int(r[4] or 0),
                    'unit_price': float(r[5] or 0),
                    'amount': float(r[6] or 0),
                    'customer_id': str(r[7]) if r[7] is not None else None,
                    'customer_name': r[8] or '',
                    'reason': r[9] or '',
                    'timestamp': r[10] if len(r) > 10 else None,
                    'user': r[11] if len(r) > 11 else None
                }
            else:
                rid = str(r[0])
                results[rid] = {
                    'sale_id': r[5] or None,
                    'medicine_id': r[1] or None,
                    'medicine_name': '',
                    'quantity': int(r[2] or 0),
                    'unit_price': float(r[3] or 0),
                    'amount': float(r[4] or 0),
                    'customer_id': str(r[6]) if (len(r) > 6 and r[6] is not None) else None,
                    'customer_name': '',
                    'reason': r[7] or '' if len(r) > 7 else '',
                    'timestamp': r[8] if len(r) > 8 else None,
                    'user': r[9] if len(r) > 9 else None
                }
        return results
    
    def get_stock_adjustments(self):
        """Get all stock adjustments from database view"""
        results = {}
        # Prefer stored procedure if available
        try:
            cursor.execute("EXEC GetStockAdjustments")
            rows = cursor.fetchall()
        except Exception:
            rows = []

        for r in rows:
            aid = str(r[0])
            if len(r) >= 12:
                reason_text = (r[8] or '') if r[8] is not None else ''

                results[aid] = {
                    'medicine_id': str(r[1]) if r[1] is not None else None,
                    'medicine_name': r[2] or '',
                    'old_quantity': int(r[3] or 0),
                    'new_quantity': int(r[4] or 0),
                    'change': int(r[5] or 0),
                    'supplier_id': str(r[6]) if r[6] is not None else None,
                    'supplier_name': r[7] or '',
                    'reason': r[8] or '',
                    'user': r[9] or '',
                    'user_fullname': r[10] if len(r) > 10 else None,
                    'timestamp': r[11] if len(r) > 11 else None
                }
            else:
                reason_text = (r[6] or '') if r[6] is not None else ''
                results[aid] = {
                    'medicine_id': str(r[1]) if r[1] is not None else None,
                    'medicine_name': '',
                    'old_quantity': int(r[2] or 0),
                    'new_quantity': int(r[3] or 0),
                    'change': int(r[4] or 0),
                    'supplier_id': str(r[5]) if r[5] is not None else None,
                    'supplier_name': '',
                    'reason': r[6] or '',
                    'user': r[7] or '',
                    'user_fullname': None,
                    'timestamp': r[8] if len(r) > 8 else None
                }
        return results
    
    def get_activity_log(self):
        """Get activity log from database view"""
        results = {}
        # Prefer stored procedure if available
        try:
            cursor.execute("EXEC GetActivityLog")
            rows = cursor.fetchall()
        except Exception:
            rows = []

        for r in rows:
            log_id = int(r[0]) if r[0] else str(r[0])
            results[log_id] = {
                'user': r[1] or '',
                'action': r[2] or '',
                'timestamp': r[3] if len(r) > 3 else None
            }
        return results
    
    def add_medicine(self, name, category, quantity, price, medicine_id=None, minimum_stock=10, supplier_id=None, user=None):
        # Add a new medicine to inventory (database only)
        qty = int(quantity) if quantity else 0
        min_stock = int(minimum_stock or 10)

        # Determine status based on quantities and minimum stock
        status = 'ok'
        if qty <= 0:
            status = 'out of stock'
        elif qty < min_stock:
            status = 'low stock'
        # Add to database and return the generated MedicineID as a string.
        try:
            # Pass supplier_id (INT) to stored procedure; allow NULL
            try:
                supp_param = int(supplier_id) if supplier_id is not None else None
            except Exception:
                supp_param = None
            # Status is now computed server-side in AddMedicine; do not pass local status
            cursor.execute("EXEC AddMedicine ?,?,?,?,?,?,?", name, category, qty, price, min_stock, supp_param, user)
            row = cursor.fetchone()
            try:
                conn.commit()
            except Exception:
                conn.rollback()

            new_med_id = None
            if row and len(row) > 0:
                try:
                    new_med_id = int(row[0])
                except Exception:
                    new_med_id = None

            return str(new_med_id) if new_med_id is not None else None
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            return None
    
    def update_medicine(self, medicine_id, name=None, category=None, quantity=None, price=None, minimum_stock=None, supplier_id=None, record_adjustment=False, user=None, reason=None):
        # Update medicine details (database only)
        try:
            # Get current medicine data from database
            cursor.execute("EXEC GetMedicineByID ?", int(medicine_id))
            row = cursor.fetchone()
            if not row:
                return False
            
            # Current values
            db_name = name if name is not None else row[0]
            db_category = category if category is not None else row[1]
            old_qty = int(row[2] or 0)
            db_qty = int(quantity) if quantity is not None else old_qty
            db_price = price if price is not None else float(row[4])
            db_min_stock = int(minimum_stock) if minimum_stock is not None else int(row[3] or 0)
            
            # Status is now computed inside the database `UpdateMedicine`
            # stored procedure (it will use @Quantity and @MinimumStock).
            # Use provided supplier_id if given, otherwise try to read from returned row
            supp_param = None
            if supplier_id is not None:
                try:
                    supp_param = int(supplier_id)
                except Exception:
                    supp_param = None
            else:
                try:
                    if len(row) > 6:
                        try:
                            supp_param = int(row[6])
                        except Exception:
                            supp_param = None
                except Exception:
                    supp_param = None

            cursor.execute("EXEC UpdateMedicine ?,?,?,?,?,?,?,?", int(medicine_id), db_name, db_category, db_qty, db_price, db_min_stock, supp_param, user)
            conn.commit()

            return True
        except Exception:
            conn.rollback()
            return False
    
    def delete_medicine(self, medicine_id, user = None):
        # Delete medicine from inventory (database only)
        try:
            cursor.execute("EXEC DeleteMedicineCascade ?,?", int(medicine_id), user)
            conn.commit()
            #self.add_activity(f'Deleted medicine {medicine_id}')
            return True
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            return False
    
    def add_customer(self, name, phone, email, user=None):
        # Add a new customer (database only)
        # Let the database generate the integer CustomerID (IDENTITY).
            # Client-side validation: require non-empty phone and email
            if not phone or str(phone).strip() == '' or not email or str(email).strip() == '':
                return None
            try:
                # Pass the values as provided (not forcing empty strings)
                cursor.execute("EXEC AddCustomer ?,?,?,?", name, phone, email, user)
                row = cursor.fetchone()
                conn.commit()
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                print("AddCustomer failed:", e)
                return None

            if not row:
                return None

            try:
                new_id = int(row[0])
            except Exception:
                return None

            return str(new_id)

    def update_customer(self, customer_id, name=None, phone=None, email=None, user=None):
        # Update customer details (database only)
        try:
            # Get current customer data via stored procedure
            # ensure we pass integer CustomerID to the DB
            int_cid = int(customer_id)
            cursor.execute("EXEC GetCustomerByID ?", int_cid)
            row = cursor.fetchone()
            if not row:
                return False
            
            db_name = name if name is not None else row[0]
            db_phone = phone if phone is not None else row[1]
            db_email = email if email is not None else row[2]
            
            cursor.execute("EXEC UpdateCustomer ?,?,?,?,?", int_cid, db_name, db_phone, db_email, user)
            conn.commit()
            #self.add_activity(f'Updated customer {customer_id}')
            return True
        except Exception:
            conn.rollback()
            return False

    def delete_customer(self, customer_id, user=None):
        # Delete a customer (database only)
        try:
            cursor.execute("EXEC DeleteCustomer ?,?", int(customer_id), user)
            conn.commit()
            #self.add_activity(f'Deleted customer {customer_id}')
            return True
        except Exception:
            conn.rollback()
            return False
    
    def create_sale(self, customer_id, items, user=None):
        # Create a new sale transaction using identity-based SaleID in the DB.
        # Calculate totals
        subtotal = sum(item['quantity'] * item['price'] for item in items)
        # Read settings at call time to avoid KeyError when settings haven't been loaded
        settings = self.get_settings()
        tax_rate = float(settings.get('tax_rate', 0.0))
        tax = (subtotal * tax_rate) / 100
        total = subtotal + tax

        # Pre-check stock availability to avoid the DB stored procedure throwing
        try:
            for item in items:
                med_id = item['medicine_id']
                qty = int(item['quantity'])
                try:
                    cursor.execute("EXEC GetMedicineByID ?", int(med_id))
                    row = cursor.fetchone()
                except Exception:
                    row = None
                if not row:
                    return None, f'Invalid medicine id: {med_id}'
                # GetMedicineByID returns (Name, Category, Quantity, MinimumStock, Price, Status)
                available = int(row[2] or 0)
                if available < qty:
                    return None, f'Insufficient stock for {med_id} (available {available})'
        except Exception:
            pass

        # Persist sale via stored procedures (CreateSale now returns the generated SaleID)
        try:
            conn.autocommit = False

            # Ensure CustomerID is passed as INT or NULL (UI uses string keys)
            cust_param = None
            try:
                if customer_id is not None:
                    cust_param = int(customer_id)
            except Exception:
                cust_param = None

            cursor.execute("EXEC CreateSale ?,?,?,?,?", cust_param, subtotal, tax, total, user)
            row = cursor.fetchone()
            if not row:
                conn.rollback()
                conn.autocommit = True
                return None, 'Failed to create sale header'
            try:
                sale_id = int(row[0])
            except Exception:
                sale_id = row[0]

            # For each sale item: add sale item and update medicine qty (all within one transaction)
            db_errors = False
            last_error = None
            for item in items:
                med_id = item['medicine_id']
                qty = item['quantity']
                price = item.get('price', 0)
                try:
                    # Read current DB medicine row BEFORE subtracting so we have the correct old quantity
                    cursor.execute("EXEC GetMedicineByID ?", int(med_id))
                    mrow_pre = cursor.fetchone()
                    if mrow_pre is not None:
                        db_name = mrow_pre[0] or ''
                        db_cat = mrow_pre[1] or ''
                        db_old = int(mrow_pre[2] or 0)
                        db_min = int(mrow_pre[3] or 0)
                        db_price = float(mrow_pre[4] or 0)
                        db_status = mrow_pre[5] or ''
                    else:
                        db_name = ''
                        db_cat = ''
                        db_old = 0
                        db_min = 0
                        db_price = price
                        db_status = ''

                    # Now add sale item which itself decreases the medicine quantity in the DB
                    # Pass the current user so stock adjustments record who performed the sale
                    cursor.execute("EXEC AddSaleItem ?,?,?,?,?", sale_id, int(med_id), qty, price, user or None)

                    # Compute new quantity based on pre-read value (the stored proc should participate in this transaction)
                    db_new = db_old - qty
                except Exception:
                    db_errors = True
                    try:
                        last_error = str(sys.exc_info()[1])
                    except Exception:
                        last_error = 'Error adding sale item or updating medicine/stock'
                    break

            if db_errors:
                conn.rollback()
                conn.autocommit = True
                return None, (last_error or 'Database error during sale persistence')

            try:
                conn.commit()
            except Exception as e:
                conn.rollback()
                conn.autocommit = True
                return None, f'Database commit failed: {e}'

            # Log activity for the created sale (best-effort; don't break sale flow if logging fails)
            self.add_activity(f'Sale {sale_id} created: {total}', user)


            conn.autocommit = True

            # Sale created successfully in database
            return sale_id, total
        except Exception as e:
            conn.rollback()
            conn.autocommit = True
            return None, str(e)

    def add_return(self, medicine_id, quantity, sale_id=None, customer_id=None, reason='', user=None):
        # Register a returned item in database
        try:
            qty = int(quantity)
            if qty <= 0:
                return None, 'Quantity must be positive'
        except Exception:
            return None, 'Invalid quantity'

        # Get medicine price and current quantity from database
        try:
            cursor.execute("EXEC GetMedicineByID ?", int(medicine_id))
            mrow = cursor.fetchone()
            if mrow is None:
                return None, 'Invalid medicine id'
            # (Name, Category, Quantity, MinimumStock, Price, Status)
            unit_price = float(mrow[4] or 0) if len(mrow) > 4 else 0.0
            old_qty = int(mrow[2] or 0) if len(mrow) > 2 else 0
        except Exception:
            return None, 'Database error retrieving medicine'

        refund_amount = unit_price * qty

        # Re-read current quantity right before creating the return to ensure accurate old_qty
        try:
            try:
                cursor.execute("EXEC GetMedicineByID ?", int(medicine_id))
                mrow_now = cursor.fetchone()
                if mrow_now is not None:
                    old_qty = int(mrow_now[2] or 0) if len(mrow_now) > 2 else old_qty
            except Exception:
                # If re-read fails, proceed with previously read old_qty
                pass
        except Exception:
            pass

        # Create return in database (stored procedure handles stock update and returns the new ReturnID)
        try:
            # Ensure SaleID and CustomerID are passed as INT or NULL (UI may supply string ids)
            sale_param = None
            cust_param = None
            try:
                if sale_id is not None:
                    sale_param = int(sale_id)
            except Exception:
                sale_param = None
            try:
                if customer_id is not None:
                    cust_param = int(customer_id)
            except Exception:
                cust_param = None

            cursor.execute("EXEC AddReturn ?,?,?,?,?,?,?,?", int(medicine_id), qty, unit_price, refund_amount, sale_param, cust_param, reason or '', user)
            row = cursor.fetchone()
            try:
                conn.commit()
            except Exception:
                conn.rollback()

            if row is not None:
                return_id = row[0]
            else:
                # Do not generate a local ReturnID here; require DB to return it.
                return_id = None
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            return None, str(e)

        # Stock adjustment is now recorded by the AddReturn stored procedure.

        #self.add_activity(f'Created return {return_id}', user)

        # Return the DB-provided ID (may be None if DB didn't return one)
        return return_id, None

    def add_activity(self, action, user=None):
        """Record an activity entry in database.
        Returns the LogID (int) when known, otherwise None.
        """
        log_id = None
        # Persist to database
        try:
            cursor.execute("EXEC AddActivityLog ?,?", user or None, action)
            row = cursor.fetchone()
            conn.commit()
            if row is not None:
                try:
                    log_id = int(row[0])
                except Exception:
                    log_id = row[0]
        except Exception:
            conn.rollback()

        # Return log_id (None if DB failed to provide one)

        return log_id
    
    def get_low_stock_medicines(self, threshold=10):
        # Prefer using the database stored procedure which returns low-stock items
        results = {}
        try:
            cursor.execute("EXEC GetLowStockItems")
            rows = cursor.fetchall()
        except Exception:
            rows = None

        # If the stored procedure is not available or fails, fall back to in-Python filter
        if rows is None:
            try:
                medicines = self.get_medicines()
                return {mid: med for mid, med in medicines.items() if med.get('quantity', 0) < threshold}
            except Exception:
                return {}

        for r in rows:
            try:
                mid = str(r[0])
                results[mid] = {
                    'name': r[1] or '',
                    'category': r[2] or '',
                    'quantity': int(r[3] or 0),
                    'price': float(r[5] or 0) if len(r) > 5 else float(r[4] or 0),
                    'minimum_stock': int(r[4] or 0) if len(r) > 4 else 0,
                    'status': 'low stock',
                    'created_date': None
                }
            except Exception:
                # Skip malformed rows
                continue

        return results
    
    def get_today_sales(self):
        # Use stored procedure to fetch today's sales for efficiency
        today_sales = []
        total_amount = 0.0
        try:
            cursor.execute("EXEC GetSalesReport ?", 'today')
            rows = cursor.fetchall()
        except Exception:
            rows = []

        for r in rows:
            try:
                sale = {
                    'sale_id': str(r[0]),
                    'customer_id': str(r[1]) if r[1] is not None else None,
                    'customer_name': r[2] or '',
                    'subtotal': float(r[3]) if len(r) > 3 and r[3] is not None else 0.0,
                    'tax': float(r[4]) if len(r) > 4 and r[4] is not None else 0.0,
                    'total': float(r[5]) if len(r) > 5 and r[5] is not None else 0.0,
                    'timestamp': r[6] if len(r) > 6 else None,
                    'items': []
                }
                total_amount += sale['total']
                today_sales.append(sale)
            except Exception:
                continue

        return today_sales, total_amount

    def get_dashboard_stats(self):
        """Return aggregated values used by the dashboard:
        - total_medicines
        - low_stock (medicines where Quantity < MinimumStock)
        - today_sales_count
        - today_revenue

        Prefer an efficient SQL query; fall back to in-Python computation if the query fails.
        """
        stats = {
            'total_medicines': 0,
            'low_stock': 0,
            'today_sales_count': 0,
            'today_revenue': 0.0
        }

        try:
            # Use stored procedure to fetch dashboard aggregates
            cursor.execute("EXEC GetDashboardStats")
            row = cursor.fetchone()
            if row:
                stats['total_medicines'] = int(row[0] or 0)
                stats['low_stock'] = int(row[1] or 0)
                stats['today_sales_count'] = int(row[2] or 0)
                try:
                    stats['today_revenue'] = float(row[3] or 0.0)
                except Exception:
                    stats['today_revenue'] = 0.0
            return stats
        except Exception:
            # Fall back to existing Python helpers (less efficient)
            try:
                meds = self.get_medicines()
                stats['total_medicines'] = len(meds)
                stats['low_stock'] = len([m for m in meds.values() if int(m.get('quantity', 0)) < int(m.get('minimum_stock', 0) or 0)])
            except Exception:
                stats['total_medicines'] = 0
                stats['low_stock'] = 0

            try:
                today_sales, total_amount = self.get_today_sales()
                stats['today_sales_count'] = len(today_sales)
                stats['today_revenue'] = total_amount
            except Exception:
                stats['today_sales_count'] = 0
                stats['today_revenue'] = 0.0

            return stats
    
    def search_medicines(self, query):
        # Prefer database-backed search procedure when available for efficiency
        results = {}
        try:
            try:
                cursor.execute("EXEC SearchMedicines ?", query or '')
                rows = cursor.fetchall()
            except Exception:
                rows = None

            if rows is None:
                # Fallback to in-Python filter when stored procedure unavailable
                q = (query or '').lower()
                medicines = self.get_medicines()
                for mid, med in medicines.items():
                    try:
                        if (q in med.get('name','').lower() or
                            q in med.get('category','').lower() or
                            q in mid.lower()):
                            results[mid] = med
                    except Exception:
                        continue
                return results

            for r in rows:
                mid_key = str(r[0])
                results[mid_key] = {
                    'name': r[1] or '',
                    'category': r[2] or '',
                    'quantity': int(r[3] or 0),
                    'price': float(r[4] or 0),
                    'minimum_stock': int(r[5] or 0),
                    'status': r[6] or '',
                    'created_date': r[7] if len(r) > 7 else None
                }
            return results
        except Exception:
            # Final fallback to existing Python search
            q = (query or '').lower()
            medicines = self.get_medicines()
            for mid, med in medicines.items():
                try:
                    if (q in med.get('name','').lower() or q in med.get('category','').lower() or q in mid.lower()):
                        results[mid] = med
                except Exception:
                    continue
            return results
    
    def search_customers(self, query):
        # Use DB stored procedure when possible
        results = {}
        try:
            try:
                cursor.execute("EXEC SearchCustomers ?", query or '')
                rows = cursor.fetchall()
            except Exception:
                rows = None

            if rows is None:
                q = (query or '').lower()
                customers = self.get_customers()
                for cid, cust in customers.items():
                    try:
                        if (q in cust.get('name','').lower() or
                            q in cust.get('phone','').lower() or
                            q in cust.get('email','').lower() or
                            q in cid.lower()):
                            results[cid] = cust
                    except Exception:
                        continue
                return results

            for r in rows:
                cid = str(r[0])
                results[cid] = {
                    'name': r[1] or '',
                    'phone': r[2] or '',
                    'email': r[3] or '',
                    'created_date': r[4] if len(r) > 4 else None,
                    'total_purchases': float(r[5] or 0) if len(r) > 5 else 0
                }
            return results
        except Exception:
            # Fallback
            q = (query or '').lower()
            customers = self.get_customers()
            for cid, cust in customers.items():
                try:
                    if (q in cust.get('name','').lower() or q in cust.get('phone','').lower() or q in cust.get('email','').lower() or q in cid.lower()):
                        results[cid] = cust
                except Exception:
                    continue
            return results

    # --- Suppliers management ---
    def add_supplier(self, name, company='', phone='', email='', active=True, supplier_id=None, user=None):
        # Add a new supplier (DB will generate numeric SupplierID via IDENTITY)
        try:
            # Stored procedure signature: AddSupplier @Name, @Company, @Phone, @Email, @Active, @UserName
            cursor.execute("EXEC AddSupplier ?,?,?,?,?,?", name, company or '', phone or '', email or '', 1 if active else 0, user)
            row = cursor.fetchone()
            try:
                conn.commit()
            except Exception:
                conn.rollback()

            if row is not None:
                try:
                    new_id = int(row[0])
                except Exception:
                    new_id = row[0]
            else:
                new_id = None
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            return None

        supplier_key = str(new_id) if new_id is not None else None
        #self.add_activity(f'Added supplier {supplier_key}', user=None)
        return supplier_key

    def record_stock_adjustment(self, medicine_id, old_qty, new_qty, supplier_id=None, reason='', user=None):
        # Record an audit entry for a stock adjustment in database
        adj_id = None
        try:
            try:
                change = int((new_qty or 0) - (old_qty or 0))
            except Exception:
                change = 0

            # Call DB procedure which now returns the generated AdjustmentID
            # Ensure supplier_id is passed as INT or NULL
            supp_param = None
            try:
                if supplier_id is not None:
                    supp_param = int(supplier_id)
            except Exception:
                supp_param = None

            cursor.execute("EXEC AddStockAdjustment ?,?,?,?,?,?,?", int(medicine_id), old_qty, new_qty, change, supp_param, reason or '', user or None)
            row = cursor.fetchone()
            try:
                conn.commit()
            except Exception:
                conn.rollback()

            if row is not None:
                adj_id = row[0]
            # Do not generate local IDs here; force DB to provide the ID.
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            # On error, do not synthesize a local AdjustmentID. Leave adj_id as None.

        # Log stock adjustment
        try:
            delta = int(new_qty - old_qty)
        except Exception:
            delta = 0
        self.add_activity(f'Stock adjustment {adj_id} for {medicine_id} ({delta:+d})', user)

        return str(adj_id)    # --- User management ---
    def _hash_password(self, username, password):
        try:
            return str(password)
        except Exception:
            return None

    def add_user(self, username, full_name, password, role='cashier', active=True, email=None, phone=None):
        # Add a new user with a role (admin/manager/cashier). Password stored hashed.
        uname = str(username).strip()
        if not uname:
            return None
        pwd_hash = self._hash_password(uname, password)

        # Persist to database
        try:
            cursor.execute("EXEC AddUser ?,?,?,?,?,?,?", uname, full_name, pwd_hash, role, 1 if active else 0, email or '', phone or '')
            conn.commit()
        except Exception:
            conn.rollback()
            return None

        #self.add_activity(f'Added user {uname}', user=uname)

        return uname

    def authenticate_user(self, username, password):
        uname = str(username).strip()
        users = self.get_users()
        if uname not in users:
            return False, None
        expected = users[uname].get('password')
        got = self._hash_password(uname, password)
        if expected and got and expected == got:
            return True, users[uname].get('role')
        return False, None

    def update_user(self, username, full_name=None, password=None, role=None, active=None, email=None, phone=None):
        users = self.get_users()
        if username not in users:
            return False
        
        # Prepare values for update
        pwd_hash = self._hash_password(username, password) if password is not None else None
        
        # Update in database
        try:
            cursor.execute("EXEC UpdateUser ?,?,?,?,?,?,?", username, full_name, pwd_hash, role, 1 if active else 0 if active is not None else None, email, phone)
            conn.commit()
        except Exception:
            conn.rollback()
            return False

        #self.add_activity(f'Updated user {username}', user=username)

        return True

    def toggle_user_status(self, username):
        """
        Toggle the active status of a user. Returns (True, new_status) on success,
        or (False, error_message) on failure.
        """
        users = self.get_users()
        if username not in users:
            return False, 'User not found'

        # Toggle in database
        try:
            cursor.execute("EXEC ToggleUserStatus ?", username)
            row = cursor.fetchone()
            conn.commit()
            if row is not None:
                new_active = bool(row[0])
                self.add_activity(f'User {username} status toggled to {"Active" if new_active else "Inactive"}', user=username)
                return True, new_active
            else:
                return False, 'Toggle did not return status'
        except Exception as e:
            conn.rollback()
            return False, str(e)

    def delete_user(self, username):
        users = self.get_users()
        if username in users:
            try:
                cursor.execute("EXEC DeleteUser ?", username)
                conn.commit()
            except Exception:
                conn.rollback()
                return False
            #self.add_activity(f'Deleted user {username}', user=username)
            return True
        return False

    def update_supplier(self, supplier_id, name=None, company=None, phone=None, email=None, active=None, user=None):
        # Update supplier details (supports company and active status)
        suppliers = self.get_suppliers()
        if supplier_id not in suppliers:
            return False
        
        # Get current values
        supplier = suppliers[supplier_id]
        final_name = name if name is not None else supplier.get('name', '')
        final_company = company if company is not None else supplier.get('company', '')
        final_phone = phone if phone is not None else supplier.get('phone', '')
        final_email = email if email is not None else supplier.get('email', '')
        final_active = active if active is not None else supplier.get('active', True)
        
        # Persist to DB via stored procedure
        try:
            cursor.execute("EXEC UpdateSupplier ?,?,?,?,?,?,?", int(supplier_id), final_name, final_company, final_phone, final_email, 1 if final_active else 0, user)
            conn.commit()
        except Exception:
            conn.rollback()
            return False
        
        #self.add_activity(f'Updated supplier {supplier_id}', user=None)
        return True
    
    def delete_supplier(self, supplier_id, user=None):
        # Delete a supplier
        suppliers = self.get_suppliers()
        if supplier_id in suppliers:
            try:
                cursor.execute("EXEC DeleteSupplier ?,?", int(supplier_id), user)
                conn.commit()
            except Exception:
                conn.rollback()
                return False
            #self.add_activity(f'Deleted supplier {supplier_id}', user=None)
            return True
        return False

    def toggle_supplier_status(self, supplier_id, user=None):
        """
        Toggle the active status of a supplier. Returns (True, new_status) on success,
        or (False, error_message) on failure.
        """
        suppliers = self.get_suppliers()
        if supplier_id not in suppliers:
            return False, 'Supplier not found'

        try:
            cursor.execute("EXEC ToggleSupplierStatus ?,?", int(supplier_id), user)
            row = cursor.fetchone()
            conn.commit()
            if row is not None:
                new_active = bool(row[0])
                #self.add_activity(f'Supplier {supplier_id} status toggled to {"Active" if new_active else "Inactive"}', user=None)
                return True, new_active
            else:
                return False, 'Toggle did not return status'
        except Exception as e:
            conn.rollback()
            return False, str(e)

    def search_suppliers(self, query):
        # Use DB-side search when available
        results = {}
        try:
            try:
                cursor.execute("EXEC SearchSuppliers ?", query or '')
                rows = cursor.fetchall()
            except Exception:
                rows = None

            if rows is None:
                q = (query or '').lower()
                suppliers = self.get_suppliers()
                for sid, sup in suppliers.items():
                    try:
                        if (q in sup.get('name','').lower() or
                            q in sup.get('company','').lower() or
                            q in sup.get('phone','').lower() or
                            q in sup.get('email','').lower() or
                            q in sid.lower()):
                            results[sid] = sup
                    except Exception:
                        continue
                return results

            for r in rows:
                sid = str(r[0])
                results[sid] = {
                    'name': r[1] or '',
                    'company': r[2] or '',
                    'phone': r[3] or '',
                    'email': r[4] or '',
                    'active': bool(r[5]) if r[5] is not None else True,
                    'created_date': r[6] if len(r) > 6 else None
                }
            return results
        except Exception:
            q = (query or '').lower()
            suppliers = self.get_suppliers()
            for sid, sup in suppliers.items():
                try:
                    if (q in sup.get('name','').lower() or q in sup.get('company','').lower() or q in sup.get('phone','').lower() or q in sup.get('email','').lower() or q in sid.lower()):
                        results[sid] = sup
                except Exception:
                    continue
            return results

    def search_users(self, query):
        # Search users via DB procedure when available
        results = {}
        try:
            try:
                cursor.execute("EXEC SearchUsers ?", query or '')
                rows = cursor.fetchall()
            except Exception:
                rows = None

            if rows is None:
                q = (query or '').lower()
                users = self.get_users()
                for uname, info in users.items():
                    try:
                        if (q in uname.lower() or q in info.get('full_name','').lower() or q in info.get('email','').lower() or q in info.get('phone','').lower()):
                            results[uname] = info
                    except Exception:
                        continue
                return results

            for r in rows:
                uname = r[0]
                results[uname] = {
                    'full_name': r[1] or '',
                    'password': r[2] or '',
                    'role': r[3] or '',
                    'active': bool(r[4]) if r[4] is not None else True,
                    'email': r[5] or '',
                    'phone': r[6] or ''
                }
            return results
        except Exception:
            q = (query or '').lower()
            users = self.get_users()
            for uname, info in users.items():
                try:
                    if (q in uname.lower() or q in info.get('full_name','').lower() or q in info.get('email','').lower() or q in info.get('phone','').lower()):
                        results[uname] = info
                except Exception:
                    continue
            return results

class PharmacyFrontend:
    def __init__(self, root):
        self.root = root
        self.root.title("Pharmacy Management System")
        # Backend is created early so start-up preferences can be respected
        # (backend initialized below after root setup)

        # Initialize backend early so we can read startup settings
        self.backend = PharmacyBackend()

        # Use configured pharmacy name in the window title
        settings = self.backend.get_settings()
        self.root.title(f"{settings.get('pharmacy_name', 'Pharmacy')} - Pharmacy Management")
        self.current_cart = []

        # Setup styles
        self.setup_styles()

        # Respect startup preference: start_maximized (True/False)
        start_max = bool(settings.get('start_maximized', True))

        self.root.update_idletasks()
        if start_max:
            try:
                self.root.state('zoomed')
            except Exception:
                self.root.attributes('-zoomed', True)
            if sys.platform == 'win32':
                hwnd = self.root.winfo_id()
                ctypes.windll.user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
            
        else:
            # Centered, normal window
            self.center_window(1200, 800)
            self.root.state('normal')
            self.root.resizable(True, True)
        def format_currency(amount):
            cur = self.backend.get_settings().get('currency', 'USD')
            symbol = '$' if str(cur).upper() in ('USD', 'US$', '$') else f"{cur} "
            try:
                return f"{symbol}{float(amount):,.2f}"
            except Exception:
                return f"{symbol}{amount}"

        self.format_currency = format_currency
        # Bind Enter key on entry-like widgets to move focus to the next widget
        def _on_enter_focus(e):
            return self._focus_next(e)
        for cls in ('Entry', 'TEntry', 'Spinbox', 'TSpinbox', 'Combobox', 'TCombobox'):
            self.root.bind_class(cls, '<Return>', _on_enter_focus)
        
        # Show login dialog first; main layout will be created after successful login
        self.current_user = None
        self.current_role = None
        self.show_login_dialog()
    
    def setup_styles(self):
        # Configure styles for the application
        style = ttk.Style()
        # Try to use a modern theme on Windows, fall back silently if unavailable
        style.theme_use('clam')

        # Typography and color palette for a professional look
        style.configure('Title.TLabel', font=('Segoe UI', 18, 'bold'), foreground='#1f4b8f')
        style.configure('Header.TLabel', font=('Segoe UI', 12, 'bold'))
        style.configure('Card.TFrame', relief='raised', borderwidth=1, background='#f7f9fc')
        style.configure('TFrame', background='#f7f9fc')
        style.configure('TLabel', background='#f7f9fc')
        style.configure('TButton', padding=6)
        style.configure('Primary.TButton', background='#1f4b8f', foreground='white')
        style.map('Primary.TButton', background=[('active', '#163d6b')])
        style.configure('Success.TButton', foreground='#0a7a07')
        style.configure('Danger.TButton', foreground='white', background='#d9534f')
        style.map('Danger.TButton', background=[('active', '#c9302c')])
        # Save variations: green for Save & New, blue for Save & Close
        style.configure('SaveNew.TButton', background='#28a745', foreground='white')
        style.map('SaveNew.TButton', background=[('active', '#1e7e34')])
        style.configure('SaveClose.TButton', background='#007bff', foreground='white')
        style.map('SaveClose.TButton', background=[('active', '#0056b3')])
    
    def create_main_layout(self):
        # Create the main application layout
        # Header
        header_frame = ttk.Frame(self.root, padding="10")
        header_frame.pack(fill='x')
        
        ph_settings = self.backend.get_settings()
        ttk.Label(header_frame, text=ph_settings.get('pharmacy_name', 'Pharmacy').upper(), style='Title.TLabel').pack(side='left')
        
        # Navigation
        nav_frame = ttk.Frame(self.root)
        nav_frame.pack(fill='x', padx=10, pady=5)
        
        # Adjust navigation per-role. Cashiers have limited access.
        role = getattr(self, 'current_role', None)

        # Dashboard should be available to all roles
        ttk.Button(nav_frame, text="Dashboard", command=self.show_dashboard).pack(side='left', padx=5)
        # Core views available to everyone (medicines, sales, returns)
        ttk.Button(nav_frame, text="Medicines", command=self.show_medicines).pack(side='left', padx=5)
        ttk.Button(nav_frame, text="Sales", command=self.show_sales).pack(side='left', padx=5)
        ttk.Button(nav_frame, text="Returns", command=self.show_returns).pack(side='left', padx=5)

        # Activity Log quick access
        ttk.Button(nav_frame, text="Activity Log", command=self.show_activity_log).pack(side='left', padx=5)

        # Additional views for non-cashier roles
        if role != 'cashier':
            ttk.Button(nav_frame, text="Stock Management", command=self.show_stock_management).pack(side='left', padx=5)
            ttk.Button(nav_frame, text="Customers", command=self.show_customers).pack(side='left', padx=5)
            ttk.Button(nav_frame, text="Suppliers", command=self.show_suppliers).pack(side='left', padx=5)
            ttk.Button(nav_frame, text="Reports", command=self.show_reports).pack(side='left', padx=5)
        # Settings button (admin-only). Create as attribute so we can show/hide it.
        self.settings_btn = ttk.Button(nav_frame, text="Settings", command=self.show_settings)
        # Only pack the Settings button if the current user is admin (when known)
        if getattr(self, 'current_role', None) == 'admin':
            self.settings_btn.pack(side='left', padx=5)
        # Users management (admin only) - we'll show/hide based on role
        self.users_btn = ttk.Button(nav_frame, text="Users", command=self.show_users)
        if getattr(self, 'current_role', None) == 'admin':
            self.users_btn.pack(side='left', padx=5)
        ttk.Button(nav_frame, text="Logout", command=self.logout).pack(side='right', padx=5)
        ttk.Button(nav_frame, text="Exit", command=self.confirm_exit, style='Danger.TButton').pack(side='right', padx=5)
        
        # Main content area
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill='both', expand=True, padx=10, pady=10)

    def amount_to_words(self, amount: float) -> str:
        # Convert a numeric amount to words (supports dollars and cents style).
        # This is a simple implementation intended for receipt display.
        def _int_to_words(n):
            ones = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine']
            teens = ['Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen']
            tens = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']

            if n == 0:
                return 'Zero'
            if n < 10:
                return ones[n]
            if n < 20:
                return teens[n-10]
            if n < 100:
                t = tens[n // 10]
                o = ones[n % 10]
                return (t + (' ' + o if o else '')).strip()
            if n < 1000:
                h = ones[n // 100] + ' Hundred'
                rest = n % 100
                return (h + (' ' + _int_to_words(rest) if rest else '')).strip()
            for idx, word in enumerate(['Thousand', 'Million', 'Billion'], 1):
                unit = 1000 ** idx
                if n < unit * 1000:
                    high = n // unit
                    rest = n % unit
                    return (_int_to_words(high) + ' ' + word + ((' ' + _int_to_words(rest)) if rest else '')).strip()
            return str(n)

        try:
            whole = int(amount)
            cents = int(round((abs(amount) - abs(whole)) * 100))
        except Exception:
            return ''

        words = _int_to_words(abs(whole))
        if cents:
            words = f"{words} and {cents}/100"
        if amount < 0:
            words = 'Minus ' + words
        return words

    def center_window(self, width, height):
        # Center the main window on screen with given width and height
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _focus_next(self, event):
        # Move focus to the next widget when Enter is pressed on entry-like controls
        nxt = event.widget.tk_focusNext()
        if nxt:
            nxt.focus_set()
            # If the next widget supports selection (Entry), select its text for quick overwrite
            try:
                nxt.selection_range(0, 'end')
            except (AttributeError, tk.TclError):
                pass  # Widget doesn't support selection
        # Prevent default handling
        return "break"
    
    def clear_main_frame(self):
        # Clear the main content area
        for widget in self.main_frame.winfo_children():
            widget.destroy()
    
    def show_dashboard(self):
        # Display dashboard screen
        self.clear_main_frame()
        
        stats = self.backend.get_dashboard_stats()
        total_medicines = stats.get('total_medicines', 0)
        low_stock = stats.get('low_stock', 0)
        total_today_sales = stats.get('today_sales_count', 0)
        today_revenue = stats.get('today_revenue', 0.0)
        
        # Statistics cards
        stats_frame = ttk.Frame(self.main_frame)
        stats_frame.pack(fill='x', pady=10)
        
        # Card 1: Total Medicines
        card1 = ttk.Frame(stats_frame, style='Card.TFrame', padding="10")
        card1.pack(side='left', padx=5, expand=True, fill='both')
        ttk.Label(card1, text="Total Medicines", style='Header.TLabel').pack()
        ttk.Label(card1, text=str(total_medicines), font=('Arial', 24, 'bold'), foreground='blue').pack(pady=5)
        
        # Card 2: Low Stock
        card2 = ttk.Frame(stats_frame, style='Card.TFrame', padding="10")
        card2.pack(side='left', padx=5, expand=True, fill='both')
        ttk.Label(card2, text="Low Stock", style='Header.TLabel').pack()
        ttk.Label(card2, text=str(low_stock), font=('Arial', 24, 'bold'), foreground='red').pack(pady=5)
        
        # Card 3: Today's Sales
        card3 = ttk.Frame(stats_frame, style='Card.TFrame', padding="10")
        card3.pack(side='left', padx=5, expand=True, fill='both')
        ttk.Label(card3, text="Today's Sales", style='Header.TLabel').pack()
        ttk.Label(card3, text=str(total_today_sales), font=('Arial', 24, 'bold'), foreground='green').pack(pady=5)
        
        # Card 4: Today's Revenue
        card4 = ttk.Frame(stats_frame, style='Card.TFrame', padding="10")
        card4.pack(side='left', padx=5, expand=True, fill='both')
        ttk.Label(card4, text="Today's Revenue", style='Header.TLabel').pack()
        ttk.Label(card4, text=self.format_currency(today_revenue), font=('Segoe UI', 24, 'bold'), foreground='purple').pack(pady=5)
        
        # Quick actions
        actions_frame = ttk.Frame(self.main_frame)
        actions_frame.pack(fill='x', pady=20)
        
        ttk.Label(actions_frame, text="Quick Actions", style='Header.TLabel').pack()
        
        button_frame = ttk.Frame(actions_frame)
        button_frame.pack(pady=10)
        
        ttk.Button(button_frame, text="New Sale", command=self.show_sales).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Manage Medicines", command=self.show_medicines).pack(side='left', padx=5)
        ttk.Button(button_frame, text="View Reports", command=self.show_reports).pack(side='left', padx=5)
        
        # Recent sales
        recent_frame = ttk.Frame(self.main_frame)
        recent_frame.pack(fill='both', expand=True, pady=10)
        
        ttk.Label(recent_frame, text="Recent Sales", style='Header.TLabel').pack(anchor='w')
        
        # Create treeview for recent sales
        columns = ('Sale ID', 'Customer', 'Items', 'Total', 'Time')
        tree = ttk.Treeview(recent_frame, columns=columns, show='headings', height=8)
        
        # Define headings
        tree.heading('Sale ID', text='Sale ID')
        tree.heading('Customer', text='Customer')
        tree.heading('Items', text='Items')
        tree.heading('Total', text='Total')
        tree.heading('Time', text='Time')
        
        tree.pack(fill='both', expand=True, pady=5)
        
        # Load sales via stored procedures (no inline SELECT)
        recent_sales = []
        try:
            try:
                cursor.execute("EXEC GetAllSales")
                rows = cursor.fetchall()
            except Exception:
                rows = []

            sales_map = {}
            for r in rows:
                sid = r[0]
                sid_key = str(sid)
                sales_map[sid_key] = {
                    'customer_id': str(r[1]) if r[1] is not None else None,
                    'customer_name': r[2] or '',
                    'items': [],
                    'subtotal': float(r[3] or 0),
                    'tax': float(r[4] or 0),
                    'total': float(r[5] or 0),
                    'timestamp': r[6] if len(r) > 6 else None,
                    'user_fullname': r[7] if len(r) > 7 else None
                }

            # Populate items via stored procedure
            try:
                cursor.execute("EXEC GetAllSaleDetails")
                detail_rows = cursor.fetchall()
            except Exception:
                detail_rows = []

            for dr in detail_rows:
                sid = dr[0]
                sid_key = str(sid)
                if sid_key in sales_map:
                    if len(dr) >= 4:
                        mid = dr[1]
                        mname = dr[2] if len(dr) >= 3 else ''
                        qty = int(dr[3] or 0)
                        sales_map[sid_key]['items'].append({'medicine_id': str(mid), 'medicine_name': mname, 'quantity': qty})
                    else:
                        mid = dr[1]
                        qty = int(dr[2] or 0)
                        sales_map[sid_key]['items'].append({'medicine_id': str(mid), 'medicine_name': '', 'quantity': qty})

            recent_sales = sorted(sales_map.items(), key=lambda x: x[1].get('timestamp', datetime.min), reverse=True)
        except Exception:
            recent_sales = []

        for sale_id, sale in recent_sales:
            customer_name = sale.get('customer_name') or 'Walk-in'
            if not sale.get('customer_name') and sale.get('customer_id'):
                customers = self.backend.get_customers()
                if sale.get('customer_id') in customers:
                    customer_name = customers[sale.get('customer_id')]['name']

            try:
                items_text = ", ".join([f"{it.get('quantity',0)}x {it.get('medicine_name') or it.get('medicine_id','')}" for it in sale.get('items', [])])
            except Exception:
                items_text = ''

            tree.insert('', 'end', values=(
                sale_id,
                customer_name,
                items_text,
                self.format_currency(sale.get('total', 0)),
                sale.get('timestamp').strftime("%H:%M") if sale.get('timestamp') else ''
            ))
    
    def show_stock_management(self):
        # Display stock management screen with stock in/out functionality
        self.clear_main_frame()
        
        # Header
        header_frame = ttk.Frame(self.main_frame)
        header_frame.pack(fill='x', pady=10)
        ttk.Label(header_frame, text="STOCK MANAGEMENT", style='Title.TLabel').pack()
        
        # Stock In/Out Form
        form_frame = ttk.LabelFrame(self.main_frame, text="Stock Movement", padding="10")
        form_frame.pack(fill='x', pady=10, padx=5)
        form_frame.columnconfigure(1, weight=1)
        
        # Medicine selection
        ttk.Label(form_frame, text="Medicine:").grid(row=0, column=0, sticky='w', pady=5, padx=5)
        self.stock_med_var = tk.StringVar()
        self.stock_med_combo = ttk.Combobox(form_frame, textvariable=self.stock_med_var, state='readonly', width=40)
        self.stock_med_combo.grid(row=0, column=1, sticky='ew', pady=5, padx=5)
        
        # Movement type
        ttk.Label(form_frame, text="Type:").grid(row=0, column=2, sticky='w', pady=5, padx=5)
        self.stock_type_var = tk.StringVar(value='in')
        type_frame = ttk.Frame(form_frame)
        type_frame.grid(row=0, column=3, sticky='w', pady=5, padx=5)
        ttk.Radiobutton(type_frame, text='Stock In', variable=self.stock_type_var, value='in').pack(side='left', padx=3)
        ttk.Radiobutton(type_frame, text='Stock Out', variable=self.stock_type_var, value='out').pack(side='left', padx=3)
        
        # Quantity
        ttk.Label(form_frame, text="Quantity:").grid(row=1, column=0, sticky='w', pady=5, padx=5)
        self.stock_qty_var = tk.StringVar(value='1')
        ttk.Spinbox(form_frame, textvariable=self.stock_qty_var, from_=1, to=10000, width=15).grid(row=1, column=1, sticky='w', pady=5, padx=5)
        
        # Supplier (for stock in)
        ttk.Label(form_frame, text="Supplier:").grid(row=1, column=2, sticky='w', pady=5, padx=5)
        self.stock_supplier_var = tk.StringVar()
        self.stock_supplier_combo = ttk.Combobox(form_frame, textvariable=self.stock_supplier_var, state='readonly', width=25)
        self.stock_supplier_combo.grid(row=1, column=3, sticky='ew', pady=5, padx=5)
        
        # Reason
        ttk.Label(form_frame, text="Reason/Note:").grid(row=2, column=0, sticky='w', pady=5, padx=5)
        self.stock_reason_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.stock_reason_var, width=50).grid(row=2, column=1, columnspan=3, sticky='ew', pady=5, padx=5)
        
        # Action button
        ttk.Button(form_frame, text="Process Stock Movement", command=self.process_stock_movement, style='Primary.TButton').grid(row=3, column=0, columnspan=4, pady=10)
        
        # Stock Adjustments History
        history_frame = ttk.LabelFrame(self.main_frame, text="Stock Movement History", padding="5")
        history_frame.pack(fill='both', expand=True, pady=10, padx=5)
        
        # Filters
        filter_frame = ttk.Frame(history_frame)
        filter_frame.pack(fill='x', pady=5)
        
        ttk.Label(filter_frame, text="Filter by Medicine:").pack(side='left', padx=5)
        self.history_search_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.history_search_var, width=30).pack(side='left', padx=5)
        # Auto-refresh history when the search box is cleared
        try:
            self.history_search_var.trace_add('write', lambda *a: self.refresh_stock_history() if not (self.history_search_var.get() or '').strip() else None)
        except Exception:
            self.history_search_var.trace('w', lambda *a: self.refresh_stock_history() if not (self.history_search_var.get() or '').strip() else None)
        ttk.Button(filter_frame, text="Search", command=self.filter_stock_history).pack(side='left', padx=5)
        ttk.Button(filter_frame, text="Show All", command=self.refresh_stock_history).pack(side='left', padx=5)
        
        # History table
        table_frame = ttk.Frame(history_frame)
        table_frame.pack(fill='both', expand=True, pady=5)
        
        columns = ('ID', 'Medicine', 'Type', 'Old Qty', 'New Qty', 'Change', 'Supplier', 'Reason', 'User', 'Date')
        self.stock_history_tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=12)
        
        for col in columns:
            self.stock_history_tree.heading(col, text=col)
        
        self.stock_history_tree.column('ID', width=70)
        self.stock_history_tree.column('Medicine', width=150)
        self.stock_history_tree.column('Type', width=70)
        self.stock_history_tree.column('Old Qty', width=70)
        self.stock_history_tree.column('New Qty', width=70)
        self.stock_history_tree.column('Change', width=70)
        self.stock_history_tree.column('Supplier', width=100)
        self.stock_history_tree.column('Reason', width=200)
        self.stock_history_tree.column('User', width=100)
        self.stock_history_tree.column('Date', width=150)
        
        scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=self.stock_history_tree.yview)
        self.stock_history_tree.configure(yscrollcommand=scrollbar.set)
        
        self.stock_history_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Load data
        self.refresh_stock_medicines_list()
        self.refresh_stock_suppliers_list()
        self.refresh_stock_history()
    
    def refresh_stock_medicines_list(self):
        if not hasattr(self, 'stock_med_combo'):
            return
        try:
            if not self.stock_med_combo.winfo_exists():
                return
        except:
            return

        meds = []
        for mid, med in self.backend.get_medicines().items():
            meds.append(f"{mid}: {med.get('name','')} (Current: {med.get('quantity',0)})")
        try:
            self.stock_med_combo['values'] = meds
            if meds:
                self.stock_med_combo.set(meds[0])
        except Exception:
            # If the underlying Tcl widget is gone or updating fails, ignore safely
            return
    
    def refresh_stock_suppliers_list(self):
        if not hasattr(self, 'stock_supplier_combo'):
            return
        try:
            if not self.stock_supplier_combo.winfo_exists():
                return
        except:
            return

        suppliers = ['']
        for sid, sup in self.backend.get_suppliers().items():
            if sup.get('active', True):
                suppliers.append(f"{sid}: {sup.get('name','')}")
        try:
            self.stock_supplier_combo['values'] = suppliers
            self.stock_supplier_combo.set('')
        except Exception:
            return
    
    def process_stock_movement(self):
        # Process stock in or stock out transaction
        med_sel = self.stock_med_var.get()
        if not med_sel:
            messagebox.showerror('Error', 'Please select a medicine')
            return
        
        med_id = med_sel.split(':')[0]
        
        try:
            qty = int(self.stock_qty_var.get())
            if qty <= 0:
                raise ValueError()
        except:
            messagebox.showerror('Error', 'Please enter a valid quantity')
            return
        
        medicines = self.backend.get_medicines()
        if med_id not in medicines:
            messagebox.showerror('Error', 'Invalid medicine selected')
            return
        med = medicines[med_id]
        old_qty = int(med.get('quantity', 0))
        movement_type = self.stock_type_var.get()
        
        # Calculate new quantity
        if movement_type == 'in':
            new_qty = old_qty + qty
        else:  # stock out
            new_qty = old_qty - qty
            if new_qty < 0:
                messagebox.showerror('Error', f'Insufficient stock. Current quantity: {old_qty}')
                return
        
        # Get supplier if provided
        sup_sel = self.stock_supplier_var.get().strip()
        sup_id = None
        if sup_sel:
            try:
                sup_id_raw = sup_sel.split(':')[0]
                sup_id = int(sup_id_raw)
            except Exception:
                sup_id = None
        
        reason = self.stock_reason_var.get().strip()
        if not reason:
            reason = f'Stock {movement_type.upper()}'
        
        # Update stock (pass current user so stored procedure can log activity)
        success = self.backend.update_medicine(med_id, quantity=new_qty, user=getattr(self, 'current_user', None))
        if success:
            # The DB `UpdateMedicine` stored procedure creates the stock adjustment
            # and activity log when quantity changes. Avoid duplicating that here.
            messagebox.showinfo('Success', 
                f'Stock {movement_type.upper()} processed successfully!\n'
                f'Medicine: {med.get("name")}\n'
                f'Old Quantity: {old_qty}\n'
                f'New Quantity: {new_qty}\n'
                f'Change: {new_qty - old_qty:+d}')
            
            # Clear form
            self.stock_qty_var.set('1')
            self.stock_reason_var.set('')
            self.stock_supplier_var.set('')
            
            # Refresh displays
            self.refresh_stock_medicines_list()
            self.refresh_stock_history()
            
            # Also refresh other stock views if visible
            if hasattr(self, 'stock_tree'):
                self.refresh_stock()
            if hasattr(self, 'medicines_tree'):
                self.refresh_medicines()
        else:
            messagebox.showerror('Error', 'Failed to update stock')
    
    def refresh_stock_history(self):
        # Guard: widget may have been destroyed if the view changed while a
        # background callback is running (common when dialogs close). Check
        # attribute existence and that the underlying Tcl widget still exists
        # before attempting tree operations.
        if not hasattr(self, 'stock_history_tree'):
            return
        try:
            if not self.stock_history_tree.winfo_exists():
                return
        except Exception:
            return

        adjustments = sorted(self.backend.get_stock_adjustments().items(),
                             key=lambda x: x[1].get('timestamp', datetime.min),
                             reverse=True)
        self._populate_stock_history_tree(adjustments)

    def _populate_stock_history_tree(self, adjustments, filter_query: str | None = None):
        # Defensive checks: ensure the tree attribute exists and the underlying
        # Tcl widget is still valid. Protect against `_tkinter.TclError` when the
        # widget has been destroyed elsewhere (e.g., user changed views).
        if not hasattr(self, 'stock_history_tree'):
            return
        try:
            if not self.stock_history_tree.winfo_exists():
                return
        except Exception:
            return

        try:
            for item in self.stock_history_tree.get_children():
                self.stock_history_tree.delete(item)
        except tk.TclError:
            # The widget no longer exists at the Tcl level; nothing to do.
            return

        for adj_id, adj in adjustments:
            med_id = adj.get('medicine_id')
            medicines = self.backend.get_medicines()
            med_name = medicines.get(med_id, {}).get('name', med_id)
            # Prefer the medicine_name provided by the detailed view when available
            if adj.get('medicine_name'):
                med_name = adj.get('medicine_name')

            # Apply optional filter
            if filter_query:
                q = filter_query.lower()
                if q not in med_name.lower() and q not in med_id.lower():
                    continue

            old_qty = adj.get('old_quantity', 0)
            new_qty = adj.get('new_quantity', 0)
            # Best-effort change calculation
            change = int(adj.get('change', (new_qty or 0) - (old_qty or 0)))

            reason = adj.get('reason', '')
            # Derive movement type from reason/change
            if 'Sale:' in reason or 'sale' in reason.lower():
                movement_type = 'SALE'
            elif change > 0:
                movement_type = 'IN'
            elif change < 0:
                movement_type = 'OUT'
            else:
                movement_type = 'ADJ'

            # Prefer supplier_name from the detailed view when available
            sup_name = adj.get('supplier_name') or ''
            if not sup_name:
                sup_id = adj.get('supplier_id', '')
                suppliers = self.backend.get_suppliers()
                if sup_id and sup_id in suppliers:
                    sup_name = suppliers[sup_id].get('name', sup_id)

            timestamp = adj.get('timestamp')
            date_str = timestamp.strftime('%Y-%m-%d %H:%M:%S') if timestamp else ''

            tags = ()
            if movement_type == 'IN':
                tags = ('stock_in',)
            elif movement_type == 'OUT' or movement_type == 'SALE':
                tags = ('stock_out',)

            self.stock_history_tree.insert('', 'end', values=(
                adj_id,
                med_name,
                movement_type,
                old_qty,
                new_qty,
                f'{change:+d}',
                sup_name,
                adj.get('reason', ''),
                adj.get('user', ''),
                date_str
            ), tags=tags)

        # Configure tags for visual feedback (do once). Wrap in try/except in
        # case the tree was destroyed while populating.
        try:
            self.stock_history_tree.tag_configure('stock_in', background='#d4edda')
            self.stock_history_tree.tag_configure('stock_out', background='#f8d7da')
        except tk.TclError:
            return
    
    def filter_stock_history(self):
        if not hasattr(self, 'stock_history_tree') or not hasattr(self, 'history_search_var'):
            return

        query = self.history_search_var.get().strip().lower()
        if not query:
            self.refresh_stock_history()
            return

        adjustments = sorted(self.backend.get_stock_adjustments().items(),
                             key=lambda x: x[1].get('timestamp', datetime.min),
                             reverse=True)
        self._populate_stock_history_tree(adjustments, filter_query=query)


    def show_medicines(self):
        self.clear_main_frame()

        header_frame = ttk.Frame(self.main_frame)
        header_frame.pack(fill='x', pady=10)
        ttk.Label(header_frame, text="MEDICINES", style='Title.TLabel').pack()

        toolbar = ttk.Frame(self.main_frame)
        toolbar.pack(fill='x', pady=10)

        # Action buttons: hide management actions for cashiers (read-only)
        role = getattr(self, 'current_role', None)

        if role != 'cashier':
            ttk.Button(toolbar, text="Add New Medicine", command=self.show_add_medicine_dialog).pack(side='left', padx=5)
            ttk.Button(toolbar, text="Edit Selected", command=self.edit_selected_medicine).pack(side='left', padx=5)
            ttk.Button(toolbar, text="Delete Selected", command=self.delete_selected_medicine).pack(side='left', padx=5)
        else:
            # Provide a subtle hint that this view is read-only for cashiers
            ttk.Label(toolbar, text="(Read-only)").pack(side='left', padx=8)

        # Search box on the right
        ttk.Label(toolbar, text="Search:").pack(side='right', padx=5)
        self.meds_search_var = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.meds_search_var, width=30).pack(side='right', padx=5)
        # Auto-refresh medicines list when search box is cleared
        try:
            self.meds_search_var.trace_add('write', lambda *a: self.refresh_medicines() if not (self.meds_search_var.get() or '').strip() else None)
        except Exception:
            self.meds_search_var.trace('w', lambda *a: self.refresh_medicines() if not (self.meds_search_var.get() or '').strip() else None)
        ttk.Button(toolbar, text="Search", command=self.search_medicines_in_medicines_tab).pack(side='right', padx=5)

        # Medicines table
        table_frame = ttk.Frame(self.main_frame)
        table_frame.pack(fill='both', expand=True, pady=10)
        columns = ('ID', 'Name', 'Category', 'Supplier', 'Quantity', 'Min Stock', 'Price', 'Created')
        self.medicines_tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=15)

        for col in columns:
            self.medicines_tree.heading(col, text=col)

        self.medicines_tree.column('ID', width=80)
        self.medicines_tree.column('Name', width=180)
        self.medicines_tree.column('Category', width=120)
        self.medicines_tree.column('Supplier', width=140)
        self.medicines_tree.column('Quantity', width=80)
        self.medicines_tree.column('Min Stock', width=90)
        self.medicines_tree.column('Price', width=100)
        self.medicines_tree.column('Created', width=120)

        scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=self.medicines_tree.yview)
        self.medicines_tree.configure(yscrollcommand=scrollbar.set)
        self.medicines_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # Bind click for possible row actions
        self.medicines_tree.bind('<ButtonRelease-1>', self.on_medicines_click)

        # Load medicines
        self.refresh_medicines()
    
    def refresh_stock(self):
        if not hasattr(self, 'stock_tree'):
            return
        try:
            for item in self.stock_tree.get_children():
                self.stock_tree.delete(item)

            for med_id, medicine in self.backend.get_medicines().items():
                tags = () if int(medicine.get('quantity', 0)) >= 10 else ('low_stock',)

                self.stock_tree.insert('', 'end', values=(
                    med_id,
                    medicine.get('name', ''),
                    medicine.get('category', ''),
                    medicine.get('quantity', 0),
                    self.format_currency(medicine.get('price', 0))
                ), tags=tags)

            self.stock_tree.tag_configure('low_stock', background='#ffcccc')

            medicines = self.backend.get_medicines()
            total_value = sum(float(med.get('quantity', 0)) * float(med.get('price', 0)) for med in medicines.values())
            total_items = sum(int(med.get('quantity', 0)) for med in medicines.values())

            if hasattr(self, 'stock_total_label'):
                self.stock_total_label.config(text=f"Total Stock Value: {self.format_currency(total_value)}")

            if hasattr(self, 'stock_count_label'):
                self.stock_count_label.config(text=f"Total Items: {total_items}")

            self.root.update_idletasks()
        except tk.TclError:
            return

    def refresh_medicines(self):
        if not hasattr(self, 'medicines_tree'):
            return
        try:
            for item in self.medicines_tree.get_children():
                self.medicines_tree.delete(item)

            # Insert current medicines
            for med_id, medicine in self.backend.get_medicines().items():
                created = medicine.get('created_date')
                created_str = created.strftime('%Y-%m-%d') if created else ''
                tags = ()
                qty = int(medicine.get('quantity', 0) or 0)
                min_st = int(medicine.get('minimum_stock', 0) or 0)
                if min_st > 0 and qty < min_st:
                    tags = ('low_stock',)

                self.medicines_tree.insert('', 'end', values=(
                    med_id,
                    medicine.get('name', ''),
                    medicine.get('category', ''),
                    medicine.get('supplier_name', ''),
                    medicine.get('quantity', 0),
                    medicine.get('minimum_stock', 0),
                    self.format_currency(medicine.get('price', 0)),
                    created_str
                ), tags=tags)

            self.medicines_tree.tag_configure('low_stock', background='#ffcccc')

            self.root.update_idletasks()
        except tk.TclError:
            return

    def on_medicines_click(self, event):
        if not hasattr(self, 'medicines_tree'):
            return

        sel = self.medicines_tree.selection()
        if not sel:
            return

        item = sel[0]
        column = self.medicines_tree.identify_column(event.x)
        values = self.medicines_tree.item(item, 'values')

        # Prevent actions when clicking on ID or Created columns (now column #1 or #8)
        if column == '#1' or column == '#8':
            return
    


    def search_medicines_in_medicines_tab(self):
        if not hasattr(self, 'meds_search_var') or not hasattr(self, 'medicines_tree'):
            return

        query = self.meds_search_var.get()
        if not query:
            self.refresh_medicines()
            return

        results = self.backend.search_medicines(query)

        for item in self.medicines_tree.get_children():
            self.medicines_tree.delete(item)

        for med_id, medicine in results.items():
            created = medicine.get('created_date')
            created_str = created.strftime('%Y-%m-%d') if created else ''
            min_stock = medicine.get('minimum_stock', 0)
            self.medicines_tree.insert('', 'end', values=(
                med_id,
                medicine['name'],
                medicine['category'],
                medicine.get('supplier_name',''),
                medicine['quantity'],
                min_stock,
                self.format_currency(medicine['price']),
                created_str
            ))
    
    def show_add_medicine_dialog(self):
        # Show dialog to add new medicine
        self.medicine_dialog("Add New Medicine")
    
    def show_edit_medicine_dialog(self, medicine_id):
        # Show dialog to edit existing medicine
        self.medicine_dialog("Edit Medicine", medicine_id)

    def edit_selected_medicine(self):
        med_id = None
        if hasattr(self, 'medicines_tree'):
            sel = self.medicines_tree.selection()
            if sel:
                med_id = self.medicines_tree.item(sel[0], 'values')[0]

        if not med_id and hasattr(self, 'stock_tree'):
            sel = self.stock_tree.selection()
            if sel:
                med_id = self.stock_tree.item(sel[0], 'values')[0]

        if not med_id:
            messagebox.showerror("Error", "Please select a medicine to edit")
            return

        self.show_edit_medicine_dialog(med_id)

    def delete_selected_medicine(self):
        med_id = None
        if hasattr(self, 'medicines_tree'):
            sel = self.medicines_tree.selection()
            if sel:
                med_id = self.medicines_tree.item(sel[0], 'values')[0]

        if not med_id and hasattr(self, 'stock_tree'):
            sel = self.stock_tree.selection()
            if sel:
                med_id = self.stock_tree.item(sel[0], 'values')[0]

        if not med_id:
            messagebox.showerror("Error", "Please select a medicine to delete")
            return

        # Reuse existing delete_medicine (it shows confirm dialog)
        self.delete_medicine(med_id)
    
    def medicine_dialog(self, title, medicine_id=None):
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("600x380")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text=title, style='Title.TLabel').pack(pady=10)
        
        # Form fields
        form_frame = ttk.Frame(dialog)
        form_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        # Name
        ttk.Label(form_frame, text="Medicine Name:").grid(row=0, column=0, sticky='w', pady=5)
        name_var = tk.StringVar()
        name_entry = ttk.Entry(form_frame, textvariable=name_var, width=30)
        name_entry.grid(row=0, column=1, sticky='ew', pady=5, padx=5)
        
        # Category
        ttk.Label(form_frame, text="Category:").grid(row=1, column=0, sticky='w', pady=5)
        category_var = tk.StringVar()
        category_combo = ttk.Combobox(form_frame, textvariable=category_var, values=["Tablet", "Capsule", "Syrup", "Injection", "Ointment", "Drops"])
        category_combo.grid(row=1, column=1, sticky='ew', pady=5, padx=5)
        
        # Quantity
        ttk.Label(form_frame, text="Quantity:").grid(row=2, column=0, sticky='w', pady=5)
        quantity_var = tk.StringVar()
        quantity_entry = ttk.Entry(form_frame, textvariable=quantity_var, width=30)
        quantity_entry.grid(row=2, column=1, sticky='ew', pady=5, padx=5)
        
        # Price
        ttk.Label(form_frame, text="Price:").grid(row=3, column=0, sticky='w', pady=5)
        price_var = tk.StringVar()
        price_entry = ttk.Entry(form_frame, textvariable=price_var, width=30)
        price_entry.grid(row=3, column=1, sticky='ew', pady=5, padx=5)
        
        # Minimum Stock
        ttk.Label(form_frame, text="Minimum Stock:").grid(row=4, column=0, sticky='w', pady=5)
        min_stock_var = tk.StringVar()
        min_stock_entry = ttk.Entry(form_frame, textvariable=min_stock_var, width=30)
        min_stock_entry.grid(row=4, column=1, sticky='ew', pady=5, padx=5)

        # Supplier (show name only in UI; keep a small mapping name->id for lookup)
        ttk.Label(form_frame, text="Supplier:").grid(row=5, column=0, sticky='w', pady=5)
        supplier_var = tk.StringVar()
        supplier_combo = ttk.Combobox(form_frame, textvariable=supplier_var, state='readonly', width=28)
        supplier_combo.grid(row=5, column=1, sticky='ew', pady=5, padx=5)
        # Populate suppliers list with names only and keep mapping to IDs
        supplier_names = ['']
        supplier_map = {}
        for sid, sup in self.backend.get_suppliers().items():
            if sup.get('active', True):
                name = sup.get('name','')
                supplier_names.append(name)
                # If multiple suppliers share the same name, last one wins — acceptable for most setups
                supplier_map[name] = sid
        try:
            supplier_combo['values'] = supplier_names
        except Exception:
            pass
        
        medicines = self.backend.get_medicines()
        if medicine_id and medicine_id in medicines:
            medicine = medicines[medicine_id]
            name_var.set(medicine['name'])
            category_var.set(medicine['category'])
            quantity_var.set(str(medicine['quantity']))
            price_var.set(str(medicine['price']))
            min_stock_var.set(str(medicine.get('minimum_stock', 10)))
            # Set supplier if present (show name only)
            s_id = medicine.get('supplier_id')
            s_name = medicine.get('supplier_name')
            if s_name:
                try:
                    supplier_combo.set(s_name)
                except Exception:
                    supplier_combo.set(s_name or '')
        else:
            min_stock_var.set('10')
        
        def save_medicine(close_after=True):
            name = name_var.get().strip()
            category = category_var.get().strip()
            quantity = quantity_var.get().strip()
            price = price_var.get().strip()
            
            # Validation
            if not name:
                messagebox.showerror("Error", "Medicine name is required")
                return
            
            try:
                quantity = int(quantity)
                if quantity < 0:
                    messagebox.showerror("Error", "Quantity cannot be negative")
                    return
            except ValueError:
                messagebox.showerror("Error", "Quantity must be a valid number")
                return
            
            try:
                price = float(price)
                if price <= 0:
                    messagebox.showerror("Error", "Price must be positive")
                    return
            except ValueError:
                messagebox.showerror("Error", "Price must be a valid number")
                return

            # Minimum stock validation
            min_stock = 10
            try:
                min_stock = int(min_stock_var.get().strip())
                if min_stock < 0:
                    messagebox.showerror("Error", "Minimum stock cannot be negative")
                    return
            except Exception:
                messagebox.showerror("Error", "Minimum stock must be a valid integer")
                return
            
            # Save medicine
            new_med_id = None
            # Determine selected supplier id (map selected name back to id)
            sup_sel = supplier_var.get().strip()
            sup_id = None
            if sup_sel:
                try:
                    sup_id_raw = supplier_map.get(sup_sel)
                    sup_id = int(sup_id_raw) if sup_id_raw is not None else None
                except Exception:
                    sup_id = None

            if medicine_id:
                # Update existing (pass minimum_stock). Record adjustment if quantity changed.
                success = self.backend.update_medicine(
                    medicine_id,
                    name=name,
                    category=category,
                    quantity=quantity,
                    price=price,
                    minimum_stock=min_stock,
                    supplier_id=sup_id,
                    user=getattr(self, 'current_user', None),
                    # update_medicine currently accepts supplier via DB proc so ensure it's passed
                    # Note: update_medicine signature on backend uses user as last param; we updated it to include supplier internally
                    
                    # (we pass supplier via backend by temporarily using update_medicine's DB read path)
                    
                    record_adjustment=False,
                    reason=f'Edit via Medicines dialog: {medicine_id}'
                )
                if success:
                    # Show status after update
                    medicines = self.backend.get_medicines()
                    status = medicines[medicine_id].get('status', 'ok') if medicine_id in medicines else 'ok'
                    messagebox.showinfo("Success", f"Medicine updated successfully (Status: {status})")
                else:
                    messagebox.showerror("Error", "Failed to update medicine")
            else:
                # Add new (include minimum_stock) — pass current user so stock history records who added it
                new_med_id = self.backend.add_medicine(name, category, quantity, price, medicine_id=None, minimum_stock=min_stock, supplier_id=sup_id, user=getattr(self, 'current_user', None))
                if new_med_id:
                    medicines = self.backend.get_medicines()
                    status = medicines[new_med_id].get('status', 'ok') if new_med_id in medicines else 'ok'
                    messagebox.showinfo("Success", f"Medicine added successfully (Status: {status})")
                else:
                    messagebox.showerror("Error", "Failed to add medicine")

            # Close dialog if requested
            if close_after:
                dialog.destroy()

            # Update visible tables immediately for better UX
            try:
                if not medicine_id:
                    # Instead of inserting a single row manually (which can miss
                    # sort/filter state or leave inconsistent UI), refresh the
                    # full medicines and stock views so the UI accurately
                    # reflects the database after the add.
                    if hasattr(self, 'medicines_tree'):
                        try:
                            self.refresh_medicines()
                        except Exception:
                            pass

                    if hasattr(self, 'stock_tree'):
                        try:
                            self.refresh_stock()
                        except Exception:
                            pass

                else:
                    # For edits, refresh rows to reflect updates
                    if hasattr(self, 'medicines_tree'):
                        self.refresh_medicines()
                    if hasattr(self, 'stock_tree'):
                        self.refresh_stock()
            except Exception:
                pass  # If direct insert fails, tables will refresh on next view

            # Refresh sales medicines list if present
            if hasattr(self, 'sales_med_combo'):
                self.refresh_sales_medicines()

            # Also refresh stock medicine dropdown and history so the new medicine
            # appears in the Stock Adjustment view immediately (if visible)
            if hasattr(self, 'refresh_stock_medicines_list'):
                self.refresh_stock_medicines_list()
            if hasattr(self, 'refresh_stock_history'):
                self.refresh_stock_history()
        
        # Buttons: different for add vs edit
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill='x', pady=10)

        if medicine_id:
            # Edit mode: single primary Save and Cancel
            ttk.Button(button_frame, text="Save", command=lambda: save_medicine(close_after=True), style='Primary.TButton').pack(side='left', padx=8)
            ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side='left', padx=8)
        else:
            def _save_and_new():
                save_medicine(close_after=False)
                # Clear form for next entry
                name_var.set('')
                category_var.set('')
                quantity_var.set('')
                price_var.set('')
                name_entry.focus_set()

            def _save_and_close():
                save_medicine(close_after=True)

            ttk.Button(button_frame, text="Save & New", command=_save_and_new, style='SaveNew.TButton').pack(side='left', padx=8)
            ttk.Button(button_frame, text="Save & Close", command=_save_and_close, style='SaveClose.TButton').pack(side='left', padx=8)
            ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side='left', padx=8)
    
    def delete_medicine(self, medicine_id):
        medicines = self.backend.get_medicines()
        medicine_name = medicines[medicine_id]['name'] if medicine_id in medicines else 'Unknown'
        confirm = messagebox.askyesno("Confirm Delete", 
                                    f"Are you sure you want to delete {medicine_name}?")
        
        if confirm:
            success = self.backend.delete_medicine(medicine_id, user=getattr(self, 'current_user', None))
            if success:
                messagebox.showinfo("Success", "Medicine deleted successfully")
                self.refresh_stock()
                if hasattr(self, 'medicines_tree'):
                    self.refresh_medicines()
                if hasattr(self, 'sales_med_combo'):
                    self.refresh_sales_medicines()
            else:
                messagebox.showerror("Error", "Failed to delete medicine")
    
    def show_sales(self):
        self.clear_main_frame()
        
        header_frame = ttk.Frame(self.main_frame)
        header_frame.pack(fill='x', pady=10)
        ttk.Label(header_frame, text="POINT OF SALE", style='Title.TLabel').pack()
        
        # Customer section
        customer_frame = ttk.Frame(self.main_frame)
        customer_frame.pack(fill='x', pady=5)
        
        ttk.Label(customer_frame, text="Customer:").pack(side='left', padx=5)
        self.customer_var = tk.StringVar()
        customer_combo = ttk.Combobox(customer_frame, textvariable=self.customer_var, state="readonly", width=20)
        customer_combo.pack(side='left', padx=5)
        
        # Populate customers
        customer_options = ["Walk-in Customer"]
        for cust_id, customer in self.backend.get_customers().items():
            customer_options.append(f"{cust_id}: {customer['name']}")
        customer_combo['values'] = customer_options
        customer_combo.set("Walk-in Customer")
        
        # Main POS layout
        pos_frame = ttk.Frame(self.main_frame)
        pos_frame.pack(fill='both', expand=True, pady=10)
        
        # Left side - Product selection
        left_frame = ttk.Frame(pos_frame)
        left_frame.pack(side='left', fill='both', expand=True, padx=5)
        
        ttk.Label(left_frame, text="Add Product", style='Header.TLabel').pack()
        
        product_frame = ttk.Frame(left_frame)
        product_frame.pack(fill='x', pady=5)
        
        ttk.Label(product_frame, text="Medicine:").pack(anchor='w')
        # Search + selection: allow searching medicines and selecting from combobox
        search_frame = ttk.Frame(product_frame)
        search_frame.pack(fill='x', pady=2)
        ttk.Label(search_frame, text="Search:").pack(side='left')
        self.med_search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.med_search_var)
        search_entry.pack(side='left', fill='x', expand=True, padx=4)
        # Auto-refresh sales medicines when search cleared
        try:
            self.med_search_var.trace_add('write', lambda *a: self.refresh_sales_medicines() if not (self.med_search_var.get() or '').strip() else None)
        except Exception:
            self.med_search_var.trace('w', lambda *a: self.refresh_sales_medicines() if not (self.med_search_var.get() or '').strip() else None)
        ttk.Button(search_frame, text="Search", command=lambda: self.search_sales_medicines()).pack(side='left', padx=4)
        ttk.Button(search_frame, text="Clear", command=lambda: (self.med_search_var.set(''), self.refresh_sales_medicines())).pack(side='left')

        self.med_var = tk.StringVar()
        self.sales_med_combo = ttk.Combobox(product_frame, textvariable=self.med_var, state="readonly")
        self.sales_med_combo.pack(fill='x', pady=2)
        # Populate combobox with available medicines
        self.refresh_sales_medicines()
        
        ttk.Label(product_frame, text="Quantity:").pack(anchor='w')
        self.qty_var = tk.StringVar(value="1")
        qty_spinbox = ttk.Spinbox(product_frame, textvariable=self.qty_var, from_=1, to=100, width=10)
        qty_spinbox.pack(fill='x', pady=2)
        
        ttk.Button(product_frame, text="Add to Cart", command=self.add_to_cart).pack(pady=10)
        
        # Right side - Cart
        right_frame = ttk.Frame(pos_frame)
        right_frame.pack(side='right', fill='both', expand=True, padx=5)
        
        ttk.Label(right_frame, text="Current Sale", style='Header.TLabel').pack()
        
        # Cart display
        cart_tree_frame = ttk.Frame(right_frame)
        cart_tree_frame.pack(fill='both', expand=True, pady=5)
        
        columns = ('Product', 'Qty', 'Price', 'Total')
        self.cart_tree = ttk.Treeview(cart_tree_frame, columns=columns, show='headings', height=10)
        
        for col in columns:
            self.cart_tree.heading(col, text=col)
            self.cart_tree.column(col, width=80)
        
        scrollbar = ttk.Scrollbar(cart_tree_frame, orient='vertical', command=self.cart_tree.yview)
        self.cart_tree.configure(yscrollcommand=scrollbar.set)
        
        self.cart_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Total section
        total_frame = ttk.Frame(right_frame)
        total_frame.pack(fill='x', pady=5)
        
        self.subtotal_label = ttk.Label(total_frame, text=f"Subtotal: {self.format_currency(0)}", style='Header.TLabel')
        self.subtotal_label.pack()
        
        self.tax_label = ttk.Label(total_frame, text=f"Tax: {self.format_currency(0)}")
        self.tax_label.pack()
        
        self.total_label = ttk.Label(total_frame, text=f"Total: {self.format_currency(0)}", style='Header.TLabel')
        self.total_label.pack()
        
        # Action buttons
        button_frame = ttk.Frame(right_frame)
        button_frame.pack(fill='x', pady=10)
        
        ttk.Button(button_frame, text="Process Payment", command=self.process_payment).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Clear Cart", command=self.clear_cart).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Remove Selected", command=self.remove_from_cart).pack(side='left', padx=5)
    
    def refresh_sales_medicines(self):
        medicines_list = []
        query = None
        # If a search box exists and has text, use it to filter results
        try:
            if hasattr(self, 'med_search_var'):
                q = (self.med_search_var.get() or '').strip()
                if q:
                    query = q.lower()
        except Exception:
            query = None

        for med_id, medicine in self.backend.get_medicines().items():
            if medicine['quantity'] > 0:
                label = f"{med_id}: {medicine['name']} ({self.format_currency(medicine['price'])})"
                if query:
                    if query in medicine.get('name','').lower() or query in med_id.lower():
                        medicines_list.append(label)
                else:
                    medicines_list.append(label)
        if not hasattr(self, 'sales_med_combo'):
            return
        try:
            if not self.sales_med_combo.winfo_exists():
                return
        except Exception:
            return

        try:
            self.sales_med_combo['values'] = medicines_list
            if medicines_list:
                self.sales_med_combo.set(medicines_list[0])
            else:
                # Clear selection if no matches
                try:
                    self.sales_med_combo.set('')
                except Exception:
                    pass
        except Exception:
            return

    def search_sales_medicines(self):
        # Triggered by the Search button: refresh medicines list using search text
        try:
            self.refresh_sales_medicines()
        except Exception:
            pass

    # --- Returns UI ---
    def show_returns(self):
        # Display returns management screen: process returns and view history.
        self.clear_main_frame()

        ttk.Label(self.main_frame, text="RETURNS", style='Title.TLabel').pack(pady=10)

        toolbar = ttk.Frame(self.main_frame)
        toolbar.pack(fill='x', pady=6)

        # Sale selector (required) - choose the sale to return from
        ttk.Label(toolbar, text='Sale:').pack(side='left', padx=6)
        self.return_sale_var = tk.StringVar()
        self.return_sale_combo = ttk.Combobox(toolbar, textvariable=self.return_sale_var, state='readonly', width=22)
        self.return_sale_combo.pack(side='left', padx=6)

        # Medicine selector (populated from selected sale)
        ttk.Label(toolbar, text="Medicine:").pack(side='left', padx=(12,6))
        self.returns_med_var = tk.StringVar()
        self.returns_med_combo = ttk.Combobox(toolbar, textvariable=self.returns_med_var, state='readonly', width=38)
        self.returns_med_combo.pack(side='left', padx=6)

        # Quantity
        ttk.Label(toolbar, text='Qty:').pack(side='left', padx=(12,4))
        self.return_qty_var = tk.StringVar(value='1')
        self.return_qty_spin = ttk.Spinbox(toolbar, textvariable=self.return_qty_var, from_=1, to=1000, width=6)
        self.return_qty_spin.pack(side='left', padx=4)

        # Reason
        ttk.Label(toolbar, text='Reason:').pack(side='left', padx=(12,4))
        self.return_reason_var = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.return_reason_var, width=24).pack(side='left', padx=4)

        ttk.Button(toolbar, text='Process Return', command=self.process_return, style='Primary.TButton').pack(side='right', padx=6)

        # Returns table
        table_frame = ttk.Frame(self.main_frame)
        table_frame.pack(fill='both', expand=True, pady=10)

        columns = ('ID', 'Medicine', 'Qty', 'Amount', 'Sale ID', 'Customer', 'Time', 'Reason')
        self.returns_tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=12)
        for col in columns:
            self.returns_tree.heading(col, text=col)

        scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=self.returns_tree.yview)
        self.returns_tree.configure(yscrollcommand=scrollbar.set)
        self.returns_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # Populate selectors and table
        self._refresh_returns_sales_list()
        # medicine list will be populated when a sale is selected
        self.return_sale_combo.bind('<<ComboboxSelected>>', lambda e: self._on_return_sale_selected())
        self.returns_med_combo.bind('<<ComboboxSelected>>', lambda e: self._update_return_qty_limit())
        # initialize medicine list (will be overridden when a sale is chosen)
        self._refresh_returns_medicine_list()
        self.refresh_returns()

    def _refresh_returns_medicine_list(self):
        meds = []
        for mid, med in self.backend.get_medicines().items():
            meds.append(f"{mid}: {med.get('name','')} (Stock: {med.get('quantity',0)})")
        self.returns_med_combo['values'] = meds
        if meds:
            self.returns_med_combo.set(meds[0])

    def _refresh_returns_sales_list(self):
        # Only include sales that still have refundable items (remaining qty > 0)
        sales = ['']
        for sid, sale in self.backend.get_sales().items():
            items = sale.get('items', [])
            has_remaining = any((it.get('quantity', 0) > 0) for it in items)
            if has_remaining:
                sales.append(sid)
        self.return_sale_combo['values'] = sales

    def _on_return_sale_selected(self):
        # Populate medicine selector from the selected sale and limit qty.
        sale_id = self.return_sale_var.get()
        meds = []
        sales = self.backend.get_sales()
        if sale_id and sale_id in sales:
            sale = sales[sale_id]
            medicines = self.backend.get_medicines()
            for it in sale.get('items', []):
                mid = it.get('medicine_id')
                qty_remaining = int(it.get('quantity', 0) or 0)
                if qty_remaining <= 0:
                    continue
                name = medicines.get(mid, {}).get('name', mid)
                meds.append(f"{mid}: {name} (Remaining: {qty_remaining})")
        self.returns_med_combo['values'] = meds
        if meds:
            self.returns_med_combo.set(meds[0])
            # Set spinbox max to first item's remaining quantity
            try:
                rem = int(meds[0].split('Remaining:')[-1].strip().strip(')'))
            except Exception:
                rem = 1
            self.return_qty_spin.config(to=rem)
            self.return_qty_var.set('1')
        else:
            self.returns_med_combo.set('')
            self.return_qty_spin.config(to=1000)
            self.return_qty_var.set('1')

    def _update_return_qty_limit(self):
        # Update the spinbox `to` value based on selected medicine's remaining qty.
        med_sel = self.returns_med_var.get()
        if not med_sel:
            return
        try:
            # Expect format: "<id>: <name> (Remaining: N)"
            rem = int(med_sel.split('Remaining:')[-1].strip().strip(')'))
            self.return_qty_spin.config(to=rem)
            if int(self.return_qty_var.get()) > rem:
                self.return_qty_var.set(str(rem))
        except (ValueError, IndexError):
            pass  # Invalid format, keep default limit

    def process_return(self):
        med_sel = self.returns_med_var.get()
        if not med_sel:
            messagebox.showerror('Error', 'Please select a medicine to return')
            return
        med_id = med_sel.split(':')[0]
        try:
            qty = int(self.return_qty_var.get())
            if qty <= 0:
                raise ValueError()
        except Exception:
            messagebox.showerror('Error', 'Enter a valid return quantity')
            return

        sale_id = self.return_sale_var.get()
        if not sale_id:
            messagebox.showerror('Error', 'Please select the Sale to return from')
            return
        reason = self.return_reason_var.get().strip()

        return_id, err = self.backend.add_return(med_id, qty, sale_id=sale_id, reason=reason, user=getattr(self, 'current_user', None))
        if err:
            messagebox.showerror('Error', f'Return failed: {err}')
            return

        returns = self.backend.get_returns()
        refund_amount = returns[return_id]["amount"] if return_id in returns else 0
        messagebox.showinfo('Success', f'Return processed: {return_id}\nRefund: {self.format_currency(refund_amount)}')
        # Refresh views
        self.refresh_returns()
        if hasattr(self, 'stock_tree'):
            self.refresh_stock()
            # Also refresh stock movement history so the return adjustment appears
            if hasattr(self, 'refresh_stock_history'):
                self.refresh_stock_history()
        if hasattr(self, 'medicines_tree'):
            self.refresh_medicines()
        # Update sale-specific selectors and sales list so UI reflects change immediately
        # Re-populate medicines for the currently selected sale (may clear if sale exhausted)
        self._on_return_sale_selected()
        # Refresh the sales dropdown to remove sales with no refundable items
        self._refresh_returns_sales_list()
        # If current sale was removed from the values, clear selection
        vals = list(self.return_sale_combo['values'])
        if self.return_sale_var.get() not in vals:
            self.return_sale_var.set('')

    def refresh_returns(self):
        if not hasattr(self, 'returns_tree'):
            return
        for item in self.returns_tree.get_children():
            self.returns_tree.delete(item)
        medicines = self.backend.get_medicines()
        for rid, info in self.backend.get_returns().items():
            # Prefer names returned by the detailed view
            mid = info.get('medicine_id')
            med_name = info.get('medicine_name') or medicines.get(mid, {}).get('name', mid)
            cust = info.get('customer_name') or (info.get('customer_id') or '')
            sale = info.get('sale_id') or ''
            t = info.get('timestamp')
            tstr = t.strftime('%Y-%m-%d %H:%M') if t else ''
            self.returns_tree.insert('', 'end', values=(
                rid,
                med_name,
                info.get('quantity'),
                self.format_currency(info.get('amount', 0)),
                sale,
                cust,
                tstr,
                info.get('reason','')
            ))
    
    def add_to_cart(self):
        # Add selected medicine to cart
        med_selection = self.med_var.get()
        if not med_selection:
            messagebox.showerror("Error", "Please select a medicine")
            return
        
        try:
            quantity = int(self.qty_var.get())
            if quantity <= 0:
                messagebox.showerror("Error", "Quantity must be positive")
                return
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid quantity")
            return
        
        # Extract medicine ID from selection
        med_id = med_selection.split(":")[0]
        
        medicines = self.backend.get_medicines()
        if med_id not in medicines:
            messagebox.showerror("Error", "Invalid medicine selection")
            return
        
        medicine = medicines[med_id]
        
        # Check stock
        if medicine['quantity'] < quantity:
            messagebox.showerror("Error", f"Not enough stock. Only {medicine['quantity']} available")
            return
        
        # If the medicine is already in the cart, increase its quantity instead of adding a duplicate row
        existing = None
        for it in self.current_cart:
            if it.get('medicine_id') == med_id:
                existing = it
                break

        if existing:
            new_qty = existing['quantity'] + quantity
            # Check stock for the combined quantity
            if medicine['quantity'] < new_qty:
                messagebox.showerror("Error", f"Not enough stock. Only {medicine['quantity']} available in total")
                return
            existing['quantity'] = new_qty
            existing['total'] = new_qty * existing['price']
        else:
            cart_item = {
                'medicine_id': med_id,
                'name': medicine['name'],
                'quantity': quantity,
                'price': medicine['price'],
                'total': quantity * medicine['price']
            }
            self.current_cart.append(cart_item)
        self.update_cart_display()
    
    def update_cart_display(self):
        # Update the cart display
        # Clear current display
        for item in self.cart_tree.get_children():
            self.cart_tree.delete(item)
        
        # Add items to display
        for item in self.current_cart:
            self.cart_tree.insert('', 'end', values=(
                item['name'],
                item['quantity'],
                self.format_currency(item['price']),
                self.format_currency(item['total'])
            ))
        
        # Update totals
        subtotal = sum(item['total'] for item in self.current_cart)
        tax = (subtotal * float(self.backend.get_settings().get('tax_rate', 0))) / 100
        total = subtotal + tax
        
        self.subtotal_label.config(text=f"Subtotal: {self.format_currency(subtotal)}")
        self.tax_label.config(text=f"Tax: {self.format_currency(tax)}")
        self.total_label.config(text=f"Total: {self.format_currency(total)}")
    
    def remove_from_cart(self):
        # Remove selected item from cart
        selection = self.cart_tree.selection()
        if not selection:
            messagebox.showerror("Error", "Please select an item to remove")
            return
        
        for item in selection:
            index = self.cart_tree.index(item)
            if 0 <= index < len(self.current_cart):
                self.current_cart.pop(index)
            self.cart_tree.delete(item)
        
        self.update_cart_display()
    
    def clear_cart(self):
        # Clear the entire cart
        self.current_cart.clear()
        for item in self.cart_tree.get_children():
            self.cart_tree.delete(item)
        self.update_cart_display()
    
    def process_payment(self):
        # Process the payment for current cart
        if not self.current_cart:
            messagebox.showerror("Error", "Cart is empty")
            return
        
        # Get customer ID
        customer_selection = self.customer_var.get()
        if customer_selection == "Walk-in Customer":
            customer_id = None
        else:
            customer_id = customer_selection.split(":")[0]
        
        # Prepare items for backend
        items = []
        for item in self.current_cart:
            items.append({
                'medicine_id': item['medicine_id'],
                'quantity': item['quantity'],
                'price': item['price']
            })
        
        # Create sale
        sale_id, total = self.backend.create_sale(customer_id, items, user=self.current_user)

        # If sale failed, show error and abort receipt display
        if sale_id is None:
            messagebox.showerror('Sale Error', f'Failed to create sale: {total}')
            return

        # Build and show a nicely formatted receipt in a dialog
        receipt = tk.Toplevel(self.root)
        receipt.title("Receipt")
        receipt.geometry("600x700")
        receipt.transient(self.root)
        receipt.grab_set()

        # Use monospace font so columns align
        mono = tkfont.Font(family='Courier New', size=10)

        txt = tk.Text(receipt, wrap='none', font=mono)
        txt.pack(fill='both', expand=True, padx=10, pady=10)

        # Header
        s = self.backend.get_settings()
        pharmacy = s.get('pharmacy_name', 'Pharmacy')
        address = s.get('address', '')
        phone = s.get('phone', '')
        tax_rate = s.get('tax_rate', 0)

        now = datetime.now()
        # Prefer customer name from the freshly created sale (detailed view), else fall back to selection lookup
        customer_name = 'Walk-in'
        try:
            sales_info = self.backend.get_sales()
            sale_key = str(sale_id)
            if sale_id and sale_key in sales_info:
                customer_name = sales_info[sale_key].get('customer_name') or customer_name
        except Exception:
            # fallback to previous lookup
            customers = self.backend.get_customers()
            if customer_id and customer_id in customers:
                customer_name = customers[customer_id]['name']

        lines = []
        lines.append(pharmacy.center(56))
        if address:
            lines.append(address.center(56))
        if phone:
            lines.append(f"Phone: {phone}".center(56))
        lines.append("" )
        lines.append(f"Invoice: {sale_id}  Date: {now.strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"Customer: {customer_name}")
        lines.append("-" * 56)

        # Items header
        header_fmt = "{:<30}{:>6}{:>12}{:>12}"
        lines.append(header_fmt.format('Item', 'Qty', 'Unit', 'Total'))
        lines.append("-" * 56)

        subtotal = 0
        for item in self.current_cart:
            name = item['name']
            qty = item['quantity']
            unit = item['price']
            line_total = item['total']
            subtotal += line_total
            # Truncate item name if long
            display_name = (name[:27] + '...') if len(name) > 30 else name
            lines.append(header_fmt.format(display_name, str(qty), self.format_currency(unit), self.format_currency(line_total)))

        lines.append("-" * 56)
        tax = (subtotal * tax_rate) / 100
        lines.append(f"{'Subtotal:':>44} {self.format_currency(subtotal):>12}")
        lines.append(f"{'Tax (' + str(tax_rate) + '%):':>44} {self.format_currency(tax):>12}")
        lines.append(f"{'Total:':>44} {self.format_currency(total):>12}")
        # Amount in words
        words = self.amount_to_words(total)
        if words:
            lines.append(f"Amount (in words): {words}")
        lines.append("-" * 56)
        lines.append("Thank you for your purchase!".center(56))

        receipt_text = "\n".join(lines)
        txt.insert(tk.END, receipt_text)
        txt.config(state='disabled')

        # Buttons: Copy, Save, Close
        def save_receipt_to_file():
            try:
                default_name = f"receipt_{sale_id}.txt"
                path = filedialog.asksaveasfilename(defaultextension='.txt', initialfile=default_name,
                                                    filetypes=[('Text Files', '*.txt'), ('All Files', '*.*')])
                if not path:
                    return
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(receipt_text)
                messagebox.showinfo('Saved', f'Receipt saved to {path}')
            except Exception as e:
                messagebox.showerror('Error', f'Failed to save receipt: {e}')

        btn_frame = ttk.Frame(receipt)
        btn_frame.pack(pady=6)
        ttk.Button(btn_frame, text="Copy Receipt", command=lambda: self.copy_to_clipboard(receipt_text)).pack(side='left', padx=6)
        ttk.Button(btn_frame, text="Save Receipt", command=save_receipt_to_file).pack(side='left', padx=6)
        ttk.Button(btn_frame, text="Close", command=receipt.destroy).pack(side='left', padx=6)

        # Clear cart and refresh
        self.clear_cart()
        self.refresh_sales_medicines()

    def copy_to_clipboard(self, text):
        # Copy provided text to the system clipboard and notify the user
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("Copied", "Receipt copied to clipboard")
    
    def show_customers(self):
        # Display customers management screen
        self.clear_main_frame()

        ttk.Label(self.main_frame, text="CUSTOMER MANAGEMENT", style='Title.TLabel').pack(pady=10)

        # Toolbar with actions and search
        toolbar = ttk.Frame(self.main_frame)
        toolbar.pack(fill='x', pady=5)

        ttk.Button(toolbar, text="Add New Customer", command=self.show_add_customer_dialog).pack(side='left', padx=4)
        ttk.Button(toolbar, text="Edit Selected", command=self.edit_selected_customer).pack(side='left', padx=4)
        ttk.Button(toolbar, text="Delete Selected", command=self.delete_selected_customer).pack(side='left', padx=4)

        # Search box for customers
        ttk.Label(toolbar, text="Search:").pack(side='right', padx=5)
        self.customers_search_var = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.customers_search_var, width=30).pack(side='right', padx=5)
        # Auto-refresh customers list when search box is cleared
        try:
            self.customers_search_var.trace_add('write', lambda *a: self.refresh_customers() if not (self.customers_search_var.get() or '').strip() else None)
        except Exception:
            self.customers_search_var.trace('w', lambda *a: self.refresh_customers() if not (self.customers_search_var.get() or '').strip() else None)
        ttk.Button(toolbar, text="Search", command=self.search_customers).pack(side='right', padx=5)

        # Customers table
        table_frame = ttk.Frame(self.main_frame)
        table_frame.pack(fill='both', expand=True, pady=10)

        columns = ('ID', 'Name', 'Phone', 'Email', 'Total Purchases')
        self.customers_tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=12)

        for col in columns:
            self.customers_tree.heading(col, text=col)

        scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=self.customers_tree.yview)
        self.customers_tree.configure(yscrollcommand=scrollbar.set)

        self.customers_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # Load customers into table
        self.refresh_customers()
    
    def show_add_customer_dialog(self):
        # Show dialog to add new customer
        dialog = tk.Toplevel(self.root)
        dialog.title("Add New Customer")
        dialog.geometry("400x250")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Add New Customer", style='Title.TLabel').pack(pady=10)

        form_frame = ttk.Frame(dialog)
        form_frame.pack(fill='both', expand=True, padx=20, pady=10)

        ttk.Label(form_frame, text="Name:").grid(row=0, column=0, sticky='w', pady=5)
        name_var = tk.StringVar()
        name_entry = ttk.Entry(form_frame, textvariable=name_var, width=30)
        name_entry.grid(row=0, column=1, sticky='ew', pady=5, padx=5)

        ttk.Label(form_frame, text="Phone:").grid(row=1, column=0, sticky='w', pady=5)
        phone_var = tk.StringVar()
        phone_entry = ttk.Entry(form_frame, textvariable=phone_var, width=30)
        phone_entry.grid(row=1, column=1, sticky='ew', pady=5, padx=5)

        ttk.Label(form_frame, text="Email:").grid(row=2, column=0, sticky='w', pady=5)
        email_var = tk.StringVar()
        email_entry = ttk.Entry(form_frame, textvariable=email_var, width=30)
        email_entry.grid(row=2, column=1, sticky='ew', pady=5, padx=5)

        def save_customer(close_after=True):
            name = name_var.get().strip()
            phone = phone_var.get().strip()
            email = email_var.get().strip()

            if not name:
                messagebox.showerror("Error", "Customer name is required")
                return

            new_cid = self.backend.add_customer(name, phone, email, user=getattr(self, 'current_user', None))
            if not new_cid:
                messagebox.showerror("Error", "Failed to add customer. Check database or logs.")
                return
            messagebox.showinfo("Success", "Customer added successfully")

            # Refresh customers list if it's visible
            if hasattr(self, 'customers_tree'):
                self.refresh_customers()

            if close_after:
                dialog.destroy()
            else:
                # Clear fields and focus first entry for fast data entry
                name_var.set('')
                phone_var.set('')
                email_var.set('')
                name_entry.focus_set()

        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill='x', pady=10)

        # Save & New, Save & Close actions
        ttk.Button(button_frame, text="Save & New", command=lambda: save_customer(close_after=False), style='SaveNew.TButton').pack(side='left', padx=6)
        ttk.Button(button_frame, text="Save & Close", command=lambda: save_customer(close_after=True), style='SaveClose.TButton').pack(side='left', padx=6)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side='left', padx=6)

    # --- Authentication UI ---
    def show_login_dialog(self):
        # Display a full-window, modern login page (centered card).
        # Clear any existing widgets on root and prepare a clean canvas
        for w in self.root.winfo_children():
            w.destroy()

        # Respect user's startup preference: only maximize if configured
        settings = self.backend.get_settings()
        start_max = bool(settings.get('start_maximized', True))
        self.root.update_idletasks()
        if start_max:
            try:
                self.root.state('zoomed')
            except Exception:
                self.root.attributes('-zoomed', True)

        self.login_frame = ttk.Frame(self.root)
        self.login_frame.pack(fill='both', expand=True)

        # Subtle background band to give depth
        top_band = ttk.Frame(self.login_frame, height=140, style='TFrame')
        top_band.pack(fill='x')

        # Center container (give it an explicit size so the card isn't tiny on large screens)
        container = ttk.Frame(self.login_frame)
        # Make the container sizable so the card fills a reasonable area instead of being very small
        # Increased height per user request so the card appears taller on large displays
        container.place(relx=0.5, rely=0.5, anchor='center', width=720, height=640)

        # Card frame (visual card) with padding; pack to fill the container
        card = ttk.Frame(container, style='Card.TFrame', padding=20)
        card.pack(fill='both', expand=True, padx=8, pady=8)
        card.columnconfigure(0, weight=1)

        # Logo and Title row
        logo_row = ttk.Frame(card, style='Card.TFrame')
        logo_row.grid(row=0, column=0, sticky='ew', pady=(0,8))
        # Simple textual logo: first letter inside a circle-like label
        pharm_name = str(self.backend.get_settings().get('pharmacy_name', 'Pharmacy'))
        logo_text = pharm_name[:1].upper()
        logo = tk.Canvas(logo_row, width=56, height=56, highlightthickness=0, bg='#f7f9fc')
        # Draw a circle and place initial
        logo.create_oval(4, 4, 52, 52, fill='#1f4b8f', outline='')
        logo.create_text(28, 30, text=logo_text, fill='white', font=('Segoe UI', 18, 'bold'))
        logo.pack(side='left')

        title_frame = ttk.Frame(logo_row, style='Card.TFrame')
        title_frame.pack(side='left', padx=12)
        # Larger title for the expanded card
        ttk.Label(title_frame, text=pharm_name, font=('Segoe UI', 22, 'bold')).pack(anchor='w', pady=(0,4))
        ttk.Label(title_frame, text='Sign in to continue', font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=(0,2))
        ttk.Label(title_frame, text='Enter your credentials to access the system', foreground='#666666', font=('Segoe UI', 10)).pack(anchor='w')

        # Form (give it more vertical breathing room)
        form = ttk.Frame(card, style='Card.TFrame')
        form.grid(row=1, column=0, sticky='ew', pady=(12,12))
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text='Username:').grid(row=0, column=0, sticky='w', padx=6, pady=8)
        user_var = tk.StringVar()
        user_entry = ttk.Entry(form, textvariable=user_var, font=('Segoe UI', 11))
        user_entry.grid(row=0, column=1, padx=6, pady=8, sticky='ew')

        ttk.Label(form, text='Password:').grid(row=1, column=0, sticky='w', padx=6, pady=8)
        pass_var = tk.StringVar()
        pass_entry = ttk.Entry(form, textvariable=pass_var, show='*', font=('Segoe UI', 11))
        pass_entry.grid(row=1, column=1, padx=6, pady=8, sticky='ew')

        # Show password toggle + Remember me
        opts = ttk.Frame(form)
        opts.grid(row=2, column=1, sticky='w', padx=6, pady=(0,6))
        show_var = tk.BooleanVar(value=False)
        def toggle_show():
            pass_entry.config(show='' if show_var.get() else '*')
        ttk.Checkbutton(opts, text='Show password', variable=show_var, command=toggle_show).pack(side='left')
        remember_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text='Remember me', variable=remember_var).pack(side='left', padx=8)

        # Error label (inline, unobtrusive)
        error_label = ttk.Label(card, text='', foreground='#d9534f')
        error_label.grid(row=2, column=0, sticky='w', pady=(2,0))

        # Buttons (more prominent)
        # Allow card to give some vertical space so buttons don't stick to the form
        card.rowconfigure(1, weight=1)
        btns = ttk.Frame(card)
        btns.grid(row=3, column=0, sticky='e', pady=(18,12))

        def do_login(event=None):
            username = user_var.get().strip()
            password = pass_var.get()
            success, role = self.backend.authenticate_user(username, password)
            if not success:
                error_label.config(text='Invalid username or password')
                return
            # Log successful login
            self.backend.add_activity(f'User logged in: {username}', user=username)
            # Save current user and build main UI
            self.current_user = username
            self.current_role = role
            # Destroy login UI
            if hasattr(self, 'login_frame') and self.login_frame:
                self.login_frame.destroy()
                self.login_frame = None
            # Build main layout and show dashboard
            self.create_main_layout()
            # Show/hide Users and Settings buttons based on role
            if role != 'admin':
                self.users_btn.pack_forget()
                if hasattr(self, 'settings_btn'):
                    self.settings_btn.pack_forget()
            else:
                self.users_btn.pack(side='left', padx=5)
                if hasattr(self, 'settings_btn'):
                    self.settings_btn.pack(side='left', padx=5)
            self.show_dashboard()

        login_btn = ttk.Button(btns, text='Login', command=do_login, style='Primary.TButton', width=14)
        login_btn.pack(side='right', padx=6)
        exit_btn = ttk.Button(btns, text='Exit', command=self.root.destroy, width=10)
        exit_btn.pack(side='right', padx=6)

        # Keyboard and focus niceties
        user_entry.focus_set()
        # Bind Return and Escape to the login frame only so the handlers are
        # removed when the login UI is destroyed. Avoid binding these to the
        # root which can cause lingering handlers that interfere with other
        # views (e.g., pressing Enter in a search box triggering login).
        try:
            self.login_frame.bind('<Return>', do_login)
            self.login_frame.bind('<Escape>', lambda e: self.root.destroy())
        except Exception:
            # Fallback to root if login_frame isn't available for some reason
            self.root.bind('<Return>', do_login)
            self.root.bind('<Escape>', lambda e: self.root.destroy())

        # Ensure pressing Enter while focused on the password entry submits
        # the login instead of moving focus (global class binding moves
        # focus to the next widget). Widget-level handler returns "break"
        # to stop further event propagation.
        def _pass_enter_submit(event=None):
            do_login()
            return "break"

        try:
            pass_entry.bind('<Return>', _pass_enter_submit)
        except Exception:
            pass

    def logout(self):
        confirm = messagebox.askyesno('Logout', 'Are you sure you want to logout?')
        if not confirm:
            return
        if self.current_user:
            self.backend.add_activity(f'User logged out: {self.current_user}', user=self.current_user)
        # Destroy and recreate main UI
        self.current_user = None
        self.current_role = None
        for widget in self.root.winfo_children():
            widget.destroy()
        # Show login again
        self.show_login_dialog()
    
    def show_reports(self):
        # Display reports screen
        self.clear_main_frame()
        
        ttk.Label(self.main_frame, text="REPORTS & ANALYTICS", style='Title.TLabel').pack(pady=10)
        
        # Report controls
        controls_frame = ttk.Frame(self.main_frame)
        controls_frame.pack(fill='x', pady=10)
        
        ttk.Label(controls_frame, text="Report Type:").pack(side='left', padx=5)
        self.report_type = tk.StringVar(value="sales")
        ttk.Combobox(controls_frame, textvariable=self.report_type,
                    values=["sales", "stock", "customers"], state="readonly").pack(side='left', padx=5)
        
        ttk.Label(controls_frame, text="Period:").pack(side='left', padx=5)
        self.report_period = tk.StringVar(value="today")
        ttk.Combobox(controls_frame, textvariable=self.report_period,
                    values=["today", "week", "month"], state="readonly").pack(side='left', padx=5)
        
        ttk.Button(controls_frame, text="Generate Report", command=self.generate_report).pack(side='left', padx=20)
        
        # Report display
        self.report_text = tk.Text(self.main_frame, wrap='word', height=20, width=80)
        self.report_text.pack(fill='both', expand=True, pady=10)
        
        # Generate initial report
        self.generate_report()

    def show_activity_log(self):
        # Display activity log entries
        self.clear_main_frame()

        ttk.Label(self.main_frame, text="ACTIVITY LOG", style='Title.TLabel').pack(pady=10)

        toolbar = ttk.Frame(self.main_frame)
        toolbar.pack(fill='x', pady=5)

        ttk.Label(toolbar, text="Filter by user:").pack(side='left', padx=5)
        self.activity_user_var = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.activity_user_var, width=25).pack(side='left', padx=5)
        ttk.Button(toolbar, text="Filter", command=self.filter_activity_log).pack(side='left', padx=5)
        ttk.Button(toolbar, text="Refresh", command=self.refresh_activity_log).pack(side='left', padx=5)

        # Activity log table
        cols = ('ID', 'User', 'Action', 'Time')
        table_frame = ttk.Frame(self.main_frame)
        table_frame.pack(fill='both', expand=True, pady=10)

        self.activity_tree = ttk.Treeview(table_frame, columns=cols, show='headings', height=18)
        for c in cols:
            self.activity_tree.heading(c, text=c)

        self.activity_tree.column('ID', width=70)
        self.activity_tree.column('User', width=140)
        self.activity_tree.column('Action', width=380)
        self.activity_tree.column('Time', width=160)

        scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=self.activity_tree.yview)
        self.activity_tree.configure(yscrollcommand=scrollbar.set)
        self.activity_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        self.refresh_activity_log()

    def refresh_activity_log(self):
        # Refresh tree with backend activity log
        if not hasattr(self, 'activity_tree'):
            return
        for i in self.activity_tree.get_children():
            self.activity_tree.delete(i)

        # Ensure latest from DB
        entries = sorted(self.backend.get_activity_log().items(), key=lambda x: x[1].get('timestamp') or datetime.min, reverse=True)
        for log_id, rec in entries:
            ts = rec.get('timestamp')
            ts_str = ts.strftime('%Y-%m-%d %H:%M:%S') if ts else ''
            self.activity_tree.insert('', 'end', values=(log_id, rec.get('user',''), rec.get('action',''), ts_str))

    def filter_activity_log(self):
        if not hasattr(self, 'activity_tree'):
            return
        query = self.activity_user_var.get().strip().lower()
        if not query:
            self.refresh_activity_log()
            return
        for i in self.activity_tree.get_children():
            self.activity_tree.delete(i)

        for log_id, rec in sorted(self.backend.get_activity_log().items(), key=lambda x: x[1].get('timestamp') or datetime.min, reverse=True):
            user = rec.get('user','')
            if query in str(user).lower():
                ts = rec.get('timestamp')
                ts_str = ts.strftime('%Y-%m-%d %H:%M:%S') if ts else ''
                self.activity_tree.insert('', 'end', values=(log_id, user, rec.get('action',''), ts_str))

    def refresh_customers(self):
        if not hasattr(self, 'customers_tree'):
            return

        for item in self.customers_tree.get_children():
            self.customers_tree.delete(item)

        for cust_id, customer in self.backend.get_customers().items():
            self.customers_tree.insert('', 'end', values=(
                cust_id,
                customer['name'],
                customer['phone'],
                customer['email'],
                self.format_currency(customer.get('total_purchases', 0))
            ))

    def search_customers(self):
        if not hasattr(self, 'customers_tree') or not hasattr(self, 'customers_search_var'):
            return

        query = self.customers_search_var.get().strip()
        if not query:
            self.refresh_customers()
            return

        results = self.backend.search_customers(query)

        for item in self.customers_tree.get_children():
            self.customers_tree.delete(item)

        for cust_id, customer in results.items():
            self.customers_tree.insert('', 'end', values=(
                cust_id,
                customer['name'],
                customer['phone'],
                customer['email'],
                self.format_currency(customer.get('total_purchases', 0))
            ))

    def edit_selected_customer(self):
        if not hasattr(self, 'customers_tree'):
            messagebox.showerror("Error", "Customers table is not available")
            return

        sel = self.customers_tree.selection()
        if not sel:
            messagebox.showerror("Error", "Please select a customer to edit")
            return

        cust_id = self.customers_tree.item(sel[0], 'values')[0]
        self.show_edit_customer_dialog(cust_id)

    def delete_selected_customer(self):
        if not hasattr(self, 'customers_tree'):
            messagebox.showerror("Error", "Customers table is not available")
            return

        sel = self.customers_tree.selection()
        if not sel:
            messagebox.showerror("Error", "Please select a customer to delete")
            return

        cust_id = self.customers_tree.item(sel[0], 'values')[0]
        confirm = messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete customer {cust_id}?")
        if not confirm:
            return

        success = self.backend.delete_customer(cust_id, user=self.current_user)
        if success:
            messagebox.showinfo("Success", "Customer deleted successfully")
            self.refresh_customers()
        else:
            messagebox.showerror("Error", "Failed to delete customer")

    def show_edit_customer_dialog(self, customer_id):
        # Show dialog to edit existing customer
        customers = self.backend.get_customers()
        if customer_id not in customers:
            messagebox.showerror("Error", "Invalid customer selected")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Customer")
        dialog.geometry("400x250")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Edit Customer", style='Title.TLabel').pack(pady=10)

        form_frame = ttk.Frame(dialog)
        form_frame.pack(fill='both', expand=True, padx=20, pady=10)

        customer = customers.get(customer_id, {})

        ttk.Label(form_frame, text="Name:").grid(row=0, column=0, sticky='w', pady=5)
        name_var = tk.StringVar(value=customer.get('name', ''))
        ttk.Entry(form_frame, textvariable=name_var, width=30).grid(row=0, column=1, sticky='ew', pady=5, padx=5)

        ttk.Label(form_frame, text="Phone:").grid(row=1, column=0, sticky='w', pady=5)
        phone_var = tk.StringVar(value=customer.get('phone', ''))
        ttk.Entry(form_frame, textvariable=phone_var, width=30).grid(row=1, column=1, sticky='ew', pady=5, padx=5)

        ttk.Label(form_frame, text="Email:").grid(row=2, column=0, sticky='w', pady=5)
        email_var = tk.StringVar(value=customer.get('email', ''))
        ttk.Entry(form_frame, textvariable=email_var, width=30).grid(row=2, column=1, sticky='ew', pady=5, padx=5)

        def save_customer():
            name = name_var.get().strip()
            phone = phone_var.get().strip()
            email = email_var.get().strip()

            if not name:
                messagebox.showerror("Error", "Customer name is required")
                return

            success = self.backend.update_customer(customer_id, name=name, phone=phone, email=email, user=self.current_user)
            if success:
                messagebox.showinfo("Success", "Customer updated successfully")
                dialog.destroy()
                self.refresh_customers()
            else:
                messagebox.showerror("Error", "Failed to update customer")

        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill='x', pady=10)

        ttk.Button(button_frame, text="Save", command=save_customer, style='Primary.TButton').pack(side='left', padx=10)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side='left', padx=10)

    # --- Suppliers UI ---
    def show_suppliers(self):
        self.clear_main_frame()

        ttk.Label(self.main_frame, text="SUPPLIERS", style='Title.TLabel').pack(pady=10)

        # Toolbar with actions and search
        toolbar = ttk.Frame(self.main_frame)
        toolbar.pack(fill='x', pady=5)

        ttk.Button(toolbar, text="Add New Supplier", command=self.show_add_supplier_dialog).pack(side='left', padx=4)
        ttk.Button(toolbar, text="Edit Selected", command=self.edit_selected_supplier).pack(side='left', padx=4)
        ttk.Button(toolbar, text="Delete Selected", command=self.delete_selected_supplier).pack(side='left', padx=4)
        ttk.Button(toolbar, text="Toggle Status", command=self.toggle_selected_supplier_status).pack(side='left', padx=4)

        ttk.Label(toolbar, text="Search:").pack(side='right', padx=5)
        self.suppliers_search_var = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.suppliers_search_var, width=30).pack(side='right', padx=5)
        # Auto-refresh suppliers list when search box is cleared
        try:
            self.suppliers_search_var.trace_add('write', lambda *a: self.refresh_suppliers() if not (self.suppliers_search_var.get() or '').strip() else None)
        except Exception:
            self.suppliers_search_var.trace('w', lambda *a: self.refresh_suppliers() if not (self.suppliers_search_var.get() or '').strip() else None)
        ttk.Button(toolbar, text="Search", command=self.search_suppliers).pack(side='right', padx=5)

        # Suppliers table
        table_frame = ttk.Frame(self.main_frame)
        table_frame.pack(fill='both', expand=True, pady=10)

        columns = ('ID', 'Name', 'Company', 'Phone', 'Email', 'Status', 'Created')
        self.suppliers_tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=12)

        for col in columns:
            self.suppliers_tree.heading(col, text=col)

        scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=self.suppliers_tree.yview)
        self.suppliers_tree.configure(yscrollcommand=scrollbar.set)

        self.suppliers_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        self.refresh_suppliers()

    # --- Users management (admin only) ---
    def show_users(self):
        if self.current_role != 'admin':
            messagebox.showerror('Access Denied', 'Only administrators can manage users')
            return
        self.clear_main_frame()
        ttk.Label(self.main_frame, text='USER MANAGEMENT', style='Title.TLabel').pack(pady=10)

        toolbar = ttk.Frame(self.main_frame)
        toolbar.pack(fill='x')
        ttk.Button(toolbar, text='Add User', command=self.show_add_user_dialog).pack(side='left', padx=4)
        ttk.Button(toolbar, text='Edit Selected', command=self.edit_selected_user).pack(side='left', padx=4)
        ttk.Button(toolbar, text='Delete Selected', command=self.delete_selected_user).pack(side='left', padx=4)
        ttk.Button(toolbar, text='Toggle Status', command=self.toggle_selected_user_status).pack(side='left', padx=4)
        # Search box for users (right side)
        self.users_search_var = tk.StringVar()
        ttk.Label(toolbar, text='Search:').pack(side='right', padx=5)
        ttk.Entry(toolbar, textvariable=self.users_search_var, width=30).pack(side='right', padx=5)
        # Auto-refresh users table when search cleared
        try:
            self.users_search_var.trace_add('write', lambda *a: self.refresh_users() if not (self.users_search_var.get() or '').strip() else None)
        except Exception:
            self.users_search_var.trace('w', lambda *a: self.refresh_users() if not (self.users_search_var.get() or '').strip() else None)
        ttk.Button(toolbar, text='Search', command=self.search_users).pack(side='right', padx=5)
        ttk.Button(toolbar, text='Refresh', command=self.refresh_users).pack(side='right', padx=5)

        table_frame = ttk.Frame(self.main_frame)
        table_frame.pack(fill='both', expand=True, pady=10)
        columns = ('Username', 'Full Name', 'Phone', 'Email', 'Role', 'Status')
        self.users_tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=12)
        for col in columns:
            self.users_tree.heading(col, text=col)
        scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=self.users_tree.yview)
        self.users_tree.configure(yscrollcommand=scrollbar.set)
        self.users_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        self.refresh_users()

    def refresh_users(self):
        if not hasattr(self, 'users_tree'):
            return
        for item in self.users_tree.get_children():
            self.users_tree.delete(item)
        for uname, info in self.backend.get_users().items():
            active = info.get('active', True)
            active_text = 'Active' if active else 'Inactive'
            self.users_tree.insert('', 'end', values=(
                uname,
                info.get('full_name',''),
                info.get('phone',''),
                info.get('email',''),
                info.get('role',''),
                active_text
            ))

    def search_users(self):
        # Search users by username, full name, role, or status and populate the users table.
        if not hasattr(self, 'users_tree') or not hasattr(self, 'users_search_var'):
            return

        query = self.users_search_var.get().strip()
        if not query:
            self.refresh_users()
            return

        # Prefer DB-backed search
        try:
            matches = self.backend.search_users(query)
            # Populate tree with matches
            for item in self.users_tree.get_children():
                self.users_tree.delete(item)

            for uname, info in matches.items():
                status_text = 'Active' if info.get('active', True) else 'Inactive'
                self.users_tree.insert('', 'end', values=(uname, info.get('full_name',''), info.get('phone',''), info.get('email',''), info.get('role',''), status_text))
        except Exception:
            # Fallback to previous in-Python implementation
            q = query.lower()
            matches = []
            for uname, info in self.backend.get_users().items():
                full = info.get('full_name','') or ''
                role = info.get('role','') or ''
                status = 'active' if info.get('active', True) else 'inactive'
                phone = info.get('phone','') or ''
                email = info.get('email','') or ''
                if (q in uname.lower() or q in full.lower() or q in phone.lower() or q in email.lower() or q in role.lower() or q in status.lower()):
                    matches.append((uname, full, phone, email, role, status.title()))

            for item in self.users_tree.get_children():
                self.users_tree.delete(item)

            for uname, full, phone, email, role, status_text in matches:
                self.users_tree.insert('', 'end', values=(uname, full, phone, email, role, status_text))

    def show_add_user_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title('Add User')
        dialog.geometry('420x380')
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        frm = ttk.Frame(dialog)
        frm.pack(fill='both', expand=True, padx=12, pady=10)
        frm.columnconfigure(1, weight=1)
        ttk.Label(frm, text='Username:').grid(row=0, column=0, sticky='w', padx=6, pady=6)
        uname_var = tk.StringVar()
        uname_entry = ttk.Entry(frm, textvariable=uname_var)
        uname_entry.grid(row=0, column=1, sticky='ew', padx=6, pady=6)
        ttk.Label(frm, text='Full Name:').grid(row=1, column=0, sticky='w', padx=6, pady=6)
        fullname_var = tk.StringVar()
        fullname_entry = ttk.Entry(frm, textvariable=fullname_var)
        fullname_entry.grid(row=1, column=1, sticky='ew', padx=6, pady=6)
        ttk.Label(frm, text='Password:').grid(row=2, column=0, sticky='w', padx=6, pady=6)
        pwd_var = tk.StringVar()
        pwd_entry = ttk.Entry(frm, textvariable=pwd_var, show='*')
        pwd_entry.grid(row=2, column=1, sticky='ew', padx=6, pady=6)
        ttk.Label(frm, text='Role:').grid(row=3, column=0, sticky='w', padx=6, pady=6)
        role_var = tk.StringVar(value='cashier')
        role_combo = ttk.Combobox(frm, textvariable=role_var, values=['admin','manager','cashier'], state='readonly')
        role_combo.grid(row=3, column=1, sticky='ew', padx=6, pady=6)
        # Active flag
        ttk.Label(frm, text='Active:').grid(row=4, column=0, sticky='w', padx=6, pady=6)
        active_var = tk.BooleanVar(value=True)
        active_chk = ttk.Checkbutton(frm, variable=active_var)
        active_chk.grid(row=4, column=1, sticky='w', padx=6, pady=6)

        # Extra contact fields (email, phone)
        ttk.Label(frm, text='Phone (optional):').grid(row=5, column=0, sticky='w', padx=6, pady=6)
        phone_var = tk.StringVar()
        ttk.Entry(frm, textvariable=phone_var).grid(row=5, column=1, sticky='ew', padx=6, pady=6)
        ttk.Label(frm, text='Email (optional):').grid(row=6, column=0, sticky='w', padx=6, pady=6)
        email_var = tk.StringVar()
        ttk.Entry(frm, textvariable=email_var).grid(row=6, column=1, sticky='ew', padx=6, pady=6)

        def save_user(close_after=True):
            uname = uname_var.get().strip()
            fullname = fullname_var.get().strip()
            pwd = pwd_var.get()
            role = role_var.get()
            if not uname or not pwd:
                messagebox.showerror('Error', 'Username and password required')
                return
            self.backend.add_user(uname, fullname, pwd, role=role, active=bool(active_var.get()), email=email_var.get().strip(), phone=phone_var.get().strip())
            if hasattr(self, 'users_tree'):
                self.refresh_users()
            if close_after:
                dialog.destroy()
            else:
                # Clear fields and focus first entry
                uname_var.set('')
                fullname_var.set('')
                pwd_var.set('')
                role_var.set('cashier')
                active_var.set(True)
                uname_entry.focus_set()

        # Buttons: right aligned like other dialogs
        btns = ttk.Frame(dialog)
        btns.pack(fill='x', pady=10, padx=12)
        ttk.Button(btns, text='Save & Close', command=lambda: save_user(close_after=True), style='SaveClose.TButton').pack(side='right', padx=6)
        ttk.Button(btns, text='Save & New', command=lambda: save_user(close_after=False), style='SaveNew.TButton').pack(side='right', padx=6)
        ttk.Button(btns, text='Close', command=dialog.destroy).pack(side='right', padx=6)

        # Keyboard shortcuts
        dialog.bind('<Return>', lambda e: save_user(close_after=True))
        dialog.bind('<Escape>', lambda e: dialog.destroy())

    def edit_selected_user(self):
        if not hasattr(self, 'users_tree'):
            return
        sel = self.users_tree.selection()
        if not sel:
            messagebox.showerror('Error', 'Select user to edit')
            return
        uname = self.users_tree.item(sel[0], 'values')[0]
        self.show_edit_user_dialog(uname)

    def show_edit_user_dialog(self, username):
        users = self.backend.get_users()
        if username not in users:
            messagebox.showerror('Error', 'Invalid user')
            return
        info = users[username]
        dialog = tk.Toplevel(self.root)
        dialog.title('Edit User')
        dialog.geometry('420x380')
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        frm = ttk.Frame(dialog)
        frm.pack(fill='both', expand=True, padx=12, pady=10)
        frm.columnconfigure(1, weight=1)
        ttk.Label(frm, text='Username:').grid(row=0, column=0, sticky='w', padx=6, pady=6)
        ttk.Label(frm, text=username).grid(row=0, column=1, sticky='w', padx=6, pady=6)
        ttk.Label(frm, text='Full Name:').grid(row=1, column=0, sticky='w', padx=6, pady=6)
        fullname_var = tk.StringVar(value=info.get('full_name',''))
        ttk.Entry(frm, textvariable=fullname_var).grid(row=1, column=1, sticky='ew', padx=6, pady=6)
        ttk.Label(frm, text='Password (leave blank to keep):').grid(row=2, column=0, sticky='w', padx=6, pady=6)
        pwd_var = tk.StringVar()
        ttk.Entry(frm, textvariable=pwd_var, show='*').grid(row=2, column=1, sticky='ew', padx=6, pady=6)
        ttk.Label(frm, text='Role:').grid(row=3, column=0, sticky='w', padx=6, pady=6)
        role_var = tk.StringVar(value=info.get('role','cashier'))
        ttk.Combobox(frm, textvariable=role_var, values=['admin','manager','cashier'], state='readonly').grid(row=3, column=1, sticky='ew', padx=6, pady=6)
        # Active flag
        ttk.Label(frm, text='Active:').grid(row=4, column=0, sticky='w', padx=6, pady=6)
        active_var = tk.BooleanVar(value=info.get('active', True))
        ttk.Checkbutton(frm, variable=active_var).grid(row=4, column=1, sticky='w', padx=6, pady=6)

        # Contact fields
        ttk.Label(frm, text='Phone (optional):').grid(row=5, column=0, sticky='w', padx=6, pady=6)
        phone_var = tk.StringVar(value=info.get('phone',''))
        ttk.Entry(frm, textvariable=phone_var).grid(row=5, column=1, sticky='ew', padx=6, pady=6)
        ttk.Label(frm, text='Email (optional):').grid(row=6, column=0, sticky='w', padx=6, pady=6)
        email_var = tk.StringVar(value=info.get('email',''))
        ttk.Entry(frm, textvariable=email_var).grid(row=6, column=1, sticky='ew', padx=6, pady=6)

        def save_user():
            fullname = fullname_var.get().strip()
            pwd = pwd_var.get()
            role = role_var.get()
            self.backend.update_user(
                username,
                full_name=fullname,
                password=(pwd if pwd else None),
                role=role,
                active=bool(active_var.get()),
                email=email_var.get().strip(),
                phone=phone_var.get().strip()
            )
            dialog.destroy()
            self.refresh_users()

        btns = ttk.Frame(dialog)
        btns.pack(fill='x', pady=10, padx=12)
        ttk.Button(btns, text='Save', command=save_user, style='Primary.TButton').pack(side='right', padx=6)
        ttk.Button(btns, text='Close', command=dialog.destroy).pack(side='right', padx=6)

        dialog.bind('<Return>', lambda e: save_user())
        dialog.bind('<Escape>', lambda e: dialog.destroy())

    def delete_selected_user(self):
        if not hasattr(self, 'users_tree'):
            return
        sel = self.users_tree.selection()
        if not sel:
            messagebox.showerror('Error', 'Select user to delete')
            return
        uname = self.users_tree.item(sel[0], 'values')[0]
        if uname == self.current_user:
            messagebox.showerror('Error', 'Cannot delete the currently logged-in user')
            return
        confirm = messagebox.askyesno('Confirm', f'Delete user {uname}?')
        if not confirm:
            return
        self.backend.delete_user(uname)
        self.refresh_users()

    def toggle_selected_user_status(self):
        if not hasattr(self, 'users_tree'):
            return
        sel = self.users_tree.selection()
        if not sel:
            messagebox.showerror('Error', 'Select a user to change status')
            return
        uname = self.users_tree.item(sel[0], 'values')[0]
        # Prevent changing status of currently logged-in user for safety
        if uname == self.current_user:
            messagebox.showerror('Error', 'Cannot change status of the currently logged-in user')
            return
        users = self.backend.get_users()
        info = users.get(uname)
        if not info:
            messagebox.showerror('Error', 'Selected user not found')
            return
        current = bool(info.get('active', True))
        new_status = not current
        action = 'Activate' if new_status else 'Deactivate'
        confirm = messagebox.askyesno('Confirm', f"{action} user {uname}?")
        if not confirm:
            return
        # Use backend toggle helper which calls the ToggleUserStatus stored procedure
        ok, result = self.backend.toggle_user_status(uname)
        if ok:
            new_status_val = result if isinstance(result, bool) else bool(result)
            messagebox.showinfo('Success', f'User {uname} is now {"Active" if new_status_val else "Inactive"}')
            self.refresh_users()
        else:
            messagebox.showerror('Error', f'Failed to update user status: {result}')

    def refresh_suppliers(self):
        if not hasattr(self, 'suppliers_tree'):
            return

        for item in self.suppliers_tree.get_children():
            self.suppliers_tree.delete(item)

        for sid, supplier in self.backend.get_suppliers().items():
            created = supplier.get('created_date')
            created_str = created.strftime('%Y-%m-%d') if created else ''
            status_text = 'Active' if supplier.get('active', True) else 'Inactive'
            self.suppliers_tree.insert('', 'end', values=(
                sid,
                supplier.get('name',''),
                supplier.get('company',''),
                supplier.get('phone',''),
                supplier.get('email',''),
                status_text,
                created_str
            ))

    def show_add_supplier_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Add New Supplier")
        # Increase dialog height so the form and buttons are fully visible
        dialog.geometry("420x360")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        ttk.Label(dialog, text="Add New Supplier", style='Title.TLabel').pack(pady=10)

        form_frame = ttk.Frame(dialog)
        form_frame.pack(fill='both', expand=True, padx=20, pady=10)

        ttk.Label(form_frame, text="Name:").grid(row=0, column=0, sticky='w', pady=5)
        name_var = tk.StringVar()
        name_entry = ttk.Entry(form_frame, textvariable=name_var, width=30)
        name_entry.grid(row=0, column=1, sticky='ew', pady=5, padx=5)

        ttk.Label(form_frame, text="Company:").grid(row=1, column=0, sticky='w', pady=5)
        company_var = tk.StringVar()
        company_entry = ttk.Entry(form_frame, textvariable=company_var, width=30)
        company_entry.grid(row=1, column=1, sticky='ew', pady=5, padx=5)

        ttk.Label(form_frame, text="Phone:").grid(row=2, column=0, sticky='w', pady=5)
        phone_var = tk.StringVar()
        phone_entry = ttk.Entry(form_frame, textvariable=phone_var, width=30)
        phone_entry.grid(row=2, column=1, sticky='ew', pady=5, padx=5)

        ttk.Label(form_frame, text="Email:").grid(row=3, column=0, sticky='w', pady=5)
        email_var = tk.StringVar()
        email_entry = ttk.Entry(form_frame, textvariable=email_var, width=30)
        email_entry.grid(row=3, column=1, sticky='ew', pady=5, padx=5)

        # Active status
        ttk.Label(form_frame, text="Active:").grid(row=4, column=0, sticky='w', pady=5)
        active_var = tk.BooleanVar(value=True)
        active_chk = ttk.Checkbutton(form_frame, variable=active_var)
        active_chk.grid(row=4, column=1, sticky='w', pady=5, padx=5)

        def save_supplier(close_after=True):
            name = name_var.get().strip()
            company = company_var.get().strip()
            phone = phone_var.get().strip()
            email = email_var.get().strip()
            if not name:
                messagebox.showerror("Error", "Supplier name is required")
                return
            self.backend.add_supplier(name, company, phone, email, active=bool(active_var.get()), user=self.current_user)
            messagebox.showinfo("Success", "Supplier added successfully")

            if hasattr(self, 'suppliers_tree'):
                self.refresh_suppliers()

            if close_after:
                dialog.destroy()
            else:
                name_var.set('')
                company_var.set('')
                phone_var.set('')
                email_var.set('')
                active_var.set(True)
                name_entry.focus_set()
        # Buttons: align to the right and highlight Save
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill='x', pady=8, padx=12)
        ttk.Button(button_frame, text="Save & Close", command=lambda: save_supplier(close_after=True), style='SaveClose.TButton').pack(side='right', padx=6)
        ttk.Button(button_frame, text="Save & New", command=lambda: save_supplier(close_after=False), style='SaveNew.TButton').pack(side='right', padx=6)
        ttk.Button(button_frame, text="Close", command=dialog.destroy).pack(side='right', padx=6)

        # Keyboard shortcuts: Enter to save, Esc to cancel
        dialog.bind('<Return>', lambda e: save_supplier())
        dialog.bind('<Escape>', lambda e: dialog.destroy())

    def edit_selected_supplier(self):
        if not hasattr(self, 'suppliers_tree'):
            messagebox.showerror("Error", "Suppliers table is not available")
            return
        sel = self.suppliers_tree.selection()
        if not sel:
            messagebox.showerror("Error", "Please select a supplier to edit")
            return
        sid = self.suppliers_tree.item(sel[0], 'values')[0]
        self.show_edit_supplier_dialog(sid)

    def delete_selected_supplier(self):
        if not hasattr(self, 'suppliers_tree'):
            messagebox.showerror("Error", "Suppliers table is not available")
            return
        sel = self.suppliers_tree.selection()
        if not sel:
            messagebox.showerror("Error", "Please select a supplier to delete")
            return
        sid = self.suppliers_tree.item(sel[0], 'values')[0]
        confirm = messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete supplier {sid}?")
        if not confirm:
            return
        success = self.backend.delete_supplier(sid, user=self.current_user)
        if success:
            messagebox.showinfo("Success", "Supplier deleted successfully")
            self.refresh_suppliers()
        else:
            messagebox.showerror("Error", "Failed to delete supplier")

    def toggle_selected_supplier_status(self):
        if not hasattr(self, 'suppliers_tree'):
            messagebox.showerror('Error', 'Suppliers table is not available')
            return
        sel = self.suppliers_tree.selection()
        if not sel:
            messagebox.showerror('Error', 'Please select a supplier to change status')
            return
        sid = self.suppliers_tree.item(sel[0], 'values')[0]
        suppliers = self.backend.get_suppliers()
        info = suppliers.get(sid)
        if not info:
            messagebox.showerror('Error', 'Selected supplier not found')
            return
        current = bool(info.get('active', True))
        new_status = not current
        action = 'Activate' if new_status else 'Deactivate'
        confirm = messagebox.askyesno('Confirm', f"{action} supplier {sid}?")
        if not confirm:
            return
        success = self.backend.update_supplier(sid, active=new_status)
        if success:
            messagebox.showinfo('Success', f"Supplier {sid} is now {'Active' if new_status else 'Inactive'}")
            self.refresh_suppliers()
        else:
            messagebox.showerror('Error', 'Failed to update supplier status')

    def show_edit_supplier_dialog(self, supplier_id):
        suppliers = self.backend.get_suppliers()
        if supplier_id not in suppliers:
            messagebox.showerror("Error", "Invalid supplier selected")
            return
        supplier = suppliers[supplier_id]
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Supplier")
        dialog.geometry("420x320")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        ttk.Label(dialog, text="Edit Supplier", style='Title.TLabel').pack(pady=10)
        form_frame = ttk.Frame(dialog)
        form_frame.pack(fill='both', expand=True, padx=20, pady=10)
        ttk.Label(form_frame, text="Name:").grid(row=0, column=0, sticky='w', pady=5)
        name_var = tk.StringVar(value=supplier.get('name', ''))
        ttk.Entry(form_frame, textvariable=name_var, width=30).grid(row=0, column=1, sticky='ew', pady=5, padx=5)
        ttk.Label(form_frame, text="Company:").grid(row=1, column=0, sticky='w', pady=5)
        company_var = tk.StringVar(value=supplier.get('company',''))
        ttk.Entry(form_frame, textvariable=company_var, width=30).grid(row=1, column=1, sticky='ew', pady=5, padx=5)

        ttk.Label(form_frame, text="Phone:").grid(row=2, column=0, sticky='w', pady=5)
        phone_var = tk.StringVar(value=supplier.get('phone', ''))
        ttk.Entry(form_frame, textvariable=phone_var, width=30).grid(row=2, column=1, sticky='ew', pady=5, padx=5)
        ttk.Label(form_frame, text="Email:").grid(row=3, column=0, sticky='w', pady=5)
        email_var = tk.StringVar(value=supplier.get('email', ''))
        ttk.Entry(form_frame, textvariable=email_var, width=30).grid(row=3, column=1, sticky='ew', pady=5, padx=5)

        # Active status
        ttk.Label(form_frame, text="Active:").grid(row=4, column=0, sticky='w', pady=5)
        active_var = tk.BooleanVar(value=supplier.get('active', True))
        ttk.Checkbutton(form_frame, variable=active_var).grid(row=4, column=1, sticky='w', pady=5, padx=5)

        def save_supplier():
            name = name_var.get().strip()
            company = company_var.get().strip()
            phone = phone_var.get().strip()
            email = email_var.get().strip()
            if not name:
                messagebox.showerror("Error", "Supplier name is required")
                return
            success = self.backend.update_supplier(supplier_id, name=name, company=company, phone=phone, email=email, active=bool(active_var.get()), user=self.current_user)
            if success:
                messagebox.showinfo("Success", "Supplier updated successfully")
                dialog.destroy()
                self.refresh_suppliers()
            else:
                messagebox.showerror("Error", "Failed to update supplier")

        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill='x', pady=8, padx=12)
        ttk.Button(button_frame, text="Save", command=save_supplier, style='Primary.TButton').pack(side='right', padx=6)
        ttk.Button(button_frame, text="Close", command=dialog.destroy).pack(side='right', padx=6)

        dialog.bind('<Return>', lambda e: save_supplier())
        dialog.bind('<Escape>', lambda e: dialog.destroy())

    def search_suppliers(self):
        if not hasattr(self, 'suppliers_tree') or not hasattr(self, 'suppliers_search_var'):
            return
        query = self.suppliers_search_var.get().strip()
        if not query:
            self.refresh_suppliers()
            return
        results = self.backend.search_suppliers(query)
        for item in self.suppliers_tree.get_children():
            self.suppliers_tree.delete(item)
        for sid, supplier in results.items():
            created = supplier.get('created_date')
            created_str = created.strftime('%Y-%m-%d') if created else ''
            status_text = 'Active' if supplier.get('active', True) else 'Inactive'
            self.suppliers_tree.insert('', 'end', values=(
                sid,
                supplier.get('name',''),
                supplier.get('company',''),
                supplier.get('phone',''),
                supplier.get('email',''),
                status_text,
                created_str
            ))
    
    def generate_report(self):
        # Generate and display report based on selections
        report_type = self.report_type.get()
        period = self.report_period.get()
        
        self.report_text.delete(1.0, tk.END)
        
        if report_type == "sales":
            self.generate_sales_report(period)
        elif report_type == "stock":
            self.generate_stock_report()
        elif report_type == "customers":
            self.generate_customers_report()
    
    def generate_sales_report(self, period):
        self.report_text.insert(tk.END, "SALES REPORT\n")
        self.report_text.insert(tk.END, "=" * 50 + "\n\n")

        try:
            cursor.execute("EXEC GetSalesReport ?", period)
            rows = cursor.fetchall()
        except Exception:
            rows = []

        total_sales = len(rows)
        total_revenue = sum(float(r[5] or 0) for r in rows)

        self.report_text.insert(tk.END, f"Period: {period.capitalize()}\n")
        self.report_text.insert(tk.END, f"Total Sales: {total_sales}\n")
        self.report_text.insert(tk.END, f"Total Revenue: {self.format_currency(total_revenue)}\n\n")

        self.report_text.insert(tk.END, "Recent Sales:\n")
        self.report_text.insert(tk.END, "-" * 30 + "\n")

        for r in rows[:10]:
            sale_id = r[0]
            cust_name = r[2] or 'Walk-in'
            total = r[5] if len(r) > 5 else 0
            self.report_text.insert(tk.END, f"{sale_id}: {cust_name} - {self.format_currency(total)}\n")
    
    def generate_stock_report(self):
        self.report_text.insert(tk.END, "STOCK REPORT\n")
        self.report_text.insert(tk.END, "=" * 50 + "\n\n")

        try:
            cursor.execute("EXEC GetStockReportSummary")
            srow = cursor.fetchone()
            total_medicines = int(srow[0] or 0)
            total_value = float(srow[1] or 0.0)
            low_count = int(srow[2] or 0)
        except Exception:
            total_medicines = 0
            total_value = 0.0
            low_count = 0

        self.report_text.insert(tk.END, f"Total Medicines: {total_medicines}\n")
        self.report_text.insert(tk.END, f"Total Stock Value: {self.format_currency(total_value)}\n")
        self.report_text.insert(tk.END, f"Low Stock Items: {low_count}\n\n")

        self.report_text.insert(tk.END, "Low Stock Items:\n")
        self.report_text.insert(tk.END, "-" * 30 + "\n")
        try:
            cursor.execute("EXEC GetLowStockItems")
            low_rows = cursor.fetchall()
        except Exception:
            low_rows = []

        for r in low_rows:
            name = r[1] or ''
            qty = int(r[3] or 0)
            self.report_text.insert(tk.END, f"{name}: {qty} left\n")
    
    def generate_customers_report(self):
        self.report_text.insert(tk.END, "CUSTOMERS REPORT\n")
        self.report_text.insert(tk.END, "=" * 50 + "\n\n")

        try:
            cursor.execute("EXEC GetCustomersReport")
            summary = cursor.fetchone()
            total_customers = int(summary[0] or 0)
            total_purchases = float(summary[1] or 0.0)
        except Exception:
            total_customers = 0
            total_purchases = 0.0

        self.report_text.insert(tk.END, f"Total Customers: {total_customers}\n")
        self.report_text.insert(tk.END, f"Total Customer Spending: {self.format_currency(total_purchases)}\n\n")

        self.report_text.insert(tk.END, "Top Customers:\n")
        self.report_text.insert(tk.END, "-" * 30 + "\n")

        try:
            if cursor.nextset():
                top_rows = cursor.fetchall()
            else:
                top_rows = []
        except Exception:
            top_rows = []

        for r in top_rows:
            name = r[1] or ''
            total = r[2] if len(r) > 2 else 0
            self.report_text.insert(tk.END, f"{name}: {self.format_currency(total)}\n")
    
    def show_settings(self):
        # Display settings screen
        # Restrict settings access to administrators only
        if getattr(self, 'current_role', None) != 'admin':
            messagebox.showerror('Access Denied', 'Only administrators can access Settings')
            return
        self.clear_main_frame()
        
        ttk.Label(self.main_frame, text="SETTINGS", style='Title.TLabel').pack(pady=10)
        
        # Pharmacy details
        details_frame = ttk.LabelFrame(self.main_frame, text="Pharmacy Details", padding="10")
        details_frame.pack(fill='x', pady=10, padx=5)
        
        ttk.Label(details_frame, text="Name:").grid(row=0, column=0, sticky='w', pady=5)
        self.name_var = tk.StringVar(value=self.backend.get_settings().get('pharmacy_name'))
        ttk.Entry(details_frame, textvariable=self.name_var, width=30).grid(row=0, column=1, sticky='ew', pady=5, padx=5)
        
        ttk.Label(details_frame, text="Address:").grid(row=1, column=0, sticky='w', pady=5)
        self.address_var = tk.StringVar(value=self.backend.get_settings().get('address'))
        ttk.Entry(details_frame, textvariable=self.address_var, width=30).grid(row=1, column=1, sticky='ew', pady=5, padx=5)
        
        ttk.Label(details_frame, text="Phone:").grid(row=2, column=0, sticky='w', pady=5)
        self.phone_var = tk.StringVar(value=self.backend.get_settings().get('phone'))
        ttk.Entry(details_frame, textvariable=self.phone_var, width=30).grid(row=2, column=1, sticky='ew', pady=5, padx=5)

        # Startup preference
        self.start_max_var = tk.BooleanVar(value=self.backend.get_settings().get('start_maximized', True))
        ttk.Label(details_frame, text="Start Maximized on Launch:").grid(row=3, column=0, sticky='w', pady=5)
        ttk.Checkbutton(details_frame, variable=self.start_max_var).grid(row=3, column=1, sticky='w', pady=5, padx=5)
        
        # Tax settings
        tax_frame = ttk.LabelFrame(self.main_frame, text="Tax & Pricing", padding="10")
        tax_frame.pack(fill='x', pady=10, padx=5)
        
        ttk.Label(tax_frame, text="Tax Rate (%):").grid(row=0, column=0, sticky='w', pady=5)
        self.tax_var = tk.StringVar(value=str(self.backend.get_settings().get('tax_rate', 0)))
        ttk.Entry(tax_frame, textvariable=self.tax_var, width=10).grid(row=0, column=1, sticky='w', pady=5, padx=5)
        
        ttk.Label(tax_frame, text="Currency:").grid(row=1, column=0, sticky='w', pady=5)
        self.currency_var = tk.StringVar(value=self.backend.get_settings().get('currency', 'USD'))
        ttk.Entry(tax_frame, textvariable=self.currency_var, width=10).grid(row=1, column=1, sticky='w', pady=5, padx=5)
        
        # Buttons
        button_frame = ttk.Frame(self.main_frame)
        button_frame.pack(pady=20)
        
        ttk.Button(button_frame, text="Save Settings", command=self.save_settings).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Reset to Default", command=self.reset_settings).pack(side='left', padx=5)
        # Show current user info
        info_frame = ttk.Frame(self.main_frame)
        info_frame.pack(fill='x', pady=10)
        user_label = self.current_user if self.current_user else 'Not logged in'
        role_label = self.current_role if self.current_role else 'N/A'
        ttk.Label(info_frame, text=f"Current User: {user_label} ({role_label})").pack(anchor='w')
    
    def save_settings(self):
        try:
            tax_rate = float(self.tax_var.get())
            if tax_rate < 0:
                messagebox.showerror("Error", "Tax rate cannot be negative")
                return
        except ValueError:
            messagebox.showerror("Error", "Tax rate must be a valid number")
            return
        
        # Save to database using stored procedure
        try:
            success = self.backend.update_settings(
                self.name_var.get(),
                self.address_var.get(),
                self.phone_var.get(),
                tax_rate,
                self.currency_var.get(),
                bool(self.start_max_var.get())
            )
            if success:
                messagebox.showinfo("Success", "Settings saved successfully")
            else:
                messagebox.showerror("Error", "Failed to save settings")
        except Exception as e:
            conn.rollback()
            messagebox.showerror("Error", f"Failed to save settings: {e}")

    def confirm_exit(self):
        if messagebox.askokcancel("Exit", "Are you sure you want to exit the application?"):
            self.root.quit()
            self.root.destroy()
    
    def reset_settings(self):
        confirm = messagebox.askyesno("Confirm Reset", "Reset all settings to default values?")
        if not confirm:
            return
        
        # Reset to defaults using stored procedure
        try:
            cursor.execute("EXEC UpdateSettings ?,?,?,?,?,?",
                'City Pharmacy',
                '123 Main Street',
                '555-0123',
                8.5,
                'USD',
                1
            )
            conn.commit()
            
            # No local cache to update; show_settings reads from DB on demand
            messagebox.showinfo("Success", "Settings reset to default")
            self.show_settings()
        except Exception as e:
            conn.rollback()
            messagebox.showerror("Error", f"Failed to reset settings: {e}")

def main():
    root = tk.Tk()
    root.withdraw()

    app = PharmacyFrontend(root)

    root.deiconify()
    root.mainloop()

if __name__ == "__main__":
    main()