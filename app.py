import os
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, make_response, jsonify
from models import (
    init_db,
    authenticate_user,
    get_all_users,
    get_user_by_id,
    get_ad_config,
    save_ad_config,
    get_rooms,
    get_room_by_id,
    get_booking_by_id,
    get_all_bookings,
    get_bookings_by_date,
    get_bookings_by_date_range,
    get_booking_dates,
    get_user_bookings,
    update_booking_minutes,
    add_user,
    upsert_user_role,
    update_user_role,
    delete_user,
    count_admin_users,
    add_booking,
    update_booking,
    delete_booking,
    check_booking_conflict,
    add_room,
    update_room,
    delete_room,
    room_has_bookings,
    sync_rooms_from_config,
    save_rooms_to_config,
)
from ad_service import ADServiceError, authenticate_ad_user, is_ad_enabled, search_ad_users, test_ad_connection

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
AD_ADMIN_PAGE_SIZE = 20

init_db()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = session.get("user")
        if not user:
            return redirect(url_for("login", next=request.path))
        if user.get("role") != "admin":
            return render_template("result.html", error="你没有权限访问此页面。")
        return view(*args, **kwargs)
    return wrapped


def safe_redirect_target(target):
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("index")


def parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_date(value, default=None):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return default or date.today()


def get_booking_start_datetime(booking):
    try:
        return datetime.fromisoformat(f"{booking['date']}T{booking['start_time']}")
    except (KeyError, TypeError, ValueError):
        return None


def can_edit_booking_minutes(booking):
    start_at = get_booking_start_datetime(booking)
    return bool(start_at and datetime.now() >= start_at)


@app.context_processor
def inject_user():
    return {"current_user": session.get("user")}


@app.route("/api/ad/users")
@login_required
def api_ad_users():
    if not is_ad_enabled():
        return jsonify({"enabled": False, "users": []})

    query = request.args.get("q", "").strip()
    try:
        users = search_ad_users(query=query, limit=20)
    except ADServiceError as exc:
        return jsonify({"enabled": True, "users": [], "error": str(exc)}), 503

    payload = []
    for user in users:
        username = user.get("username") or ""
        display_name = user.get("display_name") or username
        email = user.get("email") or ""
        if username and display_name and display_name != username:
            label = f"{display_name} ({username})"
        else:
            label = username or display_name
        payload.append({
            "username": username,
            "display_name": display_name,
            "email": email,
            "label": label,
        })
    return jsonify({"enabled": True, "users": payload})


@app.route("/")
def index():
    week_start_day = parse_date(request.args.get("start") or request.args.get("date"), date.today())
    selected_day = parse_date(request.args.get("date"), week_start_day)
    selected_date = selected_day.isoformat()
    week_start = week_start_day.isoformat()
    week_end_day = week_start_day + timedelta(days=6)
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

    rooms = get_rooms()
    bookings = get_bookings_by_date(selected_date)
    week_bookings = get_bookings_by_date_range(week_start, week_end_day.isoformat())
    week_bookings_by_date = {}
    for booking in week_bookings:
        week_bookings_by_date.setdefault(booking["date"], []).append(booking)
    week_days = []
    for offset in range(7):
        day = week_start_day + timedelta(days=offset)
        day_key = day.isoformat()
        week_days.append({
            "date": day_key,
            "weekday": weekday_names[day.weekday()],
            "bookings": week_bookings_by_date.get(day_key, []),
        })
    bookings_by_room = {room["room_id"]: [] for room in rooms}

    for booking in bookings:
        bookings_by_room[booking["room_id"]].append(booking)

    room_status = []
    for room in rooms:
        room_bookings = bookings_by_room[room["room_id"]]
        if room_bookings:
            room_status.append({
                "room": room,
                "state": "已订",
                "summary": ", ".join(f"{b['start_time']}-{b['end_time']}" for b in room_bookings),
                "bookings": room_bookings,
            })
        else:
            room_status.append({
                "room": room,
                "state": "空闲",
                "summary": "全天可用",
                "bookings": [],
            })

    ad_people = []
    try:
        if session.get("user") and is_ad_enabled():
            ad_people = search_ad_users(limit=50)
    except ADServiceError:
        ad_people = []

    return render_template(
        "index.html",
        selected_date=selected_date,
        week_start=week_start,
        week_end=week_end_day.isoformat(),
        week_days=week_days,
        room_status=room_status,
        rooms=rooms,
        bookings=bookings,
        ad_people=ad_people,
    )


