"""FastAPI application for Indiana Hotel Booking."""
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from db import get_connection
from security_utils import hash_password, verify_password

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app = FastAPI(title="Indiana Hotel Booking")
app.add_middleware(SessionMiddleware, secret_key="indiana-hotel-dev-secret")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

DEFAULT_CLIENT_SEARCH = {"checkin": "", "checkout": "", "rtype_id": "", "pets": "0"}
DEFAULT_SIGNUP_FORM = {
    "account_type": "CLIENT",
    "fname": "",
    "lname": "",
    "dob": "",
    "mail": "",
    "phone": "",
    "street": "",
    "city": "",
    "state": "",
    "zip": "",
    "emp_role": "Front Desk",
}
DEFAULT_PROFILE_FORM = {
    "client_id": 1,
    "fname": "",
    "lname": "",
    "dob": "",
    "mail": "",
    "phone": "",
    "street": "",
    "city": "",
    "state": "",
    "zip": "",
}
DEFAULT_RES_DASH_FORM = {"room_number": "101", "res_date": ""}
DEFAULT_HK_DASH_FORM = {"room_number": "102", "clean_date": ""}
ACTIVE_RESERVATION_STATUSES = ("Canceled", "Checked-Out")


def get_current_user(request: Request) -> dict | None:
    user = request.session.get("user")
    return user if isinstance(user, dict) else None


def is_manager(user: dict | None) -> bool:
    return bool(
        user
        and user.get("account_type") == "EMPLOYEE"
        and str(user.get("role", "")).lower() == "manager"
    )


def close_connection(conn) -> None:
    if conn is not None and conn.is_connected():
        conn.close()


def rollback_connection(conn) -> None:
    if conn is not None and conn.is_connected():
        conn.rollback()


def render_template(request: Request, template_name: str, **context):
    context.setdefault("user", get_current_user(request))
    return templates.TemplateResponse(request, template_name, context)


def require_login(request: Request):
    return None if get_current_user(request) else RedirectResponse(url="/login", status_code=303)


def require_client(request: Request):
    deny = require_login(request)
    if deny:
        return deny, None
    user = get_current_user(request)
    if not user or user.get("account_type") != "CLIENT":
        return RedirectResponse(url="/login", status_code=303), None
    return None, user


def parse_date_str(value: str):
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_stay_dates(checkin: str, checkout: str):
    return parse_date_str(checkin), parse_date_str(checkout)


def within_48h_of_checkin(checkin_date) -> bool:
    checkin_dt = datetime.combine(checkin_date, datetime.min.time())
    return datetime.now() > (checkin_dt - timedelta(hours=48))


def load_profile_data(client_id: int = 1) -> dict:
    profile = dict(DEFAULT_PROFILE_FORM)
    profile["client_id"] = client_id
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT c.CLIENT_ID, c.CLIENT_FNAME, c.CLIENT_LNAME, c.CLIENT_DOB, c.CLIENT_EMAIL, c.CLIENT_PHONE,
                   c.CLIENT_STREET, z.ZIP_CODE, z.ZIP_CITY, z.ZIP_STATE
            FROM CLIENT c
            LEFT JOIN ZIP z ON z.ZIP_CODE = c.ZIP_CODE
            WHERE c.CLIENT_ID = %s
            """,
            (client_id,),
        )
        row = cur.fetchone()
        cur.close()
        if not row:
            return profile
        profile.update(
            {
                "client_id": row["CLIENT_ID"],
                "fname": row["CLIENT_FNAME"] or "",
                "lname": row["CLIENT_LNAME"] or "",
                "dob": row["CLIENT_DOB"].isoformat() if row["CLIENT_DOB"] else "",
                "mail": row["CLIENT_EMAIL"] or "",
                "phone": row["CLIENT_PHONE"] or "",
                "street": row["CLIENT_STREET"] or "",
                "city": row["ZIP_CITY"] or "",
                "state": row["ZIP_STATE"] or "",
                "zip": row["ZIP_CODE"] or "",
            }
        )
        return profile
    except Exception:
        return profile
    finally:
        close_connection(conn)


def get_client_reservations(client_id: int) -> list:
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT r.RES_ID, r.RES_DATE, r.RES_CHECKIN, r.RES_CHECKOUT, r.RES_QUOTED_RATE, r.RES_STATUS,
                   rm.ROOM_NUMBER, rt.RTYPE_NAME
            FROM RESERVATION r
            JOIN ROOM rm ON rm.ROOM_ID = r.ROOM_ID
            JOIN ROOMTYPE rt ON rt.RTYPE_ID = rm.RTYPE_ID
            WHERE r.CLIENT_ID = %s
            ORDER BY r.RES_CHECKIN DESC, r.RES_ID DESC
            """,
            (client_id,),
        )
        rows = cur.fetchall()
        cur.close()
        return rows
    except Exception:
        return []
    finally:
        close_connection(conn)


