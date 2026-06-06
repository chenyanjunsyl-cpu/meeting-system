import json
import os
import sqlite3
from datetime import date
from pathlib import Path
from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = Path(os.environ.get("MEETING_DB_PATH", Path(__file__).parent / "meeting.db"))
ROOMS_CONFIG_PATH = Path(os.environ.get("ROOMS_CONFIG_PATH", Path(__file__).parent / "rooms.json"))
DEFAULT_ROOMS = [
    {"name": "401", "capacity": 10, "location": "4楼"},
    {"name": "402", "capacity": 10, "location": "4楼"},
    {"name": "403", "capacity": 12, "location": "4楼"},
    {"name": "301", "capacity": 8, "location": "3楼"},
    {"name": "201", "capacity": 8, "location": "2楼"},
]


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def load_room_config():
    if not ROOMS_CONFIG_PATH.exists():
        ROOMS_CONFIG_PATH.write_text(json.dumps(DEFAULT_ROOMS, ensure_ascii=False, indent=2), encoding="utf-8")
    with ROOMS_CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_room_config(rooms):
    with ROOMS_CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(rooms, f, ensure_ascii=False, indent=2)


def fetch_all(query, params=()):
    with get_connection() as conn:
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def fetch_one(query, params=()):
    with get_connection() as conn:
        cursor = conn.execute(query, params)
        row = cursor.fetchone()
        return dict(row) if row else None


def get_rooms():
    return fetch_all("SELECT * FROM room ORDER BY name")


def get_all_bookings():
    return fetch_all(
        "SELECT b.*, r.name AS room_name FROM booking b JOIN room r ON b.room_id = r.room_id ORDER BY date, r.name, start_time",
    )


def get_user_by_username(username):
    return fetch_one("SELECT * FROM user_account WHERE username = ?", (username,))


def get_user_by_id(user_id):
    return fetch_one(
        "SELECT user_id, username, role, display_name, email, source FROM user_account WHERE user_id = ?",
        (user_id,),
    )


def get_all_users():
    return fetch_all("SELECT user_id, username, role, display_name, email, source FROM user_account ORDER BY display_name, username")


def add_user(username, password, role, display_name=None, email="", source="local"):
    display_name = (display_name or username).strip()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO user_account (username, password_hash, role, display_name, email, source)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (username, generate_password_hash(password), role, display_name, email, source),
        )
        conn.commit()


def upsert_user_role(username, role, display_name=None, email="", source="ad"):
    display_name = (display_name or username).strip()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT user_id FROM user_account WHERE username = ?",
            (username,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE user_account
                SET role = ?,
                    display_name = COALESCE(NULLIF(?, ''), display_name, username),
                    email = COALESCE(NULLIF(?, ''), email, ''),
                    source = COALESCE(NULLIF(?, ''), source, 'ad')
                WHERE user_id = ?
                """,
                (role, display_name, email, source, existing["user_id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO user_account (username, password_hash, role, display_name, email, source)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (username, generate_password_hash("__ad_login_only__"), role, display_name, email, source),
            )
        conn.commit()


def update_user_role(user_id, role):
    with get_connection() as conn:
        conn.execute("UPDATE user_account SET role = ? WHERE user_id = ?", (role, user_id))
        conn.commit()


def delete_user(user_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM user_account WHERE user_id = ?", (user_id,))
        conn.commit()


def count_admin_users():
    row = fetch_one("SELECT COUNT(*) AS count FROM user_account WHERE role = 'admin'")
    return row["count"] if row else 0


DEFAULT_AD_CONFIG = {
    "enabled": "0",
    "server_uri": "",
    "use_ssl": "0",
    "domain": "",
    "base_dn": "",
    "bind_dn": "",
    "bind_password": "",
    "user_filter": "(&(objectClass=user)(sAMAccountName={username}))",
    "admin_group_dn": "",
    "display_attr": "displayName",
    "email_attr": "mail",
}


def ensure_ad_config_table():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )
            """
        )
        for key, value in DEFAULT_AD_CONFIG.items():
            conn.execute(
                "INSERT OR IGNORE INTO app_config (key, value) VALUES (?, ?)",
                (f"ad.{key}", value),
            )
        conn.commit()


def get_ad_config():
    ensure_ad_config_table()
    rows = fetch_all("SELECT key, value FROM app_config WHERE key LIKE 'ad.%'")
    config = DEFAULT_AD_CONFIG.copy()
    for row in rows:
        config[row["key"][3:]] = row["value"]
    return config


def save_ad_config(config):
    ensure_ad_config_table()
    current = get_ad_config()
    merged = current.copy()
    for key in DEFAULT_AD_CONFIG:
        if key == "bind_password" and config.get(key, "") == "":
            continue
        merged[key] = str(config.get(key, ""))
    with get_connection() as conn:
        for key, value in merged.items():
            conn.execute(
                "INSERT INTO app_config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (f"ad.{key}", value),
            )
        conn.commit()
    return merged


def authenticate_user(username, password):
    user = get_user_by_username(username)
    if not user:
        return None
    if check_password_hash(user["password_hash"], password):
        return {
            "username": user["username"],
            "display_name": user.get("display_name") or user["username"],
            "email": user.get("email") or "",
            "role": user["role"],
            "source": user.get("source") or "local",
        }
    return None


def get_configured_people(query="", limit=50):
    query = (query or "").strip()
    params = []
    sql = """
        SELECT user_id, username, role, display_name, email, source
        FROM user_account
    """
    if query:
        like = f"%{query}%"
        sql += " WHERE username LIKE ? OR display_name LIKE ? OR email LIKE ?"
        params.extend([like, like, like])
    sql += " ORDER BY display_name, username"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return fetch_all(sql, tuple(params))


def get_configured_people_by_usernames(usernames):
    names = [name for name in usernames if name]
    if not names:
        return []
    placeholders = ",".join("?" for _ in names)
    return fetch_all(
        f"""
        SELECT user_id, username, role, display_name, email, source
        FROM user_account
        WHERE username IN ({placeholders})
        ORDER BY display_name, username
        """,
        tuple(names),
    )


def get_room_by_id(room_id):
    return fetch_one("SELECT * FROM room WHERE room_id = ?", (room_id,))


def get_booking_by_id(booking_id):
    return fetch_one(
        "SELECT b.*, r.name AS room_name, r.location FROM booking b JOIN room r ON b.room_id = r.room_id WHERE b.booking_id = ?",
        (booking_id,),
    )


def get_bookings_by_date(date_value):
    return fetch_all(
        "SELECT b.*, r.name AS room_name FROM booking b JOIN room r ON b.room_id = r.room_id WHERE date = ? ORDER BY r.room_id, start_time",
        (date_value,),
    )


def get_bookings_by_date_range(start_date, end_date, room_id=None):
    """查询指定日期范围内的预订"""
    query = "SELECT b.*, r.name AS room_name, r.location FROM booking b JOIN room r ON b.room_id = r.room_id WHERE date >= ? AND date <= ?"
    params = [start_date, end_date]
    
    if room_id:
        query += " AND b.room_id = ?"
        params.append(room_id)
    
    query += " ORDER BY b.date DESC, r.room_id, b.start_time"
    return fetch_all(query, tuple(params))


def get_booking_dates(start_date, end_date):
    """获取指定日期范围内有预约的日期列表"""
    bookings = get_bookings_by_date_range(start_date, end_date)
    return sorted(list(set(b['date'] for b in bookings)))


def get_user_bookings(username):
    """获取用户作为申请人的所有预约（未来+过去）"""
    return fetch_all(
        "SELECT b.*, r.name AS room_name, r.location FROM booking b JOIN room r ON b.room_id = r.room_id WHERE b.owner = ? ORDER BY b.date DESC, b.start_time DESC",
        (username,),
    )