@app.route("/book", methods=["POST"])
@login_required
def book():
    form = request.form
    room_id = form.get("room_id")
    date_value = form.get("date")
    start_time = form.get("start_time")
    end_time = form.get("end_time")
    owner = session["user"]["username"]
    subject = form.get("subject", "").strip()
    attendees_values = [value.strip() for value in form.getlist("attendees") if value.strip()]
    attendees = ", ".join(attendees_values) if attendees_values else form.get("attendees", "").strip()

    if not (room_id and date_value and start_time and end_time and owner and subject and attendees):
        error = "请填写所有预约信息，包括参会人员。"
        return render_template("result.html", error=error)

    if start_time >= end_time:
        error = "开始时间必须早于结束时间。"
        return render_template("result.html", error=error)

    room_id = parse_int(room_id)
    if room_id is None or not get_room_by_id(room_id):
        return render_template("result.html", error="请选择有效的会议室。")

    if check_booking_conflict(room_id, date_value, start_time, end_time):
        error = "该会议室在所选时间段已被占用，无法重复预定。"
        return render_template("result.html", error=error)

    add_booking(room_id, date_value, start_time, end_time, owner, subject, attendees)
    message = "预约成功！请刷新页面查看最新预定情况。"
    return render_template("result.html", message=message)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = authenticate_ad_user(username, password) or authenticate_user(username, password)
        if user:
            session["user"] = user
            return redirect(safe_redirect_target(request.args.get("next")))
        error = "用户名或密码不正确。"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("index"))


@app.route("/admin/bookings")
@admin_required
def admin_bookings():
    bookings = get_all_bookings()
    rooms = get_rooms()
    return render_template("admin_bookings.html", bookings=bookings, rooms=rooms, message=None, error=None)


@app.route("/admin/bookings/edit/<int:booking_id>")
@admin_required
def admin_edit_booking(booking_id):
    booking = get_booking_by_id(booking_id)
    if not booking:
        return render_template("result.html", error="预约不存在。")
    rooms = get_rooms()
    return render_template("edit_booking.html", booking=booking, rooms=rooms)


@app.route("/admin/bookings/update/<int:booking_id>", methods=["POST"])
@admin_required
def admin_update_booking(booking_id):
    form = request.form
    room_id = form.get("room_id")
    date_value = form.get("date")
    start_time = form.get("start_time")
    end_time = form.get("end_time")
    owner = form.get("owner", "匿名")
    subject = form.get("subject", "会议预约")
    attendees = form.get("attendees", "")

    if not (room_id and date_value and start_time and end_time and owner and subject and attendees):
        return render_template("result.html", error="请填写所有预约信息，包括参会人员。")

    if start_time >= end_time:
        return render_template("result.html", error="开始时间必须早于结束时间。")

    room_id = parse_int(room_id)
    if room_id is None or not get_room_by_id(room_id):
        return render_template("result.html", error="请选择有效的会议室。")

    if check_booking_conflict(room_id, date_value, start_time, end_time, exclude_booking_id=booking_id):
        return render_template("result.html", error="该会议室在所选时间段已被占用，无法修改为该时间。")

    update_booking(booking_id, room_id, date_value, start_time, end_time, owner, subject, attendees)
    return render_template("result.html", message="预约已更新成功。")


@app.route("/admin/bookings/delete/<int:booking_id>", methods=["POST"])
@admin_required
def admin_delete_booking(booking_id):
    delete_booking(booking_id)
    return redirect(url_for("admin_bookings"))


@app.route("/admin")
@admin_required
def admin_index():
    return redirect("/admin/rooms")


def render_admin_users(
    message=None,
    error=None,
    ad_users=None,
    ad_query="",
    ad_page=1,
    ad_total=0,
    ad_total_pages=0,
    ad_search_performed=False,
):
    ad_config = get_ad_config()
    return render_template(
        "admin_users.html",
        users=get_all_users(),
        ad_config=ad_config,
        ad_enabled=is_ad_enabled(ad_config),
        ad_users=ad_users or [],
        ad_query=ad_query,
        ad_page=ad_page,
        ad_total=ad_total,
        ad_total_pages=ad_total_pages,
        ad_page_size=AD_ADMIN_PAGE_SIZE,
        ad_search_performed=ad_search_performed,
        message=message,
        error=error,
    )


