from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, send_file
)

import sqlite3
import os
import csv
import io

from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key"
)

DB = os.path.join(
    os.path.dirname(__file__),
    "erp.db"
)


# =========================================================
# DATABASE
# =========================================================

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def column_exists(conn, table, column):
    columns = conn.execute(
        f"PRAGMA table_info({table})"
    ).fetchall()

    return any(
        row["name"] == column
        for row in columns
    )


def init_db():

    conn = db()
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'Admin',
        active INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS projects(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_code TEXT UNIQUE NOT NULL,
        project_name TEXT NOT NULL,
        client TEXT,
        location TEXT,
        start_date TEXT,
        end_date TEXT,
        contract_value REAL DEFAULT 0,
        status TEXT DEFAULT 'Active',
        remarks TEXT
    );

    CREATE TABLE IF NOT EXISTS work_orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wo_no TEXT UNIQUE NOT NULL,
        work_name TEXT NOT NULL,
        project_id INTEGER,
        location TEXT,
        wo_date TEXT,
        po_no TEXT,
        po_date TEXT,
        start_date TEXT,
        end_date TEXT,
        contract_value REAL DEFAULT 0,
        status TEXT DEFAULT 'Active',
        remarks TEXT
    );

    CREATE TABLE IF NOT EXISTS vendors(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_code TEXT UNIQUE NOT NULL,
        vendor_name TEXT NOT NULL,
        contact TEXT,
        email TEXT,
        gst_no TEXT,
        bank_details TEXT,
        status TEXT DEFAULT 'Active',
        remarks TEXT
    );

    CREATE TABLE IF NOT EXISTS employees(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        emp_code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        designation TEXT,
        phone TEXT,
        joining_date TEXT,
        salary REAL DEFAULT 0,
        project_id INTEGER,
        status TEXT DEFAULT 'Active'
    );

    CREATE TABLE IF NOT EXISTS materials(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_code TEXT UNIQUE NOT NULL,
        item_name TEXT NOT NULL,
        unit TEXT,
        qty REAL DEFAULT 0,
        rate REAL DEFAULT 0,
        location TEXT,
        remarks TEXT
    );

    CREATE TABLE IF NOT EXISTS expenses(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        expense_date TEXT,
        project_id INTEGER,
        category TEXT,
        description TEXT,
        amount REAL DEFAULT 0,
        paid_to TEXT,
        payment_mode TEXT,
        remarks TEXT
    );

    CREATE TABLE IF NOT EXISTS bills(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bill_no TEXT UNIQUE NOT NULL,
        bill_date TEXT,
        project_id INTEGER,
        bill_type TEXT,
        party_name TEXT,
        gross_amount REAL DEFAULT 0,
        deductions REAL DEFAULT 0,
        net_amount REAL DEFAULT 0,
        status TEXT DEFAULT 'Pending',
        remarks TEXT
    );

    CREATE TABLE IF NOT EXISTS payments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        payment_no TEXT UNIQUE NOT NULL,
        payment_date TEXT,
        project_id INTEGER,
        party_name TEXT,
        amount REAL DEFAULT 0,
        mode TEXT,
        reference_no TEXT,
        type TEXT,
        remarks TEXT
    );
    """)

    # Upgrade old users table automatically
    if not column_exists(
        conn,
        "users",
        "active"
    ):
        conn.execute(
            "ALTER TABLE users "
            "ADD COLUMN active INTEGER "
            "NOT NULL DEFAULT 1"
        )

    user = conn.execute(
        "SELECT * FROM users "
        "WHERE username='admin'"
    ).fetchone()

    if not user:

        conn.execute(
            """
            INSERT INTO users
            (username,password_hash,role,active)
            VALUES(?,?,?,?)
            """,
            (
                "admin",
                generate_password_hash(
                    "admin123"
                ),
                "Admin",
                1
            )
        )

    conn.commit()
    conn.close()


# =========================================================
# LOGIN HELPERS
# =========================================================

def login_required(f):

    @wraps(f)
    def wrapper(*args, **kwargs):

        if "user" not in session:

            return redirect(
                url_for("login")
            )

        return f(
            *args,
            **kwargs
        )

    return wrapper


def admin_required(f):

    @wraps(f)
    def wrapper(*args, **kwargs):

        if "user" not in session:

            return redirect(
                url_for("login")
            )

        if session.get("role") != "Admin":

            flash(
                "Admin access required.",
                "danger"
            )

            return redirect(
                url_for("dashboard")
            )

        return f(
            *args,
            **kwargs
        )

    return wrapper


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        conn = db()

        user = conn.execute(
            """
            SELECT *
            FROM users
            WHERE username=?
            """,
            (
                request.form[
                    "username"
                ],
            )
        ).fetchone()

        conn.close()

        if (
            user
            and user["active"] == 1
            and check_password_hash(
                user["password_hash"],
                request.form["password"]
            )
        ):

            session["user"] = (
                user["username"]
            )

            session["role"] = (
                user["role"]
            )

            session["user_id"] = (
                user["id"]
            )

            return redirect(
                url_for("dashboard")
            )

        if user and user["active"] == 0:

            flash(
                "This account is inactive. "
                "Please contact administrator.",
                "danger"
            )

        else:

            flash(
                "Invalid username or password",
                "danger"
            )

    return render_template(
        "login.html"
    )


@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/")
@login_required
def dashboard():

    conn = db()

    stats = {

        "projects":
            conn.execute(
                """
                SELECT COUNT(*) c
                FROM projects
                WHERE status!='Completed'
                """
            ).fetchone()["c"],

        "work_orders":
            conn.execute(
                """
                SELECT COUNT(*) c
                FROM work_orders
                """
            ).fetchone()["c"],

        "vendors":
            conn.execute(
                """
                SELECT COUNT(*) c
                FROM vendors
                WHERE status='Active'
                """
            ).fetchone()["c"],

        "employees":
            conn.execute(
                """
                SELECT COUNT(*) c
                FROM employees
                WHERE status='Active'
                """
            ).fetchone()["c"],

        "stock_value":
            conn.execute(
                """
                SELECT
                COALESCE(
                    SUM(qty*rate),
                    0
                ) v
                FROM materials
                """
            ).fetchone()["v"],

        "expenses":
            conn.execute(
                """
                SELECT
                COALESCE(
                    SUM(amount),
                    0
                ) v
                FROM expenses
                """
            ).fetchone()["v"],

        "pending_bills":
            conn.execute(
                """
                SELECT
                COALESCE(
                    SUM(net_amount),
                    0
                ) v
                FROM bills
                WHERE status!='Paid'
                """
            ).fetchone()["v"],

        "payments":
            conn.execute(
                """
                SELECT
                COALESCE(
                    SUM(amount),
                    0
                ) v
                FROM payments
                """
            ).fetchone()["v"],
    }

    recent = conn.execute(
        """
        SELECT *
        FROM work_orders
        ORDER BY id DESC
        LIMIT 5
        """
    ).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        stats=stats,
        recent=recent
    )


# =========================================================
# MODULE DEFINITIONS
# =========================================================

MODULES = {

    "projects": (
        "Projects",
        "projects",
        [
            (
                "project_code",
                "Project Code",
                "text"
            ),
            (
                "project_name",
                "Project Name",
                "text"
            ),
            (
                "client",
                "Client",
                "text"
            ),
            (
                "location",
                "Location",
                "text"
            ),
            (
                "start_date",
                "Start Date",
                "date"
            ),
            (
                "end_date",
                "End Date",
                "date"
            ),
            (
                "contract_value",
                "Contract Value",
                "number"
            ),
            (
                "status",
                "Status",
                "select:Active|Completed|Hold"
            ),
            (
                "remarks",
                "Remarks",
                "textarea"
            ),
        ]
    ),

    "work-orders": (
        "Work Orders",
        "work_orders",
        [
            (
                "wo_no",
                "Work Order No.",
                "text"
            ),
            (
                "work_name",
                "Work Name",
                "text"
            ),
            (
                "project_id",
                "Project",
                "project"
            ),
            (
                "location",
                "Location",
                "text"
            ),
            (
                "wo_date",
                "WO Date",
                "date"
            ),
            (
                "po_no",
                "PO No.",
                "text"
            ),
            (
                "po_date",
                "PO Date",
                "date"
            ),
            (
                "start_date",
                "Start Date",
                "date"
            ),
            (
                "end_date",
                "End Date",
                "date"
            ),
            (
                "contract_value",
                "Contract Value",
                "number"
            ),
            (
                "status",
                "Status",
                "select:Active|Completed|Hold|Cancelled"
            ),
            (
                "remarks",
                "Remarks",
                "textarea"
            ),
        ]
    ),

    "vendors": (
        "Contractors / Vendors",
        "vendors",
        [
            (
                "vendor_code",
                "Vendor Code",
                "text"
            ),
            (
                "vendor_name",
                "Vendor Name",
                "text"
            ),
            (
                "contact",
                "Contact",
                "text"
            ),
            (
                "email",
                "Email",
                "email"
            ),
            (
                "gst_no",
                "GST No.",
                "text"
            ),
            (
                "bank_details",
                "Bank Details",
                "textarea"
            ),
            (
                "status",
                "Status",
                "select:Active|Inactive"
            ),
            (
                "remarks",
                "Remarks",
                "textarea"
            ),
        ]
    ),

    "employees": (
        "Employees / Workers",
        "employees",
        [
            (
                "emp_code",
                "Employee Code",
                "text"
            ),
            (
                "name",
                "Name",
                "text"
            ),
            (
                "designation",
                "Designation",
                "text"
            ),
            (
                "phone",
                "Phone",
                "text"
            ),
            (
                "joining_date",
                "Joining Date",
                "date"
            ),
            (
                "salary",
                "Salary",
                "number"
            ),
            (
                "project_id",
                "Project",
                "project"
            ),
            (
                "status",
                "Status",
                "select:Active|Inactive"
            ),
        ]
    ),

    "materials": (
        "Material / Inventory",
        "materials",
        [
            (
                "item_code",
                "Item Code",
                "text"
            ),
            (
                "item_name",
                "Item Name",
                "text"
            ),
            (
                "unit",
                "Unit",
                "text"
            ),
            (
                "qty",
                "Quantity",
                "number"
            ),
            (
                "rate",
                "Rate",
                "number"
            ),
            (
                "location",
                "Store / Site",
                "text"
            ),
            (
                "remarks",
                "Remarks",
                "textarea"
            ),
        ]
    ),

    "expenses": (
        "Site Expenses",
        "expenses",
        [
            (
                "expense_date",
                "Date",
                "date"
            ),
            (
                "project_id",
                "Project",
                "project"
            ),
            (
                "category",
                "Category",
                "select:Labour|Material|Transport|Fuel|Food|Accommodation|Other"
            ),
            (
                "description",
                "Description",
                "text"
            ),
            (
                "amount",
                "Amount",
                "number"
            ),
            (
                "paid_to",
                "Paid To",
                "text"
            ),
            (
                "payment_mode",
                "Payment Mode",
                "select:Cash|Bank|UPI|Cheque"
            ),
            (
                "remarks",
                "Remarks",
                "textarea"
            ),
        ]
    ),

    "billing": (
        "Billing",
        "bills",
        [
            (
                "bill_no",
                "Bill No.",
                "text"
            ),
            (
                "bill_date",
                "Bill Date",
                "date"
            ),
            (
                "project_id",
                "Project",
                "project"
            ),
            (
                "bill_type",
                "Bill Type",
                "select:Client RA Bill|Final Bill|Contractor Bill|Invoice"
            ),
            (
                "party_name",
                "Party Name",
                "text"
            ),
            (
                "gross_amount",
                "Gross Amount",
                "number"
            ),
            (
                "deductions",
                "Deductions",
                "number"
            ),
            (
                "net_amount",
                "Net Amount",
                "number"
            ),
            (
                "status",
                "Status",
                "select:Pending|Submitted|Approved|Paid|Rejected"
            ),
            (
                "remarks",
                "Remarks",
                "textarea"
            ),
        ]
    ),

    "payments": (
        "Payments / Receipts",
        "payments",
        [
            (
                "payment_no",
                "Voucher No.",
                "text"
            ),
            (
                "payment_date",
                "Date",
                "date"
            ),
            (
                "project_id",
                "Project",
                "project"
            ),
            (
                "party_name",
                "Party Name",
                "text"
            ),
            (
                "amount",
                "Amount",
                "number"
            ),
            (
                "mode",
                "Mode",
                "select:Cash|Bank|UPI|Cheque|NEFT|RTGS"
            ),
            (
                "reference_no",
                "Reference No.",
                "text"
            ),
            (
                "type",
                "Type",
                "select:Payment|Receipt"
            ),
            (
                "remarks",
                "Remarks",
                "textarea"
            ),
        ]
    ),
}


# =========================================================
# ROLE PERMISSIONS
# =========================================================

ROLE_ACCESS = {

    "Admin": [
        "projects",
        "work-orders",
        "vendors",
        "employees",
        "materials",
        "expenses",
        "billing",
        "payments",
    ],

    "Project Manager": [
        "projects",
        "work-orders",
        "vendors",
        "employees",
        "materials",
    ],

    "Accounts": [
        "projects",
        "expenses",
        "billing",
        "payments",
    ],

    "Store": [
        "projects",
        "materials",
    ],

    "Site User": [
        "projects",
        "work-orders",
        "employees",
        "materials",
        "expenses",
    ],
}


def module_allowed(slug):

    role = session.get(
        "role",
        ""
    )

    if role == "Admin":
        return True

    return slug in ROLE_ACCESS.get(
        role,
        []
    )


# =========================================================
# MODULE PAGE
# =========================================================

@app.route(
    "/module/<slug>",
    methods=["GET", "POST"]
)
@login_required
def module(slug):

    if slug not in MODULES:
        return "Not found", 404

    if not module_allowed(slug):

        flash(
            "You do not have permission "
            "to access this module.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    title, table, fields = (
        MODULES[slug]
    )

    conn = db()

    if request.method == "POST":

        cols = []
        vals = []

        for name, label, typ in fields:

            cols.append(name)

            val = request.form.get(
                name,
                ""
            )

            if typ == "number":

                try:
                    val = float(
                        val or 0
                    )

                except ValueError:
                    val = 0

            vals.append(val)

        try:

            sql = (
                f"INSERT INTO {table} "
                f"({','.join(cols)}) "
                f"VALUES "
                f"({','.join(['?'] * len(cols))})"
            )

            conn.execute(
                sql,
                vals
            )

            conn.commit()

            flash(
                "Record saved successfully.",
                "success"
            )

        except sqlite3.IntegrityError:

            flash(
                "Duplicate code/number. "
                "Please use a unique value.",
                "danger"
            )

        conn.close()

        return redirect(
            url_for(
                "module",
                slug=slug
            )
        )

    rows = conn.execute(
        f"""
        SELECT *
        FROM {table}
        ORDER BY id DESC
        """
    ).fetchall()

    projects = conn.execute(
        """
        SELECT
            id,
            project_code,
            project_name
        FROM projects
        ORDER BY project_name
        """
    ).fetchall()

    conn.close()

    return render_template(
        "module.html",
        title=title,
        table=table,
        fields=fields,
        slug=slug,
        rows=rows,
        projects=projects
    )


# =========================================================
# DELETE RECORD
# =========================================================

@app.route(
    "/module/<slug>/delete/<int:id>",
    methods=["POST"]
)
@login_required
def delete_record(
    slug,
    id
):

    if slug not in MODULES:
        return "Not found", 404

    if not module_allowed(slug):

        flash(
            "Permission denied.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    title, table, fields = (
        MODULES[slug]
    )

    conn = db()

    conn.execute(
        f"""
        DELETE FROM {table}
        WHERE id=?
        """,
        (id,)
    )

    conn.commit()
    conn.close()

    flash(
        "Record deleted.",
        "success"
    )

    return redirect(
        url_for(
            "module",
            slug=slug
        )
    )


# =========================================================
# PRINT WORK ORDER
# =========================================================

@app.route(
    "/work-order/<int:id>/print"
)
@login_required
def print_work_order(id):

    conn = db()

    wo = conn.execute(
        """
        SELECT
            w.*,
            p.project_code,
            p.project_name
        FROM work_orders w
        LEFT JOIN projects p
        ON p.id=w.project_id
        WHERE w.id=?
        """,
        (id,)
    ).fetchone()

    conn.close()

    if not wo:
        return "Not found", 404

    return render_template(
        "print_work_order.html",
        wo=wo
    )


# =========================================================
# REPORTS
# =========================================================

@app.route("/reports")
@login_required
def reports():

    conn = db()

    rows = conn.execute(
        """
        SELECT
            p.project_code,
            p.project_name,
            p.client,
            p.location,
            p.contract_value,

            COALESCE(
                (
                    SELECT SUM(amount)
                    FROM expenses e
                    WHERE e.project_id=p.id
                ),
                0
            ) expenses,

            COALESCE(
                (
                    SELECT SUM(net_amount)
                    FROM bills b
                    WHERE b.project_id=p.id
                ),
                0
            ) billed,

            COALESCE(
                (
                    SELECT SUM(amount)
                    FROM payments x
                    WHERE
                        x.project_id=p.id
                        AND x.type='Receipt'
                ),
                0
            ) receipts

        FROM projects p

        ORDER BY p.id DESC
        """
    ).fetchall()

    conn.close()

    return render_template(
        "reports.html",
        rows=rows
    )


# =========================================================
# EXPORT CSV
# =========================================================

@app.route("/export/<slug>")
@login_required
def export_csv(slug):

    if slug not in MODULES:
        return "Not found", 404

    if not module_allowed(slug):

        return "Permission denied", 403

    title, table, fields = (
        MODULES[slug]
    )

    conn = db()

    rows = conn.execute(
        f"""
        SELECT *
        FROM {table}
        ORDER BY id
        """
    ).fetchall()

    conn.close()

    output = io.StringIO()

    writer = csv.writer(output)

    if rows:

        writer.writerow(
            rows[0].keys()
        )

        for r in rows:

            writer.writerow(
                list(r)
            )

    mem = io.BytesIO(
        output.getvalue().encode(
            "utf-8-sig"
        )
    )

    mem.seek(0)

    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"{slug}.csv"
    )


# =========================================================
# USER MANAGEMENT
# =========================================================

@app.route(
    "/users",
    methods=["GET", "POST"]
)
@admin_required
def users():

    conn = db()

    if request.method == "POST":

        username = (
            request.form.get(
                "username",
                ""
            )
            .strip()
            .lower()
        )

        password = (
            request.form.get(
                "password",
                ""
            )
        )

        role = request.form.get(
            "role",
            "Site User"
        )

        allowed_roles = [
            "Admin",
            "Project Manager",
            "Accounts",
            "Store",
            "Site User",
        ]

        if not username:

            flash(
                "Username is required.",
                "danger"
            )

        elif len(password) < 6:

            flash(
                "Password must contain "
                "at least 6 characters.",
                "danger"
            )

        elif role not in allowed_roles:

            flash(
                "Invalid role.",
                "danger"
            )

        else:

            try:

                conn.execute(
                    """
                    INSERT INTO users
                    (
                        username,
                        password_hash,
                        role,
                        active
                    )
                    VALUES(?,?,?,1)
                    """,
                    (
                        username,
                        generate_password_hash(
                            password
                        ),
                        role
                    )
                )

                conn.commit()

                flash(
                    "User account created.",
                    "success"
                )

            except sqlite3.IntegrityError:

                flash(
                    "Username already exists.",
                    "danger"
                )

        conn.close()

        return redirect(
            url_for("users")
        )

    user_rows = conn.execute(
        """
        SELECT
            id,
            username,
            role,
            active
        FROM users
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    return render_template(
        "users.html",
        users=user_rows
    )