def render_signup_page(request: Request, feedback: str = "", ok: bool = True, form_data: dict | None = None):
    user = get_current_user(request)
    return render_template(
        request,
        "Registration_UI.html",
        feedback=feedback,
        ok=ok,
        form_data=form_data or dict(DEFAULT_SIGNUP_FORM),
        can_create_employee=is_manager(user),
    )


def render_login_page(request: Request, feedback: str = "", ok: bool = True):
    return render_template(request, "Login_UI.html", feedback=feedback, ok=ok)


def render_forgot_password_page(request: Request, feedback: str = "", ok: bool = True):
    return render_template(request, "ForgotPassword_UI.html", feedback=feedback, ok=ok)


def render_profile_page(
    request: Request,
    feedback: str = "",
    ok: bool = True,
    form_data: dict | None = None,
    client_id: int = 1,
):
    return render_template(
        request,
        "Update_Profile_Info.html",
        feedback=feedback,
        ok=ok,
        form_data=form_data or load_profile_data(client_id),
    )


def render_reservation_page(
    request: Request,
    feedback: str = "",
    ok: bool = True,
    form_data: dict | None = None,
    reservation_info: dict | None = None,
):
    return render_template(
        request,
        "Reservation_Dashboard.html",
        feedback=feedback,
        ok=ok,
        form_data=form_data or dict(DEFAULT_RES_DASH_FORM),
        reservation_info=reservation_info or {},
    )


def render_housekeeping_page(
    request: Request,
    feedback: str = "",
    ok: bool = True,
    form_data: dict | None = None,
    room_info: dict | None = None,
):
    return render_template(
        request,
        "Housekeeping_Dashboard.html",
        feedback=feedback,
        ok=ok,
        form_data=form_data or dict(DEFAULT_HK_DASH_FORM),
        room_info=room_info or {},
    )


def render_client_page(
    request: Request,
    user: dict,
    feedback: str = "",
    ok: bool = True,
    search_data: dict | None = None,
    available_rooms: list | None = None,
    reservations: list | None = None,
):
    search_context = dict(DEFAULT_CLIENT_SEARCH)
    if search_data:
        search_context.update(search_data)
    if reservations is None:
        reservations = get_client_reservations(int(user["id"]))
    return render_template(
        request,
        "Client_Reservation_UI.html",
        feedback=feedback,
        ok=ok,
        search_data=search_context,
        available_rooms=available_rooms or [],
        reservations=reservations,
    )


@app.get("/", response_class=HTMLResponse)
@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return render_signup_page(request)


@app.post("/signup", response_class=HTMLResponse)
def signup_create_page(
    request: Request,
    account_type: str = Form("CLIENT"),
    fname: str = Form(""),
    lname: str = Form(""),
    dob: str = Form(""),
    mail: str = Form(""),
    phone: str = Form(""),
    street: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    zip: str = Form(""),
    emp_role: str = Form("Front Desk"),
    password: str = Form(""),
    confirm_password: str = Form(""),
):
    form_data = {
        "account_type": account_type.upper(),
        "fname": fname,
        "lname": lname,
        "dob": dob,
        "mail": mail,
        "phone": phone,
        "street": street,
        "city": city,
        "state": state,
        "zip": zip,
        "emp_role": emp_role,
    }
    if not password:
        return render_signup_page(request, feedback="Password is required.", ok=False, form_data=form_data)
    if password != confirm_password:
        return render_signup_page(request, feedback="Passwords do not match.", ok=False, form_data=form_data)
    if form_data["account_type"] == "EMPLOYEE" and not is_manager(get_current_user(request)):
        return render_signup_page(
            request,
            feedback="Only a logged-in manager can create employee signups.",
            ok=False,
            form_data=form_data,
        )

    conn = None
    try:
        pw_hash = hash_password(password)
        conn = get_connection()
        cur = conn.cursor()
        if form_data["account_type"] == "EMPLOYEE":
            cur.execute(
                "INSERT INTO EMPLOYEE (EMP_FNAME, EMP_LNAME, EMP_ROLE, EMP_EMAIL, EMP_PASSWORD) VALUES (%s, %s, %s, %s, %s)",
                (fname, lname, emp_role, mail, pw_hash),
            )
            conn.commit()
            cur.close()
            return render_signup_page(
                request,
                feedback="Employee account created successfully.",
                ok=True,
                form_data=dict(DEFAULT_SIGNUP_FORM),
            )

        cur.execute(
            "INSERT INTO ZIP (ZIP_CODE, ZIP_CITY, ZIP_STATE) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE ZIP_CITY = VALUES(ZIP_CITY), ZIP_STATE = VALUES(ZIP_STATE)",
            (zip, city, state),
        )
        cur.execute(
            "INSERT INTO CLIENT (CLIENT_FNAME, CLIENT_LNAME, CLIENT_DOB, CLIENT_EMAIL, CLIENT_PASSWORD, "
            "CLIENT_PHONE, CLIENT_STREET, ZIP_CODE) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (fname, lname, dob or None, mail, pw_hash, phone, street, zip),
        )
        conn.commit()
        cur.close()
        return render_signup_page(
            request,
            feedback="Client account created successfully.",
            ok=True,
            form_data=dict(DEFAULT_SIGNUP_FORM),
        )
    except Exception as e:
        rollback_connection(conn)
        return render_signup_page(
            request,
            feedback="Signup failed. Please verify your details and try again.",
            ok=False,
            form_data=form_data,
        )
    finally:
        close_connection(conn)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return render_login_page(request)


@app.post("/login", response_class=HTMLResponse)
def login_submit_page(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    account_type: str = Form("CLIENT"),
):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        if account_type.upper() == "EMPLOYEE":
            cur.execute(
                "SELECT EMP_ID, EMP_FNAME, EMP_LNAME, EMP_ROLE, EMP_EMAIL, EMP_PASSWORD "
                "FROM EMPLOYEE WHERE EMP_EMAIL = %s LIMIT 1",
                (email,),
            )
            row = cur.fetchone()
            cur.close()
            if not row:
                return render_login_page(request, feedback="Employee login failed: email not found.", ok=False)
            if not verify_password(password, row.get("EMP_PASSWORD")):
                return render_login_page(request, feedback="Employee login failed: invalid password.", ok=False)
            request.session["user"] = {
                "account_type": "EMPLOYEE",
                "id": row["EMP_ID"],
                "email": row["EMP_EMAIL"],
                "name": f"{row['EMP_FNAME']} {row['EMP_LNAME']}".strip(),
                "role": row["EMP_ROLE"] or "",
            }
            return RedirectResponse(
                url="/signup" if str(row["EMP_ROLE"] or "").lower() == "manager" else "/Reservation_Dashboard",
                status_code=303,
            )

        cur.execute(
            "SELECT CLIENT_ID, CLIENT_FNAME, CLIENT_LNAME, CLIENT_EMAIL, CLIENT_PASSWORD "
            "FROM CLIENT WHERE CLIENT_EMAIL = %s LIMIT 1",
            (email,),
        )
        row = cur.fetchone()
        cur.close()
        if not row:
            return render_login_page(request, feedback="Client login failed: email not found.", ok=False)
        if not verify_password(password, row.get("CLIENT_PASSWORD")):
            return render_login_page(request, feedback="Client login failed: invalid password.", ok=False)
        request.session["user"] = {
            "account_type": "CLIENT",
            "id": row["CLIENT_ID"],
            "email": row["CLIENT_EMAIL"],
            "name": f"{row['CLIENT_FNAME']} {row['CLIENT_LNAME']}".strip(),
            "role": "CLIENT",
        }
        return RedirectResponse(url="/client-reservations", status_code=303)
    except Exception as e:
        return render_login_page(request, feedback="Login failed. Please try again.", ok=False)
    finally:
        close_connection(conn)


@app.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(request: Request):
    return render_forgot_password_page(request)


@app.post("/forgot-password", response_class=HTMLResponse)
def forgot_password_submit_page(request: Request, email: str = Form("")):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT CLIENT_ID FROM CLIENT WHERE CLIENT_EMAIL = %s LIMIT 1", (email,))
        client = cur.fetchone()
        cur.execute("SELECT EMP_ID FROM EMPLOYEE WHERE EMP_EMAIL = %s LIMIT 1", (email,))
        employee = cur.fetchone()
        cur.close()
        if not client and not employee:
            return render_forgot_password_page(request, feedback="No account found for that email.", ok=False)
        return render_forgot_password_page(
            request,
            feedback="Email found. Please contact the front desk to reset your password.",
            ok=True,
        )
    except Exception as e:
        return render_forgot_password_page(
            request,
            feedback="Unable to process your request right now. Please try again.",
            ok=False,
        )
    finally:
        close_connection(conn)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/Update_Profile_Info", response_class=HTMLResponse)
def profile_page(request: Request, client_id: int = 1):
    deny = require_login(request)
    if deny:
        return deny
    user = get_current_user(request)
    if user and user.get("account_type") == "CLIENT":
        client_id = int(user["id"])
    return render_profile_page(request, client_id=client_id)


@app.post("/Update_Profile_Info", response_class=HTMLResponse)
def profile_update_page(
    request: Request,
    client_id: int = Form(1),
    fname: str = Form(""),
    lname: str = Form(""),
    dob: str = Form(""),
    mail: str = Form(""),
    phone: str = Form(""),
    street: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    zip: str = Form(""),
):
    deny = require_login(request)
    if deny:
        return deny
    user = get_current_user(request)
    if user and user.get("account_type") == "CLIENT":
        client_id = int(user["id"])
    form_data = {
        "client_id": client_id,
        "fname": fname,
        "lname": lname,
        "dob": dob,
        "mail": mail,
        "phone": phone,
        "street": street,
        "city": city,
        "state": state,
        "zip": zip,
    }

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO ZIP (ZIP_CODE, ZIP_CITY, ZIP_STATE) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE ZIP_CITY = VALUES(ZIP_CITY), ZIP_STATE = VALUES(ZIP_STATE)",
            (zip, city, state),
        )
        cur.execute(
            """
            UPDATE CLIENT
            SET CLIENT_FNAME = %s, CLIENT_LNAME = %s, CLIENT_DOB = %s, CLIENT_EMAIL = %s,
                CLIENT_PHONE = %s, CLIENT_STREET = %s, ZIP_CODE = %s
            WHERE CLIENT_ID = %s
            """,
            (fname, lname, dob or None, mail, phone, street, zip, client_id),
        )
        if cur.rowcount == 0:
            cur.close()
            return render_profile_page(
                request,
                feedback="Account not found. Please sign up first.",
                ok=False,
                form_data=form_data,
            )
        conn.commit()
        cur.close()
        return render_profile_page(
            request,
            feedback="Profile updated successfully.",
            ok=True,
            form_data=form_data,
        )
    except Exception as e:
        rollback_connection(conn)
        return render_profile_page(
            request,
            feedback="Profile update failed. Please try again.",
            ok=False,
            form_data=form_data,
        )
    finally:
        close_connection(conn)