@app.route("/admin/users")
@admin_required
def admin_users():
    ad_query = request.args.get("ad_query", "").strip()
    ad_page = parse_int(request.args.get("ad_page")) or 1
    if ad_page < 1:
        ad_page = 1
    ad_users = []
    ad_total = 0
    ad_total_pages = 0
    error = None
    ad_search_performed = "ad_query" in request.args
    if ad_search_performed:
        try:
            all_ad_users = search_ad_users(ad_query, limit=None)
            all_ad_users = sorted(
                all_ad_users,
                key=lambda user: (
                    (user.get("display_name") or "").lower(),
                    (user.get("username") or "").lower(),
                ),
            )
            ad_total = len(all_ad_users)
            ad_total_pages = max(1, (ad_total + AD_ADMIN_PAGE_SIZE - 1) // AD_ADMIN_PAGE_SIZE) if ad_total else 0
            if ad_total_pages and ad_page > ad_total_pages:
                ad_page = ad_total_pages
            start = (ad_page - 1) * AD_ADMIN_PAGE_SIZE
            ad_users = all_ad_users[start:start + AD_ADMIN_PAGE_SIZE]
        except ADServiceError as exc:
            error = str(exc)
    return render_admin_users(
        error=error,
        ad_users=ad_users,
        ad_query=ad_query,
        ad_page=ad_page,
        ad_total=ad_total,
        ad_total_pages=ad_total_pages,
        ad_search_performed=ad_search_performed,
    )


@app.route("/admin/ad/save", methods=["POST"])
@admin_required
def admin_save_ad_config():
    config = {
        "enabled": "1" if request.form.get("enabled") == "1" else "0",
        "server_uri": request.form.get("server_uri", "").strip(),
        "use_ssl": "1" if request.form.get("use_ssl") == "1" else "0",
        "domain": request.form.get("domain", "").strip(),
        "base_dn": request.form.get("base_dn", "").strip(),
        "bind_dn": request.form.get("bind_dn", "").strip(),
        "bind_password": request.form.get("bind_password", ""),
        "user_filter": request.form.get("user_filter", "").strip() or "(&(objectClass=user)(sAMAccountName={username}))",
        "admin_group_dn": request.form.get("admin_group_dn", "").strip(),
        "display_attr": request.form.get("display_attr", "").strip() or "displayName",
        "email_attr": request.form.get("email_attr", "").strip() or "mail",
    }
    save_ad_config(config)
    return render_admin_users(message="AD 域控配置已保存。")


@app.route("/admin/ad/test", methods=["POST"])
@admin_required
def admin_test_ad_config():
    try:
        test_ad_connection()
    except ADServiceError as exc:
        return render_admin_users(error=f"AD 连接失败：{exc}")
    return render_admin_users(message="AD 连接测试成功。")


@app.route("/admin/ad/role", methods=["POST"])
@admin_required
def admin_set_ad_user_role():
    username = request.form.get("username", "").strip()
    role = request.form.get("role", "user")
    if not username:
        return render_admin_users(error="请选择 AD 用户。")
    if role not in {"user", "admin"}:
        return render_admin_users(error="请选择有效的用户权限。")
    upsert_user_role(username, role)
    return render_admin_users(message=f"已为 AD 用户 {username} 设置系统权限。")


@app.route("/admin/users/add", methods=["POST"])
@admin_required
def admin_add_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "user")

    if role not in {"user", "admin"}:
        return render_admin_users(error="请选择有效的用户权限。")
    if not username or not password:
        return render_admin_users(error="请填写用户名和密码。")
    if len(password) < 6:
        return render_admin_users(error="密码至少需要 6 位。")

    try:
        add_user(username, password, role)
    except sqlite3.IntegrityError:
        return render_admin_users(error="该用户名已存在。")

    return render_admin_users(message="用户已创建。")


@app.route("/admin/users/role/<int:user_id>", methods=["POST"])
@admin_required
def admin_update_user_role(user_id):
    user = get_user_by_id(user_id)
    role = request.form.get("role", "user")

    if not user:
        return render_admin_users(error="用户不存在。")
    if role not in {"user", "admin"}:
        return render_admin_users(error="请选择有效的用户权限。")
    if user["role"] == "admin" and role != "admin" and count_admin_users() <= 1:
        return render_admin_users(error="至少需要保留一个管理员账号。")

    update_user_role(user_id, role)
    current_user = session.get("user")
    if current_user and current_user.get("username") == user["username"]:
        current_user["role"] = role
        session["user"] = current_user
    return render_admin_users(message="用户权限已更新。")


@app.route("/admin/users/delete/<int:user_id>", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    user = get_user_by_id(user_id)
    current_user = session.get("user")

    if not user:
        return render_admin_users(error="用户不存在。")
    if current_user and current_user.get("username") == user["username"]:
        return render_admin_users(error="不能删除当前登录的账号。")
    if user["role"] == "admin" and count_admin_users() <= 1:
        return render_admin_users(error="至少需要保留一个管理员账号。")

    delete_user(user_id)
    return render_admin_users(message="用户已删除。")


@app.route("/admin/rooms")
@admin_required
def admin_rooms():
    rooms = get_rooms()
    edit_room = None
    edit_id = request.args.get("edit")
    if edit_id:
        edit_room_id = parse_int(edit_id)
        edit_room = get_room_by_id(edit_room_id) if edit_room_id is not None else None
    return render_template("admin_rooms.html", rooms=rooms, edit_room=edit_room, message=None, error=None)


@app.route("/admin/rooms/add", methods=["POST"])
@admin_required
def admin_add_room():
    form = request.form
    name = form.get("name", "").strip()
    location = form.get("location", "").strip()
    capacity = form.get("capacity", "").strip()

    if not (name and location and capacity):
        rooms = get_rooms()
        return render_template("admin_rooms.html", rooms=rooms, edit_room=None, error="请填写会议室名称、地点和容纳人数。")

    try:
        capacity_value = int(capacity)
    except ValueError:
        rooms = get_rooms()
        return render_template("admin_rooms.html", rooms=rooms, edit_room=None, error="容纳人数必须是数字。")
    if capacity_value <= 0:
        rooms = get_rooms()
        return render_template("admin_rooms.html", rooms=rooms, edit_room=None, error="容纳人数必须大于 0。")

    add_room(name, capacity_value, location)
    save_rooms_to_config()
    rooms = get_rooms()
    return render_template("admin_rooms.html", rooms=rooms, edit_room=None, message="会议室已添加并保存到配置。")


@app.route("/admin/rooms/update/<int:room_id>", methods=["POST"])
@admin_required
def admin_update_room(room_id):
    form = request.form
    name = form.get("name", "").strip()
    location = form.get("location", "").strip()
    capacity = form.get("capacity", "").strip()

    if not (name and location and capacity):
        rooms = get_rooms()
        edit_room = get_room_by_id(room_id)
        return render_template("admin_rooms.html", rooms=rooms, edit_room=edit_room, error="请填写会议室名称、地点和容纳人数。")

    try:
        capacity_value = int(capacity)
    except ValueError:
        rooms = get_rooms()
        edit_room = get_room_by_id(room_id)
        return render_template("admin_rooms.html", rooms=rooms, edit_room=edit_room, error="容纳人数必须是数字。")
    if capacity_value <= 0:
        rooms = get_rooms()
        edit_room = get_room_by_id(room_id)
        return render_template("admin_rooms.html", rooms=rooms, edit_room=edit_room, error="容纳人数必须大于 0。")

    update_room(room_id, name, capacity_value, location)
    save_rooms_to_config()
    rooms = get_rooms()
    return render_template("admin_rooms.html", rooms=rooms, edit_room=None, message="会议室已更新并保存到配置。")


@app.route("/admin/rooms/delete/<int:room_id>", methods=["POST"])
@admin_required
def admin_delete_room(room_id):
    if room_has_bookings(room_id):
        rooms = get_rooms()
        return render_template("admin_rooms.html", rooms=rooms, edit_room=None, error="该会议室已有预约记录，不能直接删除。")
    delete_room(room_id)
    save_rooms_to_config()
    rooms = get_rooms()
    return render_template("admin_rooms.html", rooms=rooms, edit_room=None, message="会议室已删除并保存到配置。")


@app.route("/admin/rooms/sync", methods=["POST"])
@admin_required
def admin_sync_rooms():
    sync_rooms_from_config()
    rooms = get_rooms()
    return render_template("admin_rooms.html", rooms=rooms, edit_room=None, message="已从 rooms.json 同步会议室配置到数据库。")


@app.route("/history", methods=["GET", "POST"])
@login_required
def history():
    """查看会议历史记录"""
    today = str(date.today())
    
    if request.method == "POST":
        start_date = request.form.get("start_date", today)
        end_date = request.form.get("end_date", today)
        room_id = request.form.get("room_id", "")
    else:
        start_date = request.args.get("start_date", today)
        end_date = request.args.get("end_date", today)
        room_id = request.args.get("room_id", "")
    
    # 验证日期格式
    if not start_date or not end_date:
        start_date = today
        end_date = today
    
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    
    # 查询数据
    room_id_filter = parse_int(room_id) if room_id else None
    bookings = get_bookings_by_date_range(start_date, end_date, room_id_filter)
    booking_dates = get_booking_dates(start_date, end_date)
    all_rooms = get_rooms()
    selected_date = request.args.get("selected_date", "")
    
    return render_template(
        "history.html",
        bookings=bookings,
        booking_dates=booking_dates,
        start_date=start_date,
        end_date=end_date,
        room_id_filter=room_id or "",
        all_rooms=all_rooms,
        selected_date=selected_date,
    )


@app.route("/export_history", methods=["POST"])
@login_required
def export_history():
    """导出会议历史记录为 CSV"""
    import csv
    from io import StringIO
    
    start_date = request.form.get("start_date", str(date.today()))
    end_date = request.form.get("end_date", str(date.today()))
    room_id = request.form.get("room_id", "")
    
    room_id_filter = parse_int(room_id) if room_id else None
    bookings = get_bookings_by_date_range(start_date, end_date, room_id_filter)
    
    # 创建 CSV
    output = StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    
    # CSV 表头
    writer.writerow(["日期", "会议室", "地点", "开始时间", "结束时间", "会议主题", "申请人", "参会人员", "会议纪要"])
    
    # CSV 数据行
    for booking in bookings:
        writer.writerow([
            booking["date"],
            booking["room_name"],
            booking.get("location", ""),
            booking["start_time"],
            booking["end_time"],
            booking["subject"],
            booking["owner"],
            booking["attendees"],
            booking.get("minutes", ""),
        ])
    
    # 生成响应
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename=meeting_history_{start_date}_to_{end_date}.csv"
    response.headers["Content-Type"] = "text/csv; charset=utf-8-sig"
    return response


@app.route("/my_bookings")
@login_required
def my_bookings():
    """查看我的预约列表"""
    user = session.get("user")
    username = user.get("username")
    bookings = get_user_bookings(username)
    return render_template(
        "my_bookings.html",
        bookings=bookings,
        now_date=date.today().isoformat(),
        now_datetime=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


@app.route("/booking/minutes/<int:booking_id>", methods=["GET", "POST"])
@login_required
def edit_booking_minutes(booking_id):
    """编辑会议纪要"""
    booking = get_booking_by_id(booking_id)
    user = session.get("user")
    
    if not booking:
        return render_template("result.html", error="会议预约不存在。")
    
    # 只有申请人和管理员可以编辑纪要
    if booking["owner"] != user.get("username") and user.get("role") != "admin":
        return render_template("result.html", error="你没有权限编辑此会议的纪要。")

    if not can_edit_booking_minutes(booking):
        return render_template("result.html", error="会议开始后才能填写会议纪要。")
    
    if request.method == "POST":
        minutes = request.form.get("minutes", "")
        update_booking_minutes(booking_id, minutes)
        return render_template(
            "result.html",
            success="会议纪要已保存。",
            redirect_url="/my_bookings",
            button_text="返回我的预约",
        )
    
    return render_template("edit_minutes.html", booking=booking)


if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG") == "1",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "5000")),
    )
