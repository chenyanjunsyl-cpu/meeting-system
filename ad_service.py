from ldap3 import ALL, SUBTREE, Connection, Server
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars

from models import get_ad_config, get_user_by_username


USER_ATTRIBUTES = ["sAMAccountName", "userPrincipalName", "displayName", "mail", "memberOf"]


class ADServiceError(Exception):
    pass


def is_ad_enabled(config=None):
    config = config or get_ad_config()
    return config.get("enabled") == "1" and bool(config.get("server_uri") and config.get("base_dn"))


def _server(config):
    return Server(
        config["server_uri"],
        use_ssl=config.get("use_ssl") == "1",
        get_info=ALL,
        connect_timeout=5,
    )


def _bind_user_name(username, config):
    username = username.strip()
    if "@" in username or "\\" in username:
        return username
    domain = config.get("domain", "").strip()
    if domain:
        return f"{username}@{domain}"
    return username


def _service_connection(config):
    if not is_ad_enabled(config):
        raise ADServiceError("AD 域控未启用或配置不完整。")
    try:
        if config.get("bind_dn"):
            return Connection(
                _server(config),
                user=config.get("bind_dn"),
                password=config.get("bind_password", ""),
                auto_bind=True,
                receive_timeout=8,
            )
        return Connection(_server(config), auto_bind=True, receive_timeout=8)
    except LDAPException as exc:
        raise ADServiceError(f"无法连接或绑定 AD：{exc}") from exc


def _user_filter(username, config):
    template = config.get("user_filter") or "(&(objectClass=user)(sAMAccountName={username}))"
    return template.replace("{username}", escape_filter_chars(username))


def _entry_to_user(entry, config):
    attrs = entry.entry_attributes_as_dict
    username = ""
    for key in ("sAMAccountName", "userPrincipalName"):
        values = attrs.get(key) or []
        if values:
            username = str(values[0])
            break
    display_attr = config.get("display_attr") or "displayName"
    email_attr = config.get("email_attr") or "mail"
    display_values = attrs.get(display_attr) or attrs.get("displayName") or []
    email_values = attrs.get(email_attr) or attrs.get("mail") or []
    groups = attrs.get("memberOf") or []
    admin_group = config.get("admin_group_dn", "").strip().lower()
    local_user = get_user_by_username(username) if username else None
    role = local_user["role"] if local_user else "user"
    if admin_group and any(str(group).lower() == admin_group for group in groups):
        role = "admin"
    return {
        "username": username,
        "display_name": str(display_values[0]) if display_values else username,
        "email": str(email_values[0]) if email_values else "",
        "role": role,
        "source": "ad",
    }


def find_ad_user(username, config=None):
    config = config or get_ad_config()
    with _service_connection(config) as conn:
        ok = conn.search(
            search_base=config["base_dn"],
            search_filter=_user_filter(username, config),
            search_scope=SUBTREE,
            attributes=USER_ATTRIBUTES,
            size_limit=1,
        )
        if not ok or not conn.entries:
            return None
        return _entry_to_user(conn.entries[0], config)


def authenticate_ad_user(username, password):
    config = get_ad_config()
    if not is_ad_enabled(config):
        return None
    if not username or not password:
        return None
    try:
        user_info = find_ad_user(username, config)
        if not user_info:
            return None
        bind_name = _bind_user_name(username, config)
        conn = Connection(
            _server(config),
            user=bind_name,
            password=password,
            auto_bind=True,
            receive_timeout=8,
        )
        conn.unbind()
        return user_info
    except (LDAPException, ADServiceError):
        return None


def search_ad_users(query="", limit=30, config=None):
    config = config or get_ad_config()
    query = (query or "").strip()
    if query:
        safe = escape_filter_chars(query)
        search_filter = (
            "(&(objectClass=user)(|"
            f"(sAMAccountName=*{safe}*)"
            f"(displayName=*{safe}*)"
            f"(mail=*{safe}*)"
            "))"
        )
    else:
        search_filter = "(&(objectClass=user)(sAMAccountName=*))"
    with _service_connection(config) as conn:
        conn.search(
            search_base=config["base_dn"],
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=USER_ATTRIBUTES,
            size_limit=limit,
        )
        return [_entry_to_user(entry, config) for entry in conn.entries]


def test_ad_connection(config=None):
    config = config or get_ad_config()
    with _service_connection(config) as conn:
        return bool(conn.bound)
