from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder
from texts import TEXTS
from database import Event

def get_admin_chat_keyboard(user_id: int, username: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="Открыть чат",
            url=f"tg://user?id={user_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="История сообщений",
            callback_data=f"history_{user_id}"
        )
    )
    return builder.as_markup()

def get_admin_main_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="Список активных чатов",
            callback_data="list_chats"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Создать рассылку",
            callback_data="create_broadcast"
        )
    )
    return builder.as_markup()

def get_language_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")
            ]
        ]
    )
    return keyboard

def get_phone_number_keyboard(lang: str = "en") -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(
                text="📱 Share phone number" if lang == "en" else "📱 Поделиться номером телефона",
                request_contact=True
            )]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return keyboard

def get_main_keyboard(lang: str = "en") -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📅 Events" if lang == "en" else "📅 События"),
                KeyboardButton(text="🎯 My Events" if lang == "en" else "🎯 Мои события")
            ]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_events_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    if lang == "ru":
        builder.row(InlineKeyboardButton(
            text="➕ Создать событие",
            callback_data="create_event"
        ))
        builder.row(InlineKeyboardButton(
            text="🔍 Доступные события",
            callback_data="available_events"
        ))
        builder.row(InlineKeyboardButton(
            text="🎯 Мои события",
            callback_data="my_events"
        ))
        builder.row(InlineKeyboardButton(
            text="📜 Прошедшие события",
            callback_data="past_events"
        ))
    else:
        builder.row(InlineKeyboardButton(
            text="➕ Create Event",
            callback_data="create_event"
        ))
        builder.row(InlineKeyboardButton(
            text="🔍 Available Events",
            callback_data="available_events"
        ))
        builder.row(InlineKeyboardButton(
            text="🎯 My Events",
            callback_data="my_events"
        ))
        builder.row(InlineKeyboardButton(
            text="📜 Past Events",
            callback_data="past_events"
        ))
    
    return builder.as_markup()

def get_event_actions_keyboard(event_id: int, is_participant: bool, is_creator: bool, lang: str = "en") -> InlineKeyboardMarkup:
    buttons = []
    
    if not is_creator and not is_participant:
        buttons.append([InlineKeyboardButton(
            text="✅ Join" if lang == "en" else "✅ Присоединиться",
            callback_data=f"join_event:{event_id}"
        )])
    elif not is_creator and is_participant:
        buttons.append([InlineKeyboardButton(
            text="❌ Leave" if lang == "en" else "❌ Покинуть",
            callback_data=f"leave_event:{event_id}"
        )])
    
    if is_creator:
        buttons.append([InlineKeyboardButton(
            text="🚫 Cancel Event" if lang == "en" else "🚫 Отменить событие",
            callback_data=f"cancel_event:{event_id}"
        )])
    
    buttons.append([InlineKeyboardButton(
        text="◀️ Back" if lang == "en" else "◀️ Назад",
        callback_data="events_menu"
    )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_broadcast_confirmation_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Send to all" if lang == "en" else "✅ Отправить всем", callback_data="broadcast:all"),
                InlineKeyboardButton(text="🇬🇧 English only" if lang == "en" else "🇬🇧 Только английский", callback_data="broadcast:en")
            ],
            [
                InlineKeyboardButton(text="🇷🇺 Russian only" if lang == "en" else "🇷🇺 Только русский", callback_data="broadcast:ru"),
                InlineKeyboardButton(text="❌ Cancel" if lang == "en" else "❌ Отмена", callback_data="broadcast:cancel")
            ]
        ]
    )
    return keyboard

def get_broadcast_target_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Всем пользователям", callback_data="broadcast_all")
    )
    builder.row(
        InlineKeyboardButton(text="English users", callback_data="broadcast_en"),
        InlineKeyboardButton(text="Русскоязычным", callback_data="broadcast_ru")
    )
    builder.row(
        InlineKeyboardButton(text="Отмена", callback_data="broadcast_cancel")
    )
    return builder.as_markup()

def get_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="broadcast_confirm"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")
    )
    return builder.as_markup()

def get_event_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора типа мероприятия"""
    keyboard = [
        [
            InlineKeyboardButton(text="🎯 Quiz", callback_data="event_type:quiz"),
            InlineKeyboardButton(text="🎵 Music Quiz", callback_data="event_type:music_quiz")
        ],
        [
            InlineKeyboardButton(text="🎤 Karaoke", callback_data="event_type:karaoke"),
            InlineKeyboardButton(text="🎉 Party", callback_data="event_type:party")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_difficulty_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора уровня сложности"""
    keyboard = [
        [
            InlineKeyboardButton(text="😊 Easy", callback_data="difficulty:easy"),
            InlineKeyboardButton(text="🤔 Medium", callback_data="difficulty:medium"),
            InlineKeyboardButton(text="🧠 Hard", callback_data="difficulty:hard")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def format_event_info(event: Event, lang: str = "en") -> str:
    """Форматирование информации о мероприятии"""
    date_str = event.event_date.strftime("%d.%m.%Y %H:%M")
    participants_count = len(event.participants)
    max_participants_str = f"/{event.max_participants}" if event.max_participants else ""
    
    if lang == "en":
        event_type_map = {
            "quiz": "Quiz",
            "music_quiz": "Music Quiz",
            "karaoke": "Karaoke",
            "party": "Party"
        }
        
        info = [
            f"📅 {event.title}",
            f"🎯 Type: {event_type_map.get(event.event_type, 'Event')}",
            f"📝 Description: {event.description}",
            f"📍 Location: {event.location}",
            f"🕒 Date and time: {date_str}",
            f"👥 Participants: {participants_count}{max_participants_str}"
        ]
        
        if event.theme:
            info.append(f"🎨 Theme: {event.theme}")
        if event.difficulty_level:
            info.append(f"📊 Difficulty: {event.difficulty_level.capitalize()}")
        if event.music_genre:
            info.append(f"🎵 Genre: {event.music_genre}")
        if event.max_teams:
            info.append(f"👥 Teams: {event.max_teams} (max {event.team_size} per team)")
            
        info.append(f"👤 Created by: {event.creator.real_name or event.creator.first_name}")
        
        return "\n\n".join(info)
    else:
        event_type_map = {
            "quiz": "Квиз",
            "music_quiz": "Музыкальный квиз",
            "karaoke": "Караоке",
            "party": "Вечеринка"
        }
        
        info = [
            f"📅 {event.title}",
            f"🎯 Тип: {event_type_map.get(event.event_type, 'Мероприятие')}",
            f"📝 Описание: {event.description}",
            f"📍 Место: {event.location}",
            f"🕒 Дата и время: {date_str}",
            f"👥 Участники: {participants_count}{max_participants_str}"
        ]
        
        if event.theme:
            info.append(f"🎨 Тема: {event.theme}")
        if event.difficulty_level:
            difficulty_map = {"easy": "Лёгкий", "medium": "Средний", "hard": "Сложный"}
            info.append(f"📊 Сложность: {difficulty_map.get(event.difficulty_level, event.difficulty_level)}")
        if event.music_genre:
            info.append(f"🎵 Жанр: {event.music_genre}")
        if event.max_teams:
            info.append(f"👥 Команды: {event.max_teams} (максимум {event.team_size} в команде)")
            
        info.append(f"👤 Создал: {event.creator.real_name or event.creator.first_name}")
        
        return "\n\n".join(info) 