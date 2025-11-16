from datetime import datetime
from .. import users_col, questions_col, attempts_col


# ---------------------------
# USERS COLLECTION
# ---------------------------

def create_user(user_id, name):
    """Create user if not exists."""
    user = users_col.find_one({"user_id": user_id})
    if not user:
        users_col.insert_one({
            "user_id": user_id,
            "name": name,
            "joined_at": datetime.utcnow(),
            "total_attempts": 0,
            "correct_answers": 0
        })
        return True
    return False


def get_user(user_id):
    return users_col.find_one({"user_id": user_id})


def update_user_stats(user_id, correct=False):
    update_query = {"$inc": {"total_attempts": 1}}
    if correct:
        update_query["$inc"]["correct_answers"] = 1

    users_col.update_one(
        {"user_id": user_id},
        update_query
    )


# ---------------------------
# QUESTIONS COLLECTION
# ---------------------------

def add_question(question_data: dict):
    """Insert a science quiz question."""
    questions_col.insert_one(question_data)


def get_random_question(category=None):
    """Get a random question from MongoDB."""
    query = {}
    if category:
        query["category"] = category

    pipeline = [{"$match": query}, {"$sample": {"size": 1}}]
    result = list(questions_col.aggregate(pipeline))

    return result[0] if result else None


def get_question_by_id(qid):
    return questions_col.find_one({"_id": qid})


# ---------------------------
# ATTEMPTS COLLECTION
# ---------------------------

def save_attempt(user_id, qid, user_answer, correct):
    attempts_col.insert_one({
        "user_id": user_id,
        "question_id": qid,
        "answer": user_answer,
        "correct": correct,
        "timestamp": datetime.utcnow()
    })


def get_user_attempts(user_id):
    return list(attempts_col.find({"user_id": user_id}))


def get_top_users(limit=10):
    """Leaderboard (based on correct answers)."""
    return list(
        users_col.find().sort("correct_answers", -1).limit(limit)
    )