@app.get("/client-reservations", response_class=HTMLResponse)
@app.get("/Client_Reservation_UI", response_class=HTMLResponse)
def client_reservation_page(request: Request):
    deny, user = require_client(request)
    return deny or render_client_page(request, user)


@app.post("/client-reservations/search", response_class=HTMLResponse)
def client_reservation_search(
    request: Request,
    checkin: str = Form(""),
    checkout: str = Form(""),
    rtype_id: str = Form(""),
    pets: int = Form(0),
):
    deny, user = require_client(request)
    if deny:
        return deny
    search_data = {"checkin": checkin, "checkout": checkout, "rtype_id": rtype_id, "pets": str(pets)}
    try:
        in_date, out_date = parse_stay_dates(checkin, checkout)
        if out_date < in_date:
            return render_client_page(
                request,
                user,
                feedback="Checkout date must be after check-in date.",
                ok=False,
                search_data=search_data,
            )
    except Exception:
        return render_client_page(
            request,
            user,
            feedback="Invalid dates provided.",
            ok=False,
            search_data=search_data,
        )

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT rm.ROOM_ID, rm.ROOM_NUMBER, rm.ROOM_STATUS, rt.RTYPE_ID, rt.RTYPE_NAME, rt.RTYPE_PRICE, rt.RTYPE_CAP
            FROM ROOM rm
            JOIN ROOMTYPE rt ON rt.RTYPE_ID = rm.RTYPE_ID
            WHERE (%s = '' OR rt.RTYPE_ID = %s)
              AND NOT EXISTS (
                SELECT 1 FROM RESERVATION r
                WHERE r.ROOM_ID = rm.ROOM_ID
                  AND r.RES_STATUS NOT IN ('Canceled', 'Checked-Out')
                  AND NOT (r.RES_CHECKOUT < %s OR r.RES_CHECKIN > %s)
              )
            ORDER BY rm.ROOM_NUMBER
            """,
            (rtype_id, rtype_id, in_date, out_date),
        )
        available = cur.fetchall()
        cur.close()
        return render_client_page(
            request,
            user,
            feedback="Available rooms loaded." if available else "No rooms available for that criteria.",
            ok=bool(available),
            search_data=search_data,
            available_rooms=available,
        )
    except Exception as e:
        return render_client_page(
            request,
            user,
            feedback="Search failed. Please try different dates.",
            ok=False,
            search_data=search_data,
        )
    finally:
        close_connection(conn)


@app.post("/client-reservations/book", response_class=HTMLResponse)
def client_reservation_book(
    request: Request,
    room_id: int = Form(...),
    checkin: str = Form(...),
    checkout: str = Form(...),
):
    deny, user = require_client(request)
    if deny:
        return deny
    client_id = int(user["id"])
    search_data = {"checkin": checkin, "checkout": checkout}
    try:
        in_date, out_date = parse_stay_dates(checkin, checkout)
    except Exception:
        return render_client_page(
            request,
            user,
            feedback="Invalid dates for booking.",
            ok=False,
            search_data=search_data,
        )

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT rm.ROOM_ID, rm.ROOM_NUMBER, rt.RTYPE_PRICE
            FROM ROOM rm
            JOIN ROOMTYPE rt ON rt.RTYPE_ID = rm.RTYPE_ID
            WHERE rm.ROOM_ID = %s
            FOR UPDATE
            """,
            (room_id,),
        )
        room = cur.fetchone()
        if not room:
            cur.close()
            return render_client_page(request, user, feedback="Room not found.", ok=False, search_data=search_data)

        cur.execute(
            """
            SELECT RES_ID FROM RESERVATION
            WHERE ROOM_ID = %s
              AND RES_STATUS NOT IN ('Canceled', 'Checked-Out')
              AND NOT (RES_CHECKOUT < %s OR RES_CHECKIN > %s)
            LIMIT 1
            """,
            (room_id, in_date, out_date),
        )
        if cur.fetchone():
            rollback_connection(conn)
            cur.close()
            return render_client_page(
                request,
                user,
                feedback="That room is already reserved for selected dates.",
                ok=False,
                search_data=search_data,
            )

        write_cur = conn.cursor()
        write_cur.execute(
            """
            INSERT INTO RESERVATION (CLIENT_ID, ROOM_ID, RES_DATE, RES_CHECKIN, RES_CHECKOUT, RES_QUOTED_RATE, RES_STATUS)
            VALUES (%s, %s, NOW(), %s, %s, %s, %s)
            """,
            (client_id, room_id, in_date, out_date, room["RTYPE_PRICE"], "Booked"),
        )
        res_id = write_cur.lastrowid
        write_cur.execute("UPDATE ROOM SET ROOM_STATUS = %s WHERE ROOM_ID = %s", ("Reserved", room_id))
        conn.commit()
        write_cur.close()
        cur.close()
        return render_client_page(
            request,
            user,
            feedback=f"Reservation created successfully (RES_ID {res_id}).",
            ok=True,
            search_data=dict(DEFAULT_CLIENT_SEARCH),
        )
    except Exception as e:
        rollback_connection(conn)
        return render_client_page(
            request,
            user,
            feedback="Booking failed. Please try again.",
            ok=False,
            search_data=search_data,
        )
    finally:
        close_connection(conn)


@app.post("/client-reservations/modify", response_class=HTMLResponse)
def client_reservation_modify(
    request: Request,
    res_id: int = Form(...),
    checkin: str = Form(...),
    checkout: str = Form(...),
):
    deny, user = require_client(request)
    if deny:
        return deny
    client_id = int(user["id"])
    try:
        in_date, out_date = parse_stay_dates(checkin, checkout)
    except Exception:
        return render_client_page(request, user, feedback="Invalid dates for modify.", ok=False)

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT RES_ID, ROOM_ID, RES_CHECKIN, RES_STATUS FROM RESERVATION WHERE RES_ID = %s AND CLIENT_ID = %s LIMIT 1",
            (res_id, client_id),
        )
        reservation = cur.fetchone()
        if not reservation:
            cur.close()
            return render_client_page(request, user, feedback="Reservation not found for this client.", ok=False)
        if reservation["RES_STATUS"] in ACTIVE_RESERVATION_STATUSES:
            cur.close()
            return render_client_page(request, user, feedback="Only active reservations can be modified.", ok=False)
        if within_48h_of_checkin(reservation["RES_CHECKIN"]):
            cur.close()
            return render_client_page(
                request,
                user,
                feedback="Cannot modify reservation within 48 hours of check-in.",
                ok=False,
            )

        cur.execute(
            """
            SELECT RES_ID FROM RESERVATION
            WHERE ROOM_ID = %s
              AND RES_ID <> %s
              AND RES_STATUS NOT IN ('Canceled', 'Checked-Out')
              AND NOT (RES_CHECKOUT < %s OR RES_CHECKIN > %s)
            LIMIT 1
            """,
            (reservation["ROOM_ID"], res_id, in_date, out_date),
        )
        if cur.fetchone():
            cur.close()
            return render_client_page(
                request,
                user,
                feedback="Modified dates conflict with another active reservation.",
                ok=False,
            )

        write_cur = conn.cursor()
        write_cur.execute(
            "UPDATE RESERVATION SET RES_CHECKIN = %s, RES_CHECKOUT = %s, RES_DATE = NOW() WHERE RES_ID = %s",
            (in_date, out_date, res_id),
        )
        conn.commit()
        write_cur.close()
        cur.close()
        return render_client_page(request, user, feedback=f"Reservation {res_id} updated successfully.", ok=True)
    except Exception as e:
        rollback_connection(conn)
        return render_client_page(request, user, feedback="Unable to modify reservation. Please try again.", ok=False)
    finally:
        close_connection(conn)


