from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import os

# ================================
# 🔗 MongoDB Connection
# ================================
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo["GameBot"]
users_col = db["users"]


# ================================
# 👤 User Database Functions
# ================================

async def add_user(user_id: int, username: str = None):
    """
    Add a new user to the database if not exists.
    """
    check = await users_col.find_one({"user_id": user_id})
    if check:
        return False

    data = {
        "user_id": user_id,
        "username": username,
        "coins": 0,
        "level": 1,
        "created_at": datetime.utcnow()
    }

    await users_col.insert_one(data)
    return True


async def get_user(user_id: int):
    """
    Returns full user data.
    """
    user = await users_col.find_one({"user_id": user_id})
    return user


async def update_user(user_id: int, data: dict):
    """
    Update user's specific fields.
    """
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": data},
    )
    return True


async def add_coins(user_id: int, amount: int):
    """
    Adds coins to a user.
    """
    await users_col.update_one(
        {"user_id": user_id},
        {"$inc": {"coins": amount}}
    )


async def get_top_users(limit: int = 10):
    """
    Returns top users by coins.
    """
    cursor = users_col.find().sort("coins", -1).limit(limit)
    return await cursor.to_list(length=limit)
