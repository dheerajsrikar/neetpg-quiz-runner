import json
import os
import time
import random
import requests

# ============================================================
# NEET PG INLINE QUIZ BOT — 10 QUESTION TEST
# ============================================================

CHANNEL = "@neetpgquizs"
TOKEN = os.environ["BOT_TOKEN"]

START_FROM = int(os.environ.get("START_FROM", "1"))
MAX_QUESTIONS = int(os.environ.get("MAX_QUESTIONS", "10"))
QUESTION_TIME = int(os.environ.get("QUESTION_TIME", "15"))

# Test file
QUIZ_FILE = os.environ.get(
    "QUIZ_FILE",
    "TEST_10_QUESTIONS.json"
)

BASE_URL = f"https://api.telegram.org/bot{TOKEN}"


def telegram(method, data=None, timeout=30):
    try:
        response = requests.post(
            f"{BASE_URL}/{method}",
            data=data or {},
            timeout=timeout
        )

        try:
            result = response.json()
        except ValueError:
            print(
                f"Telegram {method}: invalid JSON "
                f"(HTTP {response.status_code})"
            )
            return {"ok": False}

        if not result.get("ok"):
            print(f"Telegram {method} error: {result}")

        return result

    except requests.RequestException as e:
        print(f"{method} connection error: {e}")
        return {"ok": False}


# ============================================================
# LOAD + VALIDATE JSON
# ============================================================

if not os.path.exists(QUIZ_FILE):
    raise FileNotFoundError(
        f"Quiz file not found: {QUIZ_FILE}"
    )

with open(QUIZ_FILE, "r", encoding="utf-8") as f:
    all_questions = json.load(f)

if not isinstance(all_questions, list) or not all_questions:
    raise ValueError("Quiz JSON is empty or invalid.")

for q in all_questions:
    required = (
        "number",
        "question",
        "options",
        "correct_index"
    )

    missing = [key for key in required if key not in q]

    if missing:
        raise ValueError(
            f"Q{q.get('number', '?')}: missing fields: {missing}"
        )

    if not isinstance(q["options"], list):
        raise ValueError(
            f"Q{q['number']}: options must be a list."
        )

    if len(q["options"]) != 4:
        raise ValueError(
            f"Q{q['number']}: must have exactly 4 options."
        )

    if len(set(map(str, q["options"]))) != 4:
        raise ValueError(
            f"Q{q['number']}: duplicate options found."
        )

    if not isinstance(q["correct_index"], int):
        raise ValueError(
            f"Q{q['number']}: correct_index must be an integer."
        )

    if not 0 <= q["correct_index"] < 4:
        raise ValueError(
            f"Q{q['number']}: invalid correct_index."
        )

    if not isinstance(q["question"], str) or not q["question"].strip():
        raise ValueError(
            f"Q{q['number']}: empty question."
        )


# Select questions
questions = [
    q for q in all_questions
    if int(q["number"]) >= START_FROM
]

random.shuffle(questions)
questions = questions[:MAX_QUESTIONS]

if not questions:
    raise ValueError("No questions available after filtering.")

print("==============================================")
print("🔥 NEET PG 10 QUESTION TEST BOT")
print("==============================================")
print(f"Quiz file: {QUIZ_FILE}")
print(f"Loaded: {len(all_questions)}")
print(f"Posting: {len(questions)}")
print(f"Time/question: {QUESTION_TIME} seconds")
print("Question order: RANDOM")
print("Option order: RANDOM")
print("==============================================")


# ============================================================
# REMOVE WEBHOOK / CLEAR PENDING UPDATES
# ============================================================

delete_result = telegram(
    "deleteWebhook",
    {"drop_pending_updates": True}
)

if not delete_result.get("ok"):
    raise RuntimeError(
        "Could not remove Telegram webhook."
    )

offset = 0


# ============================================================
# SEND QUESTION
# ============================================================

def send_question(q, display_number):

    options = q["options"][:]

    # Preserve the correct answer before shuffling.
    original_correct_answer = options[q["correct_index"]]

    random.shuffle(options)

    # Find the new position after shuffle.
    new_correct_index = options.index(
        original_correct_answer
    )

    keyboard = []

    for i, option in enumerate(options):
        keyboard.append([
            {
                "text": f"{chr(65 + i)}. {option}",
                "callback_data": f"NEETQ|{display_number}|{i}"
            }
        ])

    text = (
        f"🔥 Q{display_number}/{len(questions)}\n\n"
        f"{q['question']}"
    )

    result = telegram(
        "sendMessage",
        {
            "chat_id": CHANNEL,
            "text": text,
            "reply_markup": json.dumps(
                {"inline_keyboard": keyboard},
                ensure_ascii=False
            )
        }
    )

    if not result.get("ok"):
        return None, None

    message_id = result["result"]["message_id"]

    return message_id, new_correct_index