@app.post("/client-reservations/cancel", response_class=HTMLResponse)
def client_reservation_cancel(request: Request, res_id: int = Form(...)):
    deny, user = require_client(request)
    if deny:
        return deny
    client_id = int(user["id"])
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT RES_ID, ROOM_ID, RES_CHECKIN, RES_STATUS FROM RESERVATION WHERE RES_ID = %s AND CLIENT_ID = %s LIMIT 1",
            (res_id, client_id),
        )
        reservation = cur.fetchone()
        if not reservation:
            cur.close()
            return render_client_page(request, user, feedback="Reservation not found for this client.", ok=False)
        if reservation["RES_STATUS"] in ACTIVE_RESERVATION_STATUSES:
            cur.close()
            return render_client_page(request, user, feedback="Reservation is already closed.", ok=False)
        if within_48h_of_checkin(reservation["RES_CHECKIN"]):
            cur.close()
            return render_client_page(
                request,
                user,
                feedback="Cannot cancel reservation within 48 hours of check-in.",
                ok=False,
            )

        write_cur = conn.cursor()
        write_cur.execute("UPDATE RESERVATION SET RES_STATUS = %s WHERE RES_ID = %s", ("Canceled", res_id))
        write_cur.execute("UPDATE ROOM SET ROOM_STATUS = %s WHERE ROOM_ID = %s", ("Available", reservation["ROOM_ID"]))
        conn.commit()
        write_cur.close()
        cur.close()
        return render_client_page(request, user, feedback=f"Reservation {res_id} canceled.", ok=True)
    except Exception as e:
        rollback_connection(conn)
        return render_client_page(request, user, feedback="Unable to cancel reservation. Please try again.", ok=False)
    finally:
        close_connection(conn)


@app.get("/Reservation_Dashboard", response_class=HTMLResponse)
def reservation_dashboard_page(request: Request):
    return render_reservation_page(request)


@app.post("/Reservation_Dashboard", response_class=HTMLResponse)
def reservation_action_page(
    request: Request,
    room_number: int = Form(...),
    res_date: str = Form(...),
    reservation_action: str = Form(...),
):
    form_data = {"room_number": str(room_number), "res_date": res_date}
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT ROOM_ID FROM ROOM WHERE ROOM_NUMBER = %s", (room_number,))
        room = cur.fetchone()
        if not room:
            cur.close()
            return render_reservation_page(
                request,
                feedback=f"Room {room_number} not found.",
                ok=False,
                form_data=form_data,
            )

        cur.execute(
            """
            SELECT RES_ID, RES_CHECKIN, RES_CHECKOUT, RES_STATUS
            FROM RESERVATION
            WHERE ROOM_ID = %s AND %s BETWEEN RES_CHECKIN AND RES_CHECKOUT
            ORDER BY RES_DATE DESC
            LIMIT 1
            """,
            (room["ROOM_ID"], res_date),
        )
        reservation = cur.fetchone()
        if not reservation:
            cur.close()
            return render_reservation_page(
                request,
                feedback=f"No reservation found for room {room_number} on {res_date}.",
                ok=False,
                form_data=form_data,
            )

        if reservation_action == "checkin":
            new_res_status, new_room_status, action_label = "Checked-In", "Occupied", "Check-In"
        else:
            new_res_status, new_room_status, action_label = "Checked-Out", "Available", "Check-Out"

        write_cur = conn.cursor()
        write_cur.execute("UPDATE RESERVATION SET RES_STATUS = %s WHERE RES_ID = %s", (new_res_status, reservation["RES_ID"]))
        write_cur.execute("UPDATE ROOM SET ROOM_STATUS = %s WHERE ROOM_ID = %s", (new_room_status, room["ROOM_ID"]))
        conn.commit()
        write_cur.close()
        cur.close()
        return render_reservation_page(
            request,
            feedback=f"{action_label} successful for room {room_number} (RES_ID {reservation['RES_ID']}).",
            ok=True,
            form_data=form_data,
            reservation_info={
                "reservation_id": reservation["RES_ID"],
                "reservation_status": new_res_status,
                "room_status": new_room_status,
            },
        )
    except Exception as e:
        rollback_connection(conn)
        return render_reservation_page(
            request,
            feedback="Unable to complete that action. Please try again.",
            ok=False,
            form_data=form_data,
        )
    finally:
        close_connection(conn)


@app.get("/Housekeeping_Dashboard", response_class=HTMLResponse)
def housekeeping_dashboard_page(request: Request):
    return render_housekeeping_page(request)


@app.post("/Housekeeping_Dashboard", response_class=HTMLResponse)
def housekeeping_action_page(
    request: Request,
    room_number: int = Form(...),
    clean_date: str = Form(...),
    housekeeping_action: str = Form(...),
):
    form_data = {"room_number": str(room_number), "clean_date": clean_date}
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT ROOM_ID FROM ROOM WHERE ROOM_NUMBER = %s", (room_number,))
        room = cur.fetchone()
        if not room:
            cur.close()
            return render_housekeeping_page(
                request,
                feedback=f"Room {room_number} not found.",
                ok=False,
                form_data=form_data,
            )

        cur.execute(
            """
            SELECT RES_ID, RES_STATUS
            FROM RESERVATION
            WHERE ROOM_ID = %s AND %s BETWEEN RES_CHECKIN AND RES_CHECKOUT
            ORDER BY RES_DATE DESC
            LIMIT 1
            """,
            (room["ROOM_ID"], clean_date),
        )
        reservation = cur.fetchone()
        cur.execute("SELECT EMP_ID FROM EMPLOYEE WHERE LOWER(EMP_ROLE) LIKE 'housekeeper%' LIMIT 1")
        employee = cur.fetchone()
        emp_id = employee["EMP_ID"] if employee else None

        if housekeeping_action == "clean":
            new_room_status, log_action = "Available", "Clean"
        else:
            new_room_status, log_action = "Needs Service", "Needs Service"

        log_dt = datetime.strptime(clean_date, "%Y-%m-%d").replace(hour=10, minute=0, second=0)
        write_cur = conn.cursor()
        write_cur.execute("UPDATE ROOM SET ROOM_STATUS = %s WHERE ROOM_ID = %s", (new_room_status, room["ROOM_ID"]))
        write_cur.execute(
            """
            INSERT INTO HOUSEKEEPINGLOG (ROOM_ID, EMP_ID, LOG_DATE, LOG_ACTION, LOG_NOTE)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                room["ROOM_ID"],
                emp_id,
                log_dt.strftime("%Y-%m-%d %H:%M:%S"),
                log_action,
                f"Updated from UI. Reservation on date: {reservation['RES_STATUS'] if reservation else 'none'}",
            ),
        )
        conn.commit()
        write_cur.close()
        cur.close()
        return render_housekeeping_page(
            request,
            feedback=f"Room {room_number} marked '{new_room_status}' and housekeeping log created.",
            ok=True,
            form_data=form_data,
            room_info={
                "room_status": new_room_status,
                "reservation_status": reservation["RES_STATUS"] if reservation else "No active reservation",
            },
        )
    except Exception as e:
        rollback_connection(conn)
        return render_housekeeping_page(
            request,
            feedback="Unable to complete that action. Please try again.",
            ok=False,
            form_data=form_data,
        )
    finally:
        close_connection(conn)