def get_user_related_bookings(username):
    """获取用户预约的会议，以及该用户作为参会人的会议。"""
    user = get_user_by_username(username) or {}
    display_name = user.get("display_name") or username
    attendee_like_values = [f"%{username}%"]
    if display_name != username:
        attendee_like_values.append(f"%{display_name}%")
    attendee_like_sql = " OR ".join("b.attendees LIKE ?" for _ in attendee_like_values)
    rows = fetch_all(
        f"""
        SELECT b.*, r.name AS room_name, r.location
        FROM booking b
        JOIN room r ON b.room_id = r.room_id
        WHERE b.owner = ?
           OR (',' || COALESCE(b.attendee_usernames, '') || ',') LIKE ?
           OR ({attendee_like_sql})
        ORDER BY b.date DESC, b.start_time DESC
        """,
        (username, f"%,{username},%", *attendee_like_values),
    )
    for row in rows:
        attendee_names = [item.strip() for item in (row.get("attendee_usernames") or "").split(",") if item.strip()]
        is_owner = row.get("owner") == username
        attendees_text = row.get("attendees") or ""
        is_attendee = username in attendee_names or username in attendees_text or (display_name != username and display_name in attendees_text)
        if is_owner and is_attendee:
            row["relation"] = "both"
        elif is_owner:
            row["relation"] = "owner"
        else:
            row["relation"] = "attendee"
    return rows


def update_booking_minutes(booking_id, minutes):
    """更新会议纪要"""
    with get_connection() as conn:
        conn.execute(
            "UPDATE booking SET minutes = ? WHERE booking_id = ?",
            (minutes, booking_id),
        )
        conn.commit()


def add_room(name, capacity, location):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO room (name, capacity, location) VALUES (?, ?, ?)",
            (name, capacity, location),
        )
        conn.commit()


def update_room(room_id, name, capacity, location):
    with get_connection() as conn:
        conn.execute(
            "UPDATE room SET name = ?, capacity = ?, location = ? WHERE room_id = ?",
            (name, capacity, location, room_id),
        )
        conn.commit()


def delete_room(room_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM room WHERE room_id = ?", (room_id,))
        conn.commit()


def room_has_bookings(room_id):
    row = fetch_one("SELECT COUNT(*) AS count FROM booking WHERE room_id = ?", (room_id,))
    return bool(row and row["count"] > 0)


def save_rooms_to_config():
    rooms = get_rooms()
    write_room_config([
        {"name": room["name"], "capacity": room["capacity"], "location": room["location"]}
        for room in rooms
    ])


def sync_rooms_from_config():
    rooms = load_room_config()
    config_names = {room["name"] for room in rooms}
    with get_connection() as conn:
        for room in rooms:
            existing = conn.execute("SELECT room_id, capacity, location FROM room WHERE name = ?", (room["name"],)).fetchone()
            if existing:
                if existing["capacity"] != room["capacity"] or existing["location"] != room["location"]:
                    conn.execute(
                        "UPDATE room SET capacity = ?, location = ? WHERE room_id = ?",
                        (room["capacity"], room["location"], existing["room_id"]),
                    )
            else:
                conn.execute(
                    "INSERT INTO room (name, capacity, location) VALUES (?, ?, ?)",
                    (room["name"], room["capacity"], room["location"]),
                )
        existing_rooms = conn.execute("SELECT name, room_id FROM room").fetchall()
        for row in existing_rooms:
            if row["name"] not in config_names:
                booking_count = conn.execute(
                    "SELECT COUNT(*) FROM booking WHERE room_id = ?",
                    (row["room_id"],),
                ).fetchone()[0]
                if booking_count == 0:
                    conn.execute("DELETE FROM room WHERE room_id = ?", (row["room_id"],))
        conn.commit()
    return rooms


def ensure_booking_attendees_column():
    with get_connection() as conn:
        info = conn.execute("PRAGMA table_info(booking)").fetchall()
        if not any(row[1] == "attendees" for row in info):
            conn.execute("ALTER TABLE booking ADD COLUMN attendees TEXT NOT NULL DEFAULT ''")
            conn.commit()


def ensure_booking_minutes_column():
    """确保 booking 表有 minutes 列用于存储会议纪要"""
    with get_connection() as conn:
        info = conn.execute("PRAGMA table_info(booking)").fetchall()
        if not any(row[1] == "minutes" for row in info):
            conn.execute("ALTER TABLE booking ADD COLUMN minutes TEXT NOT NULL DEFAULT ''")
            conn.commit()


def ensure_user_profile_columns():
    with get_connection() as conn:
        info = conn.execute("PRAGMA table_info(user_account)").fetchall()
        columns = {row[1] for row in info}
        if "display_name" not in columns:
            conn.execute("ALTER TABLE user_account ADD COLUMN display_name TEXT NOT NULL DEFAULT ''")
        if "email" not in columns:
            conn.execute("ALTER TABLE user_account ADD COLUMN email TEXT NOT NULL DEFAULT ''")
        if "source" not in columns:
            conn.execute("ALTER TABLE user_account ADD COLUMN source TEXT NOT NULL DEFAULT 'local'")
        conn.execute("UPDATE user_account SET display_name = username WHERE display_name = ''")
        conn.execute("UPDATE user_account SET source = 'local' WHERE source = ''")
        conn.commit()


def ensure_booking_profile_columns():
    with get_connection() as conn:
        info = conn.execute("PRAGMA table_info(booking)").fetchall()
        columns = {row[1] for row in info}
        if "owner_display" not in columns:
            conn.execute("ALTER TABLE booking ADD COLUMN owner_display TEXT NOT NULL DEFAULT ''")
        if "attendee_usernames" not in columns:
            conn.execute("ALTER TABLE booking ADD COLUMN attendee_usernames TEXT NOT NULL DEFAULT ''")
        conn.execute("UPDATE booking SET owner_display = owner WHERE owner_display = ''")
        conn.commit()


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS room (
                room_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                capacity INTEGER NOT NULL,
                location TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_account (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'local'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS booking (
                booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                owner TEXT NOT NULL,
                owner_display TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL,
                attendees TEXT NOT NULL DEFAULT '',
                attendee_usernames TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (room_id) REFERENCES room(room_id) ON DELETE CASCADE
            )
            """
        )
        ensure_ad_config_table()
        ensure_user_profile_columns()
        ensure_booking_attendees_column()
        ensure_booking_minutes_column()
        ensure_booking_profile_columns()
        sync_rooms_from_config()

        existing_users = conn.execute("SELECT COUNT(*) FROM user_account").fetchone()[0]
        if existing_users == 0:
            conn.execute(
                "INSERT INTO user_account (username, password_hash, role, display_name, source) VALUES (?, ?, ?, ?, ?)",
                ("user", generate_password_hash("user123"), "user", "普通用户", "local"),
            )
            conn.execute(
                "INSERT INTO user_account (username, password_hash, role, display_name, source) VALUES (?, ?, ?, ?, ?)",
                ("admin", generate_password_hash("admin123"), "admin", "管理员", "local"),
            )
            conn.commit()

        existing = conn.execute("SELECT COUNT(*) FROM booking").fetchone()[0]
        if existing == 0:
            row = conn.execute("SELECT room_id FROM room ORDER BY name LIMIT 1").fetchone()
            if row:
                conn.execute(
                    """
                    INSERT INTO booking (room_id, date, start_time, end_time, owner, owner_display, subject, attendees, attendee_usernames)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (row["room_id"], date.today().isoformat(), "10:00", "11:00", "user", "普通用户", "项目例会", "普通用户 (user)", "user"),
                )
                conn.commit()


def add_booking(room_id, date_value, start_time, end_time, owner, subject, attendees, owner_display="", attendee_usernames=""):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO booking (room_id, date, start_time, end_time, owner, owner_display, subject, attendees, attendee_usernames)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (room_id, date_value, start_time, end_time, owner, owner_display or owner, subject, attendees, attendee_usernames),
        )
        conn.commit()


def update_booking(booking_id, room_id, date_value, start_time, end_time, owner, subject, attendees, owner_display="", attendee_usernames=""):
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE booking
            SET room_id = ?, date = ?, start_time = ?, end_time = ?, owner = ?, owner_display = ?, subject = ?, attendees = ?, attendee_usernames = ?
            WHERE booking_id = ?
            """,
            (room_id, date_value, start_time, end_time, owner, owner_display or owner, subject, attendees, attendee_usernames, booking_id),
        )
        conn.commit()


def delete_booking(booking_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM booking WHERE booking_id = ?", (booking_id,))
        conn.commit()


def check_booking_conflict(room_id, date_value, start_time, end_time, exclude_booking_id=None):
    query = "SELECT * FROM booking WHERE room_id = ? AND date = ? AND NOT (end_time <= ? OR start_time >= ?)"
    params = [room_id, date_value, start_time, end_time]
    if exclude_booking_id is not None:
        query += " AND booking_id != ?"
        params.append(exclude_booking_id)
    query += " ORDER BY start_time"
    existing = fetch_all(query, tuple(params))
    return len(existing) > 0
