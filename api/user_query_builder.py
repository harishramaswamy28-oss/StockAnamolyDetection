"""Ownership-scoped query builder for a user's six personal-data tables.

There is deliberately no SQL text field. Every operation is selected from a
server-side table/action allowlist and every supplied value is a bind value.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from psycopg import sql

from api.auth import get_current_user
from database.connection import get_connection


router = APIRouter(prefix="/database/query", tags=["personal data queries"])

TABLES = {
    "app_user": {
        "label": "My account",
        "columns": {"user_id": ("integer", "User ID"), "name": ("text", "Name"), "email": ("text", "Email")},
        "actions": ["retrieve", "modify"],
        "default_sort": "user_id",
        "owner_column": "user_id",
    },
    "watchlist": {
        "label": "My watchlists",
        "columns": {"watchlist_no": ("integer", "Watchlist ID"), "name": ("text", "Name")},
        "actions": ["retrieve", "add", "modify", "remove"],
        "default_sort": "watchlist_no",
        "owner_column": "user_id",
    },
    "watchlist_security": {
        "label": "Securities in my watchlists",
        "columns": {"watchlist_no": ("integer", "Watchlist ID"), "security_id": ("integer", "Security ID")},
        "actions": ["retrieve", "add", "remove"],
        "default_sort": "watchlist_no",
        "owner_column": "user_id",
    },
    "alert": {
        "label": "My price alerts",
        "columns": {
            "alert_no": ("integer", "Alert ID"), "security_id": ("integer", "Security ID"),
            "condition": ("text", "Condition"), "target_price": ("number", "Target price"),
            "status": ("text", "Status"),
        },
        "actions": ["retrieve", "add", "modify", "remove"],
        "default_sort": "alert_no",
        "owner_column": "user_id",
    },
    "notification": {
        "label": "My notifications",
        "columns": {
            "notification_id": ("integer", "Notification ID"), "alert_no": ("integer", "Alert ID"),
            "anomaly_id": ("integer", "Anomaly ID"), "message": ("text", "Message"),
            "created_at": ("timestamp", "Created at"), "status": ("text", "Status"),
        },
        "actions": ["retrieve", "modify", "remove"],
        "default_sort": "created_at",
        "owner_column": "user_id",
    },
    "user_preference": {
        "label": "My notification preferences",
        "columns": {
            "user_id": ("integer", "Account ID"),
            "price_alerts": ("boolean", "Price alerts"),
            "anomaly_alerts": ("boolean", "Anomaly alerts"),
            "notification_mode": ("text", "Notification mode"),
        },
        "actions": ["retrieve", "modify"],
        "default_sort": "user_id",
        "owner_column": "user_id",
    },
}

OPERATORS = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
NULL_OPERATORS = {"is_null", "is_not_null"}


class QueryFilter(BaseModel):
    column: str = Field(min_length=1, max_length=64)
    operator: Literal["eq", "neq", "gt", "gte", "lt", "lte", "contains", "starts_with", "is_null", "is_not_null"]
    value: str | None = Field(default=None, max_length=200)


class UserQuery(BaseModel):
    table: str = Field(min_length=1, max_length=64)
    action: Literal["retrieve", "add", "modify", "remove"]
    columns: list[str] = Field(default_factory=list, max_length=8)
    filters: list[QueryFilter] = Field(default_factory=list, max_length=5)
    filter_logic: Literal["and", "or"] = "and"
    values: dict[str, str | int | float | bool | None] = Field(default_factory=dict, max_length=8)
    sort_by: str | None = Field(default=None, max_length=64)
    sort_direction: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=50, ge=1, le=100)


def _value(value, kind):
    if value is None:
        raise HTTPException(status_code=422, detail="This filter requires a value.")
    text_value = str(value)
    try:
        if kind == "text":
            return text_value
        if kind == "integer":
            return int(text_value)
        if kind == "number":
            number = Decimal(text_value)
            if not number.is_finite():
                raise ValueError
            return number
        if kind == "boolean":
            if isinstance(value, bool):
                return value
            if text_value.lower() in {"true", "1", "yes"}:
                return True
            if text_value.lower() in {"false", "0", "no"}:
                return False
            raise ValueError
        if kind == "timestamp":
            stamp = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
            if stamp.utcoffset() is None:
                raise ValueError
            return stamp
    except (ValueError, InvalidOperation):
        raise HTTPException(status_code=422, detail=f"Enter a valid {kind} value.") from None
    raise HTTPException(status_code=422, detail="Unsupported filter type.")


def _ensure_target_filter(request: UserQuery, key: str):
    matches = [item for item in request.filters if item.column == key and item.operator == "eq"]
    if len(matches) != 1 or matches[0].value is None:
        raise HTTPException(status_code=422, detail=f"Choose one specific {key} to change or remove.")
    return _value(matches[0].value, TABLES[request.table]["columns"][key][0])


@router.get("/schema")
def get_query_schema(current_user=Depends(get_current_user)):
    return {
        "tables": [
            {
                "name": name,
                "label": config["label"],
                "actions": config["actions"],
                "default_sort": config["default_sort"],
                "columns": [
                    {"name": column, "type": kind, "label": label}
                    for column, (kind, label) in config["columns"].items()
                ],
            }
            for name, config in TABLES.items()
        ],
        "limits": {"max_rows": 100, "max_filters": 5, "raw_sql": False},
        "account": {"user_id": current_user["user_id"]},
    }


@router.post("/run")
def run_user_query(request: UserQuery, current_user=Depends(get_current_user)):
    config = TABLES.get(request.table)
    if config is None or request.action not in config["actions"]:
        raise HTTPException(status_code=422, detail="That table/action combination is not available.")
    user_id = current_user["user_id"]
    allowed_columns = config["columns"]
    if request.action == "retrieve":
        columns = request.columns or list(allowed_columns)
        if not columns or len(columns) != len(set(columns)) or any(name not in allowed_columns for name in columns):
            raise HTTPException(status_code=422, detail="Choose valid output columns.")
        order_by = request.sort_by or config["default_sort"]
        if order_by not in allowed_columns:
            raise HTTPException(status_code=422, detail="Choose a valid sort column.")
    else:
        columns = []

    params = []
    where = [sql.SQL("{} = %s").format(sql.Identifier(config["owner_column"]))]
    params.append(user_id)
    for item in request.filters:
        info = allowed_columns.get(item.column)
        if info is None:
            raise HTTPException(status_code=422, detail="A filter column is not available.")
        kind = info[0]
        identifier = sql.Identifier(item.column)
        if item.operator in NULL_OPERATORS:
            if item.value not in (None, ""):
                raise HTTPException(status_code=422, detail="Empty-value filters do not take a value.")
            where.append(sql.SQL("{} IS NULL" if item.operator == "is_null" else "{} IS NOT NULL").format(identifier))
        elif item.operator in {"contains", "starts_with"}:
            if kind != "text" or item.value is None:
                raise HTTPException(status_code=422, detail="Text matching requires a text column and a value.")
            pattern = f"%{item.value}%" if item.operator == "contains" else f"{item.value}%"
            where.append(sql.SQL("{} ILIKE %s").format(identifier))
            params.append(pattern)
        else:
            if item.operator in {"gt", "gte", "lt", "lte"} and kind in {"text", "boolean"}:
                raise HTTPException(status_code=422, detail="Ordering filters require a number or timestamp.")
            where.append(sql.SQL("{} {} %s").format(identifier, sql.SQL(OPERATORS[item.operator])))
            params.append(_value(item.value, kind))

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                if request.action == "retrieve":
                    query = sql.SQL("SELECT {} FROM public.{} WHERE {} ORDER BY {} {} LIMIT %s").format(
                        sql.SQL(", ").join(map(sql.Identifier, columns)),
                        sql.Identifier(request.table),
                        sql.SQL(" AND ").join(where[:1]) + sql.SQL(" AND (") + sql.SQL(
                            " OR " if request.filter_logic == "or" else " AND "
                        ).join(where[1:]) + sql.SQL(")") if len(where) > 1 else where[0],
                        sql.Identifier(order_by),
                        sql.SQL("DESC" if request.sort_direction == "desc" else "ASC"),
                    )
                    params.append(request.limit)
                    cursor.execute("SET TRANSACTION READ ONLY")
                    cursor.execute("SET LOCAL statement_timeout = '3000ms'")
                    cursor.execute(query, tuple(params))
                    names = [column.name for column in cursor.description]
                    rows = [dict(zip(names, row)) for row in cursor.fetchall()]
                    return {"table": request.table, "action": request.action, "rows": jsonable_encoder(rows), "row_count": len(rows)}

                result = _mutate(cursor, request, user_id)
                connection.commit()
                return {"table": request.table, "action": request.action, **result}
    except psycopg.errors.QueryCanceled:
        raise HTTPException(status_code=408, detail="Query took too long. Narrow your filters and try again.") from None
    except psycopg.errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="That record already exists.") from None
    except psycopg.Error:
        raise HTTPException(status_code=503, detail="The request could not be completed. Check the values and try again.") from None


def _mutate(cursor, request, user_id):
    table = request.table
    values = request.values
    if request.action == "add" and request.filters:
        raise HTTPException(status_code=422, detail="Add actions do not take filters.")
    if table == "watchlist" and request.action == "add":
        if set(values) != {"name"} or not str(values["name"]).strip():
            raise HTTPException(status_code=422, detail="Add a watchlist with a non-empty name.")
        name = str(values["name"]).strip()
        if len(name) > 100:
            raise HTTPException(status_code=422, detail="Watchlist names must contain 100 characters or fewer.")
        cursor.execute("SELECT user_id FROM app_user WHERE user_id=%s FOR UPDATE", (user_id,))
        cursor.execute("SELECT COALESCE(MAX(watchlist_no), 0) + 1 FROM watchlist WHERE user_id=%s", (user_id,))
        no = cursor.fetchone()[0]
        cursor.execute("INSERT INTO watchlist(user_id,watchlist_no,name) VALUES (%s,%s,%s)", (user_id, no, name))
        return {"message": "Watchlist added.", "watchlist_no": no}

    if table == "watchlist_security" and request.action == "add":
        if set(values) != {"watchlist_no", "symbol"}:
            raise HTTPException(status_code=422, detail="Choose one of your watchlists and a security symbol.")
        try:
            no = int(values["watchlist_no"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Choose a valid watchlist.") from None
        symbol = str(values["symbol"]).strip().upper()
        cursor.execute(
            """INSERT INTO watchlist_security(user_id,watchlist_no,security_id)
               SELECT %s,w.watchlist_no,s.security_id FROM watchlist w
               JOIN security s ON upper(s.symbol)=%s
               WHERE w.user_id=%s AND w.watchlist_no=%s
               ON CONFLICT DO NOTHING RETURNING security_id""",
            (user_id, symbol, user_id, no),
        )
        if cursor.fetchone() is None:
            cursor.execute("SELECT 1 FROM watchlist WHERE user_id=%s AND watchlist_no=%s", (user_id, no))
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Your watchlist was not found.")
            raise HTTPException(status_code=404, detail="Security not found or already in that watchlist.")
        return {"message": "Security added to your watchlist."}

    if table == "alert" and request.action == "add":
        if set(values) != {"symbol", "condition", "target_price"}:
            raise HTTPException(status_code=422, detail="Provide a symbol, above/below condition, and target price.")
        symbol = str(values["symbol"]).strip().upper()
        condition = str(values["condition"])
        try:
            target = Decimal(str(values["target_price"]))
            if not target.is_finite() or target <= 0:
                raise InvalidOperation
        except InvalidOperation:
            raise HTTPException(status_code=422, detail="Target price must be a positive number.") from None
        if condition not in {"above", "below"}:
            raise HTTPException(status_code=422, detail="Condition must be above or below.")
        cursor.execute("SELECT user_id FROM app_user WHERE user_id=%s FOR UPDATE", (user_id,))
        cursor.execute("SELECT security_id FROM security WHERE upper(symbol)=%s", (symbol,))
        security = cursor.fetchone()
        if security is None:
            raise HTTPException(status_code=404, detail="Security not found.")
        cursor.execute("SELECT COALESCE(MAX(alert_no),0)+1 FROM alert WHERE user_id=%s", (user_id,))
        alert_no = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO alert(user_id,alert_no,security_id,condition,target_price,status) VALUES (%s,%s,%s,%s,%s,'active')",
            (user_id, alert_no, security[0], condition, target),
        )
        return {"message": "Price alert added.", "alert_no": alert_no}

    if table == "user_preference" and request.action == "modify":
        if request.filters:
            raise HTTPException(status_code=422, detail="Your preferences are selected automatically.")
        allowed = {"price_alerts", "anomaly_alerts", "notification_mode"}
        if not values or set(values) - allowed:
            raise HTTPException(status_code=422, detail="Only your notification settings can be changed here.")
        cursor.execute("SELECT price_alerts,anomaly_alerts,notification_mode FROM user_preference WHERE user_id=%s", (user_id,))
        existing = cursor.fetchone() or (True, True, "in_app")
        merged = {
            "price_alerts": values.get("price_alerts", existing[0]),
            "anomaly_alerts": values.get("anomaly_alerts", existing[1]),
            "notification_mode": values.get("notification_mode", existing[2]),
        }
        if not isinstance(merged["price_alerts"], bool) or not isinstance(merged["anomaly_alerts"], bool):
            raise HTTPException(status_code=422, detail="Alert preferences must be true or false.")
        if merged["notification_mode"] not in {"in_app", "email"}:
            raise HTTPException(status_code=422, detail="Choose in_app or email notification mode.")
        cursor.execute(
            """INSERT INTO user_preference(user_id,price_alerts,anomaly_alerts,notification_mode)
               VALUES (%s,%s,%s,%s) ON CONFLICT(user_id) DO UPDATE SET
               price_alerts=EXCLUDED.price_alerts, anomaly_alerts=EXCLUDED.anomaly_alerts,
               notification_mode=EXCLUDED.notification_mode""",
            (user_id, merged["price_alerts"], merged["anomaly_alerts"], merged["notification_mode"]),
        )
        return {"message": "Your preferences were saved."}

    target_keys = {
        "app_user": "user_id", "watchlist": "watchlist_no", "alert": "alert_no",
        "notification": "notification_id", "watchlist_security": "watchlist_no",
    }
    target = target_keys.get(table)
    if request.action in {"modify", "remove"}:
        if target is None:
            raise HTTPException(status_code=422, detail="That action is not supported for this table.")
        target_value = user_id if table == "app_user" else _ensure_target_filter(request, target)
        if table == "watchlist_security":
            if len(request.filters) != 2 or any(item.operator != "eq" for item in request.filters) or {item.column for item in request.filters} != {"watchlist_no", "security_id"}:
                raise HTTPException(status_code=422, detail="Choose exactly one watchlist and one security to remove.")
            security_filter = [f for f in request.filters if f.column == "security_id" and f.operator == "eq"]
            if len(security_filter) != 1:
                raise HTTPException(status_code=422, detail="Choose a specific security in the selected watchlist.")
            sid = _value(security_filter[0].value, "integer")
            cursor.execute(
                """DELETE FROM watchlist_security WHERE user_id=%s AND watchlist_no=%s AND security_id=%s
                   RETURNING security_id""",
                (user_id, target_value, sid),
            )
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="That security is not in your watchlist.")
            return {"message": "Security removed from your watchlist."}

        if table == "app_user":
            if request.filters:
                raise HTTPException(status_code=422, detail="Your account is selected automatically.")
        elif len(request.filters) != 1 or request.filters[0].operator != "eq" or request.filters[0].column != target:
            raise HTTPException(status_code=422, detail=f"Choose only one specific {target} to change or remove.")

        if request.action == "remove":
            if values:
                raise HTTPException(status_code=422, detail="Remove actions do not accept new values.")
            cursor.execute(
                sql.SQL("DELETE FROM public.{} WHERE {}=%s AND {}=%s RETURNING 1").format(
                    sql.Identifier(table), sql.Identifier("user_id"), sql.Identifier(target),
                ),
                (user_id, target_value),
            )
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Your record was not found.")
            return {"message": "Your record was removed."}

        editable = {
            "app_user": {"name", "email"},
            "watchlist": {"name"},
            "alert": {"condition", "target_price", "status"},
            "notification": {"status"},
        }.get(table, set())
        if not values or set(values) - editable:
            raise HTTPException(status_code=422, detail="Only approved fields for your record may be changed.")
        changes = {}
        for key, value in values.items():
            if table == "app_user" and key == "name":
                text = str(value).strip()
                if not text or len(text) > 200:
                    raise HTTPException(status_code=422, detail="Name must contain 1 to 200 characters.")
                changes[key] = text
            elif table == "app_user" and key == "email":
                email = str(value).strip().lower()
                if len(email) > 255 or "@" not in email or email.startswith("@") or email.endswith("@"):
                    raise HTTPException(status_code=422, detail="Enter a valid email address.")
                changes[key] = email
            elif table == "watchlist" and key == "name":
                text = str(value).strip()
                if not text or len(text) > 100:
                    raise HTTPException(status_code=422, detail="Name must contain 1 to 100 characters.")
                changes[key] = text
            elif table == "alert" and key == "condition":
                if value not in {"above", "below"}:
                    raise HTTPException(status_code=422, detail="Condition must be above or below.")
                changes[key] = value
            elif table == "alert" and key == "target_price":
                try:
                    number = Decimal(str(value))
                    if not number.is_finite() or number <= 0: raise InvalidOperation
                except InvalidOperation:
                    raise HTTPException(status_code=422, detail="Target price must be positive.") from None
                changes[key] = number
            elif table == "alert" and key == "status":
                if value not in {"active", "inactive"}:
                    raise HTTPException(status_code=422, detail="Status must be active or inactive.")
                changes[key] = value
            elif table == "notification" and key == "status":
                if value not in {"read", "unread"}:
                    raise HTTPException(status_code=422, detail="Status must be read or unread.")
                changes[key] = value
        assignments = sql.SQL(", ").join(
            sql.SQL("{}=%s").format(sql.Identifier(key)) for key in changes
        )
        cursor.execute(
            sql.SQL("UPDATE public.{} SET {} WHERE {}=%s AND {}=%s RETURNING 1").format(
                sql.Identifier(table), assignments, sql.Identifier("user_id"), sql.Identifier(target),
            ),
            (*changes.values(), user_id, target_value),
        )
        if cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="Your record was not found.")
        return {"message": "Your record was updated."}

    raise HTTPException(status_code=422, detail="That action is not supported.")