# =========================================================
# USER ACTIVE / INACTIVE
# =========================================================

@app.route(
    "/users/<int:user_id>/toggle",
    methods=["POST"]
)
@admin_required
def toggle_user(user_id):

    conn = db()

    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE id=?
        """,
        (user_id,)
    ).fetchone()

    if not user:

        conn.close()
        return "User not found", 404

    if user["username"] == "admin":

        conn.close()

        flash(
            "Main admin account "
            "cannot be disabled.",
            "danger"
        )

        return redirect(
            url_for("users")
        )

    new_status = (
        0
        if user["active"]
        else 1
    )

    conn.execute(
        """
        UPDATE users
        SET active=?
        WHERE id=?
        """,
        (
            new_status,
            user_id
        )
    )

    conn.commit()
    conn.close()

    flash(
        "User status updated.",
        "success"
    )

    return redirect(
        url_for("users")
    )


# =========================================================
# RESET USER PASSWORD
# =========================================================

@app.route(
    "/users/<int:user_id>/password",
    methods=["POST"]
)
@admin_required
def reset_user_password(user_id):

    new_password = request.form.get(
        "new_password",
        ""
    )

    if len(new_password) < 6:

        flash(
            "Password must contain "
            "at least 6 characters.",
            "danger"
        )

        return redirect(
            url_for("users")
        )

    conn = db()

    conn.execute(
        """
        UPDATE users
        SET password_hash=?
        WHERE id=?
        """,
        (
            generate_password_hash(
                new_password
            ),
            user_id
        )
    )

    conn.commit()
    conn.close()

    flash(
        "Password updated.",
        "success"
    )

    return redirect(
        url_for("users")
    )


# =========================================================
# START DATABASE
# =========================================================

init_db()


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),
        debug=False
)