# ============================================================
# CLOSE QUESTION
# ============================================================

def close_question(message_id):

    telegram(
        "editMessageReplyMarkup",
        {
            "chat_id": CHANNEL,
            "message_id": message_id,
            "reply_markup": json.dumps(
                {"inline_keyboard": []}
            )
        }
    )


# ============================================================
# PROCESS ANSWER
# ============================================================

def process_callback(
    update,
    active_question,
    active_message_id,
    correct_index,
    answered_users
):

    callback = update.get("callback_query")

    if not callback:
        return

    callback_id = callback.get("id")
    data = callback.get("data", "")

    if not data.startswith("NEETQ|"):
        return

    try:
        _, question_number, selected_index = data.split("|")
        question_number = int(question_number)
        selected_index = int(selected_index)

    except (ValueError, TypeError):
        telegram(
            "answerCallbackQuery",
            {
                "callback_query_id": callback_id,
                "text": "⚠️ Invalid answer.",
                "show_alert": True,
                "cache_time": 0
            }
        )
        return

    message = callback.get("message")
    user = callback.get("from", {})
    user_id = user.get("id")

    if user_id is None or not message:
        return

    message_id = message.get("message_id")

    # Reject old question.
    if (
        question_number != active_question
        or message_id != active_message_id
    ):
        telegram(
            "answerCallbackQuery",
            {
                "callback_query_id": callback_id,
                "text": "⏳ This question has closed.",
                "show_alert": True,
                "cache_time": 0
            }
        )
        return

    # One attempt per user.
    if user_id in answered_users:
        telegram(
            "answerCallbackQuery",
            {
                "callback_query_id": callback_id,
                "text": "⚠️ You already answered this question.",
                "show_alert": True,
                "cache_time": 0
            }
        )
        return

    answered_users.add(user_id)

    if selected_index == correct_index:
        feedback = "✅ Correct!"
    else:
        feedback = "❌ Incorrect!"

    telegram(
        "answerCallbackQuery",
        {
            "callback_query_id": callback_id,
            "text": feedback,
            "show_alert": True,
            "cache_time": 0
        }
    )


# ============================================================
# MAIN QUIZ
# ============================================================

sent = 0

for display_number, q in enumerate(questions, start=1):

    print(
        f"\n🔥 Posting Q{display_number}/{len(questions)} "
        f"(Original Q{q['number']})"
    )

    message_id, correct_index = send_question(
        q,
        display_number
    )

    if message_id is None:
        print("❌ Could not post question. Stopping.")
        break

    sent += 1
    answered_users = set()
    start_time = time.monotonic()

    # Accept answers for QUESTION_TIME seconds.
    while (
        time.monotonic() - start_time
        < QUESTION_TIME
    ):

        elapsed = time.monotonic() - start_time
        remaining = QUESTION_TIME - elapsed

        timeout = max(
            1,
            min(5, int(remaining))
        )

        try:
            result = requests.get(
                f"{BASE_URL}/getUpdates",
                params={
                    "offset": offset,
                    "timeout": timeout,
                    "allowed_updates": json.dumps(
                        ["callback_query"]
                    )
                },
                timeout=timeout + 10
            ).json()

        except requests.RequestException as e:
            print(f"⚠️ getUpdates error: {e}")
            continue

        except ValueError:
            print("⚠️ Invalid Telegram response.")
            continue

        if not result.get("ok"):

            if result.get("error_code") == 409:
                raise RuntimeError(
                    "❌ 409 CONFLICT: another bot instance "
                    "is already using getUpdates. "
                    "Stop the other workflow/process."
                )

            continue

        for update in result.get("result", []):

            offset = update["update_id"] + 1

            process_callback(
                update,
                display_number,
                message_id,
                correct_index,
                answered_users
            )

    close_question(message_id)

    print(
        f"⏱️ Q{display_number} closed | "
        f"answered: {len(answered_users)}"
    )

    if sent < len(questions):
        time.sleep(1)


# ============================================================
# FINISHED
# ============================================================

print("\n==============================================")
print("✅ 10 QUESTION TEST COMPLETED")
print(f"✅ Questions posted: {sent}")
print(f"📄 Quiz file: {QUIZ_FILE}")
print("==============================================")
