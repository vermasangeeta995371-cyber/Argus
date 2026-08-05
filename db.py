"""
DB helper: economy, shop, inventory, listings, and admin balance operations.
Database: data/bot.db
"""

from __future__ import annotations
import aiosqlite
import os
import datetime
from typing import Optional, List, Dict, Tuple
import random

DB_PATH = os.getenv("BOT_DB_PATH", "data/bot.db")


async def init_db(path: Optional[str] = None):
    path = path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    async with aiosqlite.connect(path) as db:
        # base tables
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS economy (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                balance INTEGER NOT NULL DEFAULT 0,
                last_daily TEXT,
                last_weekly TEXT,
                last_work TEXT,
                last_crime TEXT,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                price INTEGER NOT NULL,
                type TEXT NOT NULL,       -- 'consumable', 'role', 'permanent'
                role_id INTEGER,          -- optional, if type='role'
                category TEXT,
                cooldown_seconds INTEGER DEFAULT 0,
                effect_type TEXT,
                effect_value TEXT,
                UNIQUE(guild_id, name)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS inventory (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                last_used TEXT,           -- ISO timestamp for per-user item cooldown
                PRIMARY KEY (guild_id, user_id, item_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                seller_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                price_per_item INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS afk (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reason TEXT,
                since TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS modlog_channels (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_locales (
                guild_id INTEGER PRIMARY KEY,
                locale TEXT NOT NULL DEFAULT 'en'
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS jackpot (
                guild_id INTEGER PRIMARY KEY,
                amount INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS game_cooldowns (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                game TEXT NOT NULL,
                last_used TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id, game)
            )
            """
        )
        await db.commit()


# -------------------------
# economy helpers
# -------------------------
async def _ensure_economy_row(guild_id: int, user_id: int, path: Optional[str] = None):
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO economy (guild_id, user_id, balance, last_daily, last_weekly, last_work, last_crime) VALUES (?, ?, 0, NULL, NULL, NULL, NULL)",
            (guild_id, user_id),
        )
        await db.commit()


async def get_balance(guild_id: int, user_id: int, path: Optional[str] = None) -> int:
    path = path or DB_PATH
    await _ensure_economy_row(guild_id, user_id, path)
    async with aiosqlite.connect(path) as db:
        cur = await db.execute("SELECT balance FROM economy WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        row = await cur.fetchone()
        return int(row[0]) if row else 0


async def set_balance(guild_id: int, user_id: int, amount: int, path: Optional[str] = None):
    path = path or DB_PATH
    await _ensure_economy_row(guild_id, user_id, path)
    async with aiosqlite.connect(path) as db:
        await db.execute("UPDATE economy SET balance = ? WHERE guild_id = ? AND user_id = ?", (int(amount), guild_id, user_id))
        await db.commit()


async def add_balance(guild_id: int, user_id: int, amount: int, path: Optional[str] = None) -> int:
    path = path or DB_PATH
    await _ensure_economy_row(guild_id, user_id, path)
    async with aiosqlite.connect(path) as db:
        await db.execute("UPDATE economy SET balance = balance + ? WHERE guild_id = ? AND user_id = ?", (int(amount), guild_id, user_id))
        await db.commit()
        cur = await db.execute("SELECT balance FROM economy WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        row = await cur.fetchone()
        return int(row[0]) if row else 0


async def transfer_balance(guild_id: int, from_user: int, to_user: int, amount: int, path: Optional[str] = None) -> bool:
    if amount <= 0:
        return False
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        await db.execute("BEGIN")
        await db.execute("INSERT OR IGNORE INTO economy (guild_id, user_id, balance) VALUES (?, ?, 0)", (guild_id, from_user))
        await db.execute("INSERT OR IGNORE INTO economy (guild_id, user_id, balance) VALUES (?, ?, 0)", (guild_id, to_user))
        cur = await db.execute("SELECT balance FROM economy WHERE guild_id = ? AND user_id = ?", (guild_id, from_user))
        row = await cur.fetchone()
        from_bal = int(row[0]) if row else 0
        if from_bal < amount:
            await db.execute("ROLLBACK")
            return False
        await db.execute("UPDATE economy SET balance = balance - ? WHERE guild_id = ? AND user_id = ?", (amount, guild_id, from_user))
        await db.execute("UPDATE economy SET balance = balance + ? WHERE guild_id = ? AND user_id = ?", (amount, guild_id, to_user))
        await db.commit()
        return True


async def get_leaderboard(guild_id: int, limit: int = 10, path: Optional[str] = None):
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        cur = await db.execute("SELECT user_id, balance FROM economy WHERE guild_id = ? ORDER BY balance DESC LIMIT ?", (guild_id, limit))
        rows = await cur.fetchall()
        return [{"user_id": row[0], "balance": int(row[1])} for row in rows]


# -------------------------
# items / shop
# -------------------------
async def create_item(
    guild_id: int,
    name: str,
    price: int,
    type_: str = "consumable",
    description: Optional[str] = None,
    role_id: Optional[int] = None,
    category: Optional[str] = None,
    cooldown_seconds: int = 0,
    effect_type: Optional[str] = None,
    effect_value: Optional[str] = None,
    path: Optional[str] = None,
) -> int:
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        cur = await db.execute(
            "INSERT INTO items (guild_id, name, description, price, type, role_id, category, cooldown_seconds, effect_type, effect_value) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (guild_id, name, description, int(price), type_, role_id, category, int(cooldown_seconds), effect_type, effect_value),
        )
        await db.commit()
        return cur.lastrowid


async def get_items(guild_id: int, path: Optional[str] = None) -> List[Dict]:
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        cur = await db.execute(
            "SELECT id, name, description, price, type, role_id, category, cooldown_seconds, effect_type, effect_value FROM items WHERE guild_id = ? ORDER BY id ASC",
            (guild_id,),
        )
        rows = await cur.fetchall()
        return [
            {"id": r[0], "name": r[1], "description": r[2], "price": int(r[3]), "type": r[4], "role_id": r[5], "category": r[6], "cooldown_seconds": int(r[7] or 0), "effect_type": r[8], "effect_value": r[9]}
            for r in rows
        ]


async def get_item(guild_id: int, item_id: int, path: Optional[str] = None) -> Optional[Dict]:
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        cur = await db.execute(
            "SELECT id, name, description, price, type, role_id, category, cooldown_seconds, effect_type, effect_value FROM items WHERE guild_id = ? AND id = ?",
            (guild_id, item_id),
        )
        row = await cur.fetchone()
        if not row:
            return None
        return {"id": row[0], "name": row[1], "description": row[2], "price": int(row[3]), "type": row[4], "role_id": row[5], "category": row[6], "cooldown_seconds": int(row[7] or 0), "effect_type": row[8], "effect_value": row[9]}


async def get_item_by_name(guild_id: int, name: str, path: Optional[str] = None) -> Optional[Dict]:
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        cur = await db.execute(
            "SELECT id, name, description, price, type, role_id, category, cooldown_seconds, effect_type, effect_value FROM items WHERE guild_id = ? AND LOWER(name) = LOWER(?)",
            (guild_id, name),
        )
        row = await cur.fetchone()
        if not row:
            return None
        return {"id": row[0], "name": row[1], "description": row[2], "price": int(row[3]), "type": row[4], "role_id": row[5], "category": row[6], "cooldown_seconds": int(row[7] or 0), "effect_type": row[8], "effect_value": row[9]}


async def delete_item(guild_id: int, item_id: int, path: Optional[str] = None) -> int:
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        cur = await db.execute("DELETE FROM items WHERE guild_id = ? AND id = ?", (guild_id, item_id))
        await db.commit()
        return cur.rowcount


# -------------------------
# inventory
# -------------------------
async def get_inventory(guild_id: int, user_id: int, path: Optional[str] = None) -> List[Dict]:
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        cur = await db.execute(
            "SELECT i.item_id, it.name, it.description, it.price, it.type, it.role_id, it.category, it.cooldown_seconds, it.effect_type, it.effect_value, i.quantity, i.last_used FROM inventory i JOIN items it ON i.item_id = it.id WHERE i.guild_id = ? AND i.user_id = ?",
            (guild_id, user_id),
        )
        rows = await cur.fetchall()
        return [
            {
                "item_id": r[0],
                "name": r[1],
                "description": r[2],
                "price": int(r[3]),
                "type": r[4],
                "role_id": r[5],
                "category": r[6],
                "cooldown_seconds": int(r[7] or 0),
                "effect_type": r[8],
                "effect_value": r[9],
                "quantity": int(r[10]),
                "last_used": r[11],
            }
            for r in rows
        ]


async def remove_inventory_item(guild_id: int, user_id: int, item_id: int, quantity: int = 1, path: Optional[str] = None) -> bool:
    path = path or DB_PATH
    if quantity <= 0:
        return False
    async with aiosqlite.connect(path) as db:
        cur = await db.execute("SELECT quantity FROM inventory WHERE guild_id = ? AND user_id = ? AND item_id = ?", (guild_id, user_id, item_id))
        row = await cur.fetchone()
        if not row:
            return False
        cur_qty = int(row[0])
        if cur_qty < quantity:
            return False
        new_qty = cur_qty - quantity
        if new_qty == 0:
            await db.execute("DELETE FROM inventory WHERE guild_id = ? AND user_id = ? AND item_id = ?", (guild_id, user_id, item_id))
        else:
            await db.execute("UPDATE inventory SET quantity = ? WHERE guild_id = ? AND user_id = ? AND item_id = ?", (new_qty, guild_id, user_id, item_id))
        await db.commit()
        return True


async def give_item(guild_id: int, user_id: int, item_id: int, quantity: int = 1, path: Optional[str] = None):
    path = path or DB_PATH
    if quantity <= 0:
        return
    async with aiosqlite.connect(path) as db:
        cur = await db.execute("SELECT quantity FROM inventory WHERE guild_id = ? AND user_id = ? AND item_id = ?", (guild_id, user_id, item_id))
        row = await cur.fetchone()
        if row:
            new_qty = int(row[0]) + quantity
            await db.execute("UPDATE inventory SET quantity = ? WHERE guild_id = ? AND user_id = ? AND item_id = ?", (new_qty, guild_id, user_id, item_id))
        else:
            await db.execute("INSERT INTO inventory (guild_id, user_id, item_id, quantity, last_used) VALUES (?, ?, ?, ?, NULL)", (guild_id, user_id, item_id, quantity))
        await db.commit()


# -------------------------
# buying (atomic)
# -------------------------
async def buy_item(guild_id: int, user_id: int, item_id: int, quantity: int = 1, path: Optional[str] = None) -> Tuple[bool, str, Optional[Dict]]:
    path = path or DB_PATH
    if quantity <= 0:
        return False, "Quantity must be positive.", None
    async with aiosqlite.connect(path) as db:
        try:
            await db.execute("BEGIN")
            cur = await db.execute("SELECT price, type, role_id FROM items WHERE guild_id = ? AND id = ?", (guild_id, item_id))
            row = await cur.fetchone()
            if not row:
                await db.execute("ROLLBACK")
                return False, "Item not found.", None
            price, type_, role_id = int(row[0]), row[1], row[2]
            total = price * int(quantity)
            # ensure economy row
            await db.execute("INSERT OR IGNORE INTO economy (guild_id, user_id, balance) VALUES (?, ?, 0)", (guild_id, user_id))
            cur = await db.execute("SELECT balance FROM economy WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
            row = await cur.fetchone()
            balance = int(row[0]) if row else 0
            if balance < total:
                await db.execute("ROLLBACK")
                return False, "Insufficient balance.", None
            # deduct
            await db.execute("UPDATE economy SET balance = balance - ? WHERE guild_id = ? AND user_id = ?", (total, guild_id, user_id))
            # add to inventory
            cur = await db.execute("SELECT quantity FROM inventory WHERE guild_id = ? AND user_id = ? AND item_id = ?", (guild_id, user_id, item_id))
            r2 = await cur.fetchone()
            if r2:
                new_qty = int(r2[0]) + int(quantity)
                await db.execute("UPDATE inventory SET quantity = ? WHERE guild_id = ? AND user_id = ? AND item_id = ?", (new_qty, guild_id, user_id, item_id))
            else:
                await db.execute("INSERT INTO inventory (guild_id, user_id, item_id, quantity, last_used) VALUES (?, ?, ?, ?, NULL)", (guild_id, user_id, item_id, quantity))
            await db.commit()
            item = await get_item(guild_id, item_id, path)
            return True, f"Purchased {quantity}x {item['name'] if item else item_id}.", item
        except Exception as e:
            await db.execute("ROLLBACK")
            return False, f"Database error: {e}", None


# -------------------------
# listings / marketplace
# -------------------------
async def create_listing(guild_id: int, seller_id: int, item_id: int, quantity: int, price_per_item: int, path: Optional[str] = None) -> Tuple[bool, str, Optional[int]]:
    """
    Create a marketplace listing. Items are moved into escrow (removed from seller inventory).
    Returns (success, message, listing_id)
    """
    path = path or DB_PATH
    if quantity <= 0 or price_per_item <= 0:
        return False, "Quantity and price must be positive.", None
    async with aiosqlite.connect(path) as db:
        try:
            await db.execute("BEGIN")
            # check seller inventory
            cur = await db.execute("SELECT quantity FROM inventory WHERE guild_id = ? AND user_id = ? AND item_id = ?", (guild_id, seller_id, item_id))
            row = await cur.fetchone()
            if not row or int(row[0]) < quantity:
                await db.execute("ROLLBACK")
                return False, "Insufficient items to list.", None
            # deduct inventory (escrow)
            new_qty = int(row[0]) - quantity
            if new_qty == 0:
                await db.execute("DELETE FROM inventory WHERE guild_id = ? AND user_id = ? AND item_id = ?", (guild_id, seller_id, item_id))
            else:
                await db.execute("UPDATE inventory SET quantity = ? WHERE guild_id = ? AND user_id = ? AND item_id = ?", (new_qty, guild_id, seller_id, item_id))
            # create listing
            now = datetime.datetime.utcnow().isoformat()
            cur = await db.execute("INSERT INTO listings (guild_id, seller_id, item_id, quantity, price_per_item, created_at, active) VALUES (?, ?, ?, ?, ?, ?, 1)", (guild_id, seller_id, item_id, quantity, price_per_item, now))
            lid = cur.lastrowid
            await db.commit()
            return True, "Listing created.", lid
        except Exception as e:
            await db.execute("ROLLBACK")
            return False, f"DB error: {e}", None


async def get_listings(guild_id: int, active_only: bool = True, path: Optional[str] = None) -> List[Dict]:
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        if active_only:
            cur = await db.execute("SELECT id, seller_id, item_id, quantity, price_per_item, created_at FROM listings WHERE guild_id = ? AND active = 1 ORDER BY id ASC", (guild_id,))
        else:
            cur = await db.execute("SELECT id, seller_id, item_id, quantity, price_per_item, created_at FROM listings WHERE guild_id = ? ORDER BY id ASC", (guild_id,))
        rows = await cur.fetchall()
        return [{"id": r[0], "seller_id": r[1], "item_id": r[2], "quantity": int(r[3]), "price_per_item": int(r[4]), "created_at": r[5]} for r in rows]


async def get_listing(guild_id: int, listing_id: int, path: Optional[str] = None) -> Optional[Dict]:
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        cur = await db.execute(
            "SELECT id, seller_id, item_id, quantity, price_per_item, created_at, active FROM listings WHERE guild_id = ? AND id = ?",
            (guild_id, listing_id),
        )
        row = await cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "seller_id": row[1],
            "item_id": row[2],
            "quantity": int(row[3]),
            "price_per_item": int(row[4]),
            "created_at": row[5],
            "active": int(row[6]),
        }


async def buy_listing(guild_id: int, buyer_id: int, listing_id: int, quantity: int, path: Optional[str] = None) -> Tuple[bool, str]:
    """
    Buy quantity of a listing. Atomic operation:
    - check listing active/available, buyer balance
    - deduct buyer balance, credit seller, transfer items to buyer inventory
    - update or deactivate listing
    """
    path = path or DB_PATH
    if quantity <= 0:
        return False, "Quantity must be positive."
    async with aiosqlite.connect(path) as db:
        try:
            await db.execute("BEGIN")
            cur = await db.execute("SELECT seller_id, item_id, quantity, price_per_item, active FROM listings WHERE id = ? AND guild_id = ?", (listing_id, guild_id))
            row = await cur.fetchone()
            if not row:
                await db.execute("ROLLBACK")
                return False, "Listing not found."
            seller_id, item_id, avail_qty, price_per_item, active = row[0], row[1], int(row[2]), int(row[3]), int(row[4])
            if active != 1 or avail_qty <= 0:
                await db.execute("ROLLBACK")
                return False, "Listing not available."
            if quantity > avail_qty:
                await db.execute("ROLLBACK")
                return False, "Not enough quantity in listing."
            total = price_per_item * quantity
            # ensure buyer row
            await db.execute("INSERT OR IGNORE INTO economy (guild_id, user_id, balance) VALUES (?, ?, 0)", (guild_id, buyer_id))
            cur = await db.execute("SELECT balance FROM economy WHERE guild_id = ? AND user_id = ?", (guild_id, buyer_id))
            brow = await cur.fetchone()
            balance = int(brow[0]) if brow else 0
            if balance < total:
                await db.execute("ROLLBACK")
                return False, "Buyer has insufficient balance."
            # transfer funds
            await db.execute("UPDATE economy SET balance = balance - ? WHERE guild_id = ? AND user_id = ?", (total, guild_id, buyer_id))
            await db.execute("INSERT OR IGNORE INTO economy (guild_id, user_id, balance) VALUES (?, ?, 0)", (guild_id, seller_id))
            await db.execute("UPDATE economy SET balance = balance + ? WHERE guild_id = ? AND user_id = ?", (total, guild_id, seller_id))
            # transfer items to buyer inventory
            cur = await db.execute("SELECT quantity FROM inventory WHERE guild_id = ? AND user_id = ? AND item_id = ?", (guild_id, buyer_id, item_id))
            br = await cur.fetchone()
            if br:
                new_bqty = int(br[0]) + quantity
                await db.execute("UPDATE inventory SET quantity = ? WHERE guild_id = ? AND user_id = ? AND item_id = ?", (new_bqty, guild_id, buyer_id, item_id))
            else:
                await db.execute("INSERT INTO inventory (guild_id, user_id, item_id, quantity, last_used) VALUES (?, ?, ?, ?, NULL)", (guild_id, buyer_id, item_id, quantity))
            # update listing
            new_avail = avail_qty - quantity
            if new_avail == 0:
                await db.execute("UPDATE listings SET quantity = 0, active = 0 WHERE id = ?", (listing_id,))
            else:
                await db.execute("UPDATE listings SET quantity = ? WHERE id = ?", (new_avail, listing_id))
            await db.commit()
            return True, "Purchase successful."
        except Exception as e:
            await db.execute("ROLLBACK")
            return False, f"DB error: {e}"


# -------------------------
# server / guild settings
# -------------------------
async def set_modlog_channel(guild_id: int, channel_id: int, path: Optional[str] = None):
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT INTO modlog_channels (guild_id, channel_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id",
            (guild_id, channel_id),
        )
        await db.commit()


async def get_modlog_channel(guild_id: int, path: Optional[str] = None) -> Optional[int]:
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        cur = await db.execute("SELECT channel_id FROM modlog_channels WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
        return int(row[0]) if row else None


async def clear_modlog_channel(guild_id: int, path: Optional[str] = None):
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        await db.execute("DELETE FROM modlog_channels WHERE guild_id = ?", (guild_id,))
        await db.commit()


async def get_guild_locale(guild_id: int, path: Optional[str] = None) -> str:
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        cur = await db.execute("SELECT locale FROM guild_locales WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
        if row:
            return row[0]
        await db.execute("INSERT INTO guild_locales (guild_id, locale) VALUES (?, 'en')", (guild_id,))
        await db.commit()
        return "en"


async def set_guild_locale(guild_id: int, locale: str, path: Optional[str] = None):
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT INTO guild_locales (guild_id, locale) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET locale = excluded.locale",
            (guild_id, locale),
        )
        await db.commit()


async def add_warn(guild_id: int, user_id: int, moderator_id: int, reason: str, path: Optional[str] = None) -> int:
    path = path or DB_PATH
    now = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(path) as db:
        cur = await db.execute(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, moderator_id, reason, now),
        )
        await db.commit()
        return cur.lastrowid


async def get_warns(guild_id: int, user_id: int, path: Optional[str] = None) -> List[Dict]:
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        cur = await db.execute(
            "SELECT id, moderator_id, reason, created_at FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id ASC",
            (guild_id, user_id),
        )
        rows = await cur.fetchall()
        return [{"id": r[0], "moderator_id": int(r[1]), "reason": r[2], "created_at": r[3]} for r in rows]


async def remove_warn(guild_id: int, warn_id: int, path: Optional[str] = None) -> int:
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        cur = await db.execute("DELETE FROM warnings WHERE guild_id = ? AND id = ?", (guild_id, warn_id))
        await db.commit()
        return cur.rowcount


# -------------------------
# afk / presence
# -------------------------
async def set_afk(guild_id: int, user_id: int, reason: str, path: Optional[str] = None):
    path = path or DB_PATH
    now = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT INTO afk (guild_id, user_id, reason, since) VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET reason = excluded.reason, since = excluded.since",
            (guild_id, user_id, reason, now),
        )
        await db.commit()


async def get_afk(guild_id: int, user_id: int, path: Optional[str] = None) -> Optional[Dict]:
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        cur = await db.execute("SELECT reason, since FROM afk WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        row = await cur.fetchone()
        if not row:
            return None
        return {"reason": row[0], "since": row[1]}


async def remove_afk(guild_id: int, user_id: int, path: Optional[str] = None) -> bool:
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        cur = await db.execute("DELETE FROM afk WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        await db.commit()
        return cur.rowcount > 0


# -------------------------
# jackpot / mini-games
# -------------------------
async def add_to_jackpot(guild_id: int, amount: int, path: Optional[str] = None) -> int:
    if amount <= 0:
        return 0
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        await db.execute("INSERT OR IGNORE INTO jackpot (guild_id, amount) VALUES (?, 0)", (guild_id,))
        await db.execute("UPDATE jackpot SET amount = amount + ? WHERE guild_id = ?", (amount, guild_id))
        await db.commit()
        cur = await db.execute("SELECT amount FROM jackpot WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
        return int(row[0]) if row else 0


async def get_jackpot(guild_id: int, path: Optional[str] = None) -> int:
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        await db.execute("INSERT OR IGNORE INTO jackpot (guild_id, amount) VALUES (?, 0)", (guild_id,))
        cur = await db.execute("SELECT amount FROM jackpot WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
        return int(row[0]) if row else 0


async def claim_jackpot(guild_id: int, path: Optional[str] = None) -> int:
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        await db.execute("BEGIN")
        cur = await db.execute("SELECT amount FROM jackpot WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
        amount = int(row[0]) if row else 0
        await db.execute("INSERT OR IGNORE INTO jackpot (guild_id, amount) VALUES (?, 0)", (guild_id,))
        await db.execute("UPDATE jackpot SET amount = 0 WHERE guild_id = ?", (guild_id,))
        await db.commit()
        return amount


async def can_use_game(guild_id: int, user_id: int, game: str, cooldown: int, path: Optional[str] = None) -> Tuple[bool, Optional[int]]:
    path = path or DB_PATH
    now = datetime.datetime.utcnow()
    async with aiosqlite.connect(path) as db:
        cur = await db.execute("SELECT last_used FROM game_cooldowns WHERE guild_id = ? AND user_id = ? AND game = ?", (guild_id, user_id, game))
        row = await cur.fetchone()
        if not row:
            return True, None
        try:
            last_used = datetime.datetime.fromisoformat(row[0])
        except Exception:
            return True, None
        delta = (now - last_used).total_seconds()
        if delta >= cooldown:
            return True, None
        return False, int(cooldown - delta)


async def set_game_cooldown(guild_id: int, user_id: int, game: str, when: datetime.datetime, path: Optional[str] = None):
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT INTO game_cooldowns (guild_id, user_id, game, last_used) VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id, game) DO UPDATE SET last_used = excluded.last_used",
            (guild_id, user_id, game, when.isoformat()),
        )
        await db.commit()


async def set_inventory_last_used(guild_id: int, user_id: int, item_id: int, path: Optional[str] = None):
    path = path or DB_PATH
    now = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "UPDATE inventory SET last_used = ? WHERE guild_id = ? AND user_id = ? AND item_id = ?",
            (now, guild_id, user_id, item_id),
        )
        await db.commit()


async def cancel_listing(guild_id: int, seller_id: int, listing_id: int, path: Optional[str] = None) -> Tuple[bool, str]:
    """
    Cancel a listing and return items to the seller (only seller or admins should call this).
    """
    path = path or DB_PATH
    async with aiosqlite.connect(path) as db:
        try:
            await db.execute("BEGIN")
            cur = await db.execute("SELECT seller_id, item_id, quantity, active FROM listings WHERE id = ? AND guild_id = ?", (listing_id, guild_id))
            row = await cur.fetchone()
            if not row:
                await db.execute("ROLLBACK")
                return False, "Listing not found."
            seller, item_id, qty, active = row[0], row[1], int(row[2]), int(row[3])
            if seller != seller_id:
                await db.execute("ROLLBACK")
                return False, "Only the seller can cancel this listing."
            if active != 1:
                await db.execute("ROLLBACK")
                return False, "Listing already inactive."
            # return items to seller inventory
            cur = await db.execute("SELECT quantity FROM inventory WHERE guild_id = ? AND user_id = ? AND item_id = ?", (guild_id, seller_id, item_id))
            r2 = await cur.fetchone()
            if r2:
                new_q = int(r2[0]) + qty
                await db.execute("UPDATE inventory SET quantity = ? WHERE guild_id = ? AND user_id = ? AND item_id = ?", (new_q, guild_id, seller_id, item_id))
            else:
                await db.execute("INSERT INTO inventory (guild_id, user_id, item_id, quantity, last_used) VALUES (?, ?, ?, ?, NULL)", (guild_id, seller_id, item_id, qty))
            await db.execute("UPDATE listings SET active = 0 WHERE id = ?", (listing_id,))
            await db.commit()
            return True, "Listing cancelled and items returned."
        except Exception as e:
            await db.execute("ROLLBACK")
            return False, f"DB error: {e}"