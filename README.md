**Project**: Pharmacy Management — Desktop app (Python + SQL Server)

- **Description**: A Windows desktop pharmacy management application with a SQL Server backend. The GUI is built with `tkinter` and the database schema + stored procedures are in `pharmacy.sql`.

**Prerequisites**:
- Python 3.8 or newer on Windows
- Microsoft SQL Server (Express or full) and SQL Server Management Studio or `sqlcmd`
- ODBC Driver for SQL Server (e.g. "ODBC Driver 17 for SQL Server")
- Python package: `pyodbc`

**Files**:
- `pharmacy.py`: Main application (Tkinter GUI). Update the connection string inside this file to match your SQL Server instance.
- `pharmacy.sql`: SQL script to create the `PharmacyDB` database, tables, stored procedures, and seed data.
- `requirements.txt`: Python dependencies.
- `.gitignore`: Suggested ignores for Python projects.
- `LICENSE`: MIT license (recommended).

**Setup**:
1. Install Python and required ODBC driver for SQL Server.
2. Create a virtual environment (recommended):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

3. Create the database: open `pharmacy.sql` in SQL Server Management Studio and run the script, or run via `sqlcmd`:

```powershell
sqlcmd -S <SERVER_NAME> -i "pharmacy.sql"
```

Replace `<SERVER_NAME>` with your instance (for example `localhost\SQLEXPRESS`).

4. Update connection string in `pharmacy.py` (near top of file) to match your server, database, and authentication method. Example connection string currently in the file:

```
'DRIVER={SQL Server};SERVER=DESKTOP-HE9I4KD\\SQLEXPRESS;DATABASE=PharmacyDB;Trusted_Connection=yes;'
```

If using SQL Server ODBC Driver 17, you may prefer:

```
'DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost\\SQLEXPRESS;DATABASE=PharmacyDB;Trusted_Connection=yes;'
```

**Run**:

```powershell
python pharmacy.py
```

**Notes**:
- The GUI uses `pyodbc` to connect to SQL Server; ensure the ODBC driver and server are accessible.
- `tkinter` is included with standard Python installers on Windows.
- If `pyodbc` is not installed, the app will show a popup and exit — install dependencies before running.

**License**: See `LICENSE`.

