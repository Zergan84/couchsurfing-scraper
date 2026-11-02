"""
message_generator.py - Генератор персонализированных запросов на Couchsurfing.

Формирует живое, уважительное и детально проработанное сообщение для хоста:
1. Теплое личное приветствие с отсылкой к конкретному интересу хоста (кулинария, искусство, языки, технологии, спорт и т.д.).
2. Четкие даты заезда/выезда и понятная цель поездки (короткая остановка в Токио перед работой лыжным инструктором в Club Med Tomamu на Хоккайдо).
3. Доказательство надежности гостя: 10+ лет на CS, аккуратность, уважение к границам и правилам, дневная занятость в городе.
4. Предложение комфортного взаимодействия: совместный ужин / истории за чаем / напитком, без навязчивости.
5. Органичное включение кодового слова (secret code), если оно требуется в профиле хоста.
"""

import re
from datetime import datetime
from typing import Any, Dict, Optional


def format_date_range(check_in: str, check_out: str) -> str:
    """Форматирует даты в читаемый вид, например: Nov 11th – 14th, 2026."""
    try:
        d_in = datetime.strptime(check_in.strip(), "%Y-%m-%d")
        d_out = datetime.strptime(check_out.strip(), "%Y-%m-%d")

        month_in = d_in.strftime("%b")
        month_out = d_out.strftime("%b")

        day_in_suffix = "th" if 11 <= d_in.day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d_in.day % 10, "th")
        day_out_suffix = "th" if 11 <= d_out.day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d_out.day % 10, "th")

        if d_in.year == d_out.year and d_in.month == d_out.month:
            return f"{month_in} {d_in.day}{day_in_suffix} – {d_out.day}{day_out_suffix}, {d_in.year}"
        else:
            return f"{month_in} {d_in.day}{day_in_suffix} – {month_out} {d_out.day}{day_out_suffix}, {d_in.year}"
    except Exception:
        return f"{check_in} – {check_out}"


def extract_hook_and_topics(host: Dict[str, Any]) -> str:
    """
    Анализирует описание хоста и генерирует уникальный персонализированный хук.
    """
    about = (host.get("about_me_clean") or host.get("about_me") or "").lower()
    name = host.get("clean_name") or host.get("name") or "there"

    # 1. Кулинария / Еда
    if any(k in about for k in ("food", "cook", "ramen", "sushi", "chef", "wine", "beer", "sake", "tea", "baking", "foodie")):
        return (
            f"I was really drawn to your profile and loved seeing your passion for good food and cooking. "
            f"As someone who loves exploring authentic local flavors and sharing a homemade meal, "
            f"your approach to hosting immediately stood out."
        )

    # 2. Спорт / Горы / Активный отдых
    if any(k in about for k in ("hiking", "mountain", "climb", "running", "ski", "snowboard", "surf", "outdoor", "cycling", "bike")):
        return (
            f"I loved reading your bio, especially your enthusiasm for the outdoors and staying active. "
            f"As an outdoor enthusiast and ski instructor heading up north for the season, "
            f"it's always refreshing to connect with people who share that energy."
        )

    # 3. Искусство / Дизайн / Музыка / Фотография
    if any(k in about for k in ("art", "design", "photo", "music", "guitar", "piano", "cinema", "drawing", "creative")):
        return (
            f"I really enjoyed reading your profile, especially your interest in creative work and art. "
            f"It's always inspiring to meet hosts with an artistic and open mindset on Couchsurfing."
        )

    # 4. Языки / Культурный обмен
    if any(k in about for k in ("language", "cultural exchange", "learn", "teach", "practice", "french", "spanish", "english")):
        return (
            f"Your focus on genuine cultural and language exchange really resonated with me. "
            f"After many years on CS, that meaningful connection is still my favorite part of the community."
        )

    # 5. Путешествия / Бэкпэкинг
    if any(k in about for k in ("backpack", "travel", "solo trip", "countries", "hitchhik", "world")):
        return (
            f"I came across your profile and was really impressed by your travel experiences and perspective on the road. "
            f"It's always wonderful to connect with a fellow traveler who appreciates the true spirit of Couchsurfing."
        )

    # 6. Технологии / Программирование / Стартапы
    if any(k in about for k in ("program", "software", "developer", "startup", "engineer", "tech", "data", "ai")):
        return (
            f"I was happy to read through your background in tech and your thoughtful approach to hosting. "
            f"Your perspective on sharing experiences and hosting travelers felt very welcoming."
        )

    # Фолбэк на естественный теплый тон
    return (
        f"I spent some time reading through your profile and was really impressed by your thoughtful approach "
        f"and great recommendations from fellow Couchsurfers."
    )


def generate_stay_request(
    host: Dict[str, Any],
    check_in: str = "2026-11-11",
    check_out: str = "2026-11-14",
    guest_context: Optional[str] = None,
) -> str:
    """
    Генерирует строго персонализированный текст запроса для конкретного хоста.
    """
    clean_name = host.get("clean_name") or host.get("name") or "there"
    date_str = format_date_range(check_in, check_out)
    hook = extract_hook_and_topics(host)

    # Проверка секретного слова
    secret_code = host.get("secret_code_hint") or ""
    has_secret = host.get("secret_code_detected", False)

    # Размещение
    sleeping = host.get("sleeping_arrangement", "Not specified")
    sleeping_phrase = ""
    if sleeping and sleeping != "Not specified":
        sleeping_phrase = f"I also saw that you offer a {sleeping.lower()}, which suits me completely."

    # Параграф 1: Персонализированное приветствие и хук
    greeting = f"Hi {clean_name}!"
    p1 = f"{greeting} Hope you're having a wonderful week. {hook}"

    # Если есть кодовое слово, элегантно вставляем подтверждение прочтения
    if has_secret and secret_code and len(secret_code) < 30 and not "profile reading" in secret_code.lower():
        p1 += f" (And right away, making sure I read your home details carefully: '{secret_code}'! :))"

    # Параграф 2: Даты и цель поездки (лыжный инструктор)
    p2 = (
        f"I'm writing to ask if you might be available to host me in Tokyo for a few days from "
        f"{date_str}. I am on my way to Hokkaido, where I'll be working the upcoming winter season "
        f"as a professional ski instructor at Club Med Tomamu, and I'm taking a couple of days in "
        f"Tokyo to acclimatize, pick up some winter gear, and enjoy the city's neighborhoods."
    )

    # Параграф 3: Опыт на CS, уважение к границам, распорядок дня
    p3 = (
        f"I've been hosting and surfing on Couchsurfing for over 10 years, so I deeply appreciate "
        f"what makes hosting comfortable: being very tidy, respectful of your space and quiet hours, "
        f"and having zero expectations of you acting as a full-time guide. {sleeping_phrase} "
        f"During the day, I'll be out and about exploring the city, so I certainly won't crowd your routine."
    )

    # Параграф 4: Вечернее общение / совместный ужин и прощание
    p4 = (
        f"In the evenings, I’d be delighted to cook a tasty meal together, share some fun stories from "
        f"the mountains over a tea or a drink, or just give you your peaceful space if you have a busy week. "
        f"Thank you very much for your time and hospitality, and wishing you all the best regardless!"
    )

    signoff = "Warm regards,\nAndrey"

    paragraphs = [p1, p2, p3, p4, signoff]
    return "\n\n".join(paragraphs)
