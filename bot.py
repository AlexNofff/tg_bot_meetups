import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Union
import json

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    Message,
    ReplyKeyboardRemove,
    Contact,
    PreCheckoutQuery,
    LabeledPrice,
    BotCommand,
)
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import (
    Message as DBMessage,
    BroadcastMessage,
    User,
    Event,
    DatabaseMiddleware,
    get_users_by_language,
    init_db,
    mark_message_sent_to_user,
    save_broadcast_message,
    create_event,
    get_user_events,
    get_available_events,
    join_event,
    leave_event,
    cancel_event,
    create_payment,
    update_payment_status,
    get_upcoming_events,
    get_past_events,
    import_meetupshare_event,
    get_or_create_user
)
from keyboards import (
    get_admin_chat_keyboard,
    get_admin_main_keyboard,
    get_broadcast_confirmation_keyboard,
    get_broadcast_target_keyboard,
    get_language_keyboard,
    get_phone_number_keyboard,
    get_main_keyboard,
    get_events_keyboard,
    get_event_actions_keyboard,
    get_event_type_keyboard,
    get_difficulty_keyboard,
    format_event_info
)
from payments import create_payment_intent, format_price
from scheduler import setup_scheduler
from states import BroadcastStates, RegistrationStates, EventStates
from texts import get_text, TEXTS

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

# Конфигурация
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

logger.info(f"Token: {TOKEN}")
logger.info(f"Admin ID: {ADMIN_ID}")

# Роутеры
admin_router = Router(name="admin")
user_router = Router(name="user")

# Словарь для хранения последней активности пользователей
last_activity: Dict[int, datetime] = {}

# Словарь для хранения данных рассылки
broadcast_data: Dict[int, Dict[str, Any]] = {}

# Функции для работы с базой данных
async def get_or_create_user(session: AsyncSession, telegram_user: Any) -> User:
    try:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_user.id)
        )
        user = result.scalar_one_or_none()
        
        if user is None:
            user = User(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                registration_complete=False
            )
            session.add(user)
            await session.commit()
        
        return user
    except Exception as e:
        await session.rollback()
        logger.error(f"Error in get_or_create_user: {e}", exc_info=True)
        raise

async def save_message(session: AsyncSession, user: User, text: str, is_from_user: bool):
    try:
        message = DBMessage(
            user_id=user.id,
            text=text,
            is_from_user=is_from_user
        )
        session.add(message)
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"Error in save_message: {e}", exc_info=True)
        raise

def format_event_info(event: Event, lang: str = "en") -> str:
    date_str = event.event_date.strftime("%d.%m.%Y %H:%M")
    participants_count = len(event.participants)
    max_participants_str = f"/{event.max_participants}" if event.max_participants else ""
    
    if lang == "en":
        return (
            f"📅 {event.title}\n\n"
            f"📝 Description: {event.description}\n"
            f"📍 Location: {event.location}\n"
            f"🕒 Date and time: {date_str}\n"
            f"👥 Participants: {participants_count}{max_participants_str}\n"
            f"👤 Created by: {event.creator.real_name or event.creator.first_name}"
        )
    else:
        return (
            f"📅 {event.title}\n\n"
            f"📝 Описание: {event.description}\n"
            f"📍 Место: {event.location}\n"
            f"🕒 Дата и время: {date_str}\n"
            f"👥 Участники: {participants_count}{max_participants_str}\n"
            f"👤 Создал: {event.creator.real_name or event.creator.first_name}"
        )

# Хендлеры для регистрации
@user_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, **kwargs):
    try:
        session = kwargs['session']
        try:
            user = await get_or_create_user(session, message.from_user)
            logger.info(f"New user started bot: {message.from_user.id} ({message.from_user.username})")
            
            if not user.registration_complete:
                # Сбрасываем состояние и начинаем регистрацию
                await state.clear()
                await message.answer(
                    TEXTS["en"]["welcome"],
                    reply_markup=get_language_keyboard()
                )
                await state.set_state(RegistrationStates.waiting_for_language)
            else:
                # Для зарегистрированных пользователей показываем приветствие и инструкции
                lang = user.language
                main_keyboard = get_main_keyboard(lang)
                await message.answer(
                    TEXTS[lang]["welcome"],
                    reply_markup=main_keyboard
                )
                await message.answer(
                    TEXTS[lang]["help"],
                    reply_markup=main_keyboard
                )
        except Exception as e:
            await session.rollback()
            logger.error(f"Database error in start command: {e}", exc_info=True)
            raise
    except Exception as e:
        logger.error(f"Error in start command: {e}", exc_info=True)
        await message.answer("An error occurred. Please try again later.\n"
                           "Произошла ошибка. Пожалуйста, попробуйте позже.")

@user_router.message(Command("help"))
async def cmd_help(message: Message, **kwargs):
    try:
        session = kwargs['session']
        user = await get_or_create_user(session, message.from_user)
        lang = user.language if user and user.registration_complete else "en"
        
        await message.answer(
            TEXTS[lang]["help"],
            reply_markup=get_main_keyboard(lang) if user and user.registration_complete else None
        )
    except Exception as e:
        logger.error(f"Error in help command: {e}", exc_info=True)
        await message.answer("An error occurred. Please try again later.\n"
                           "Произошла ошибка. Пожалуйста, попробуйте позже.")

@user_router.message(lambda message: message.text and message.text.lower() in ['help', 'помощь'])
async def text_help(message: Message, **kwargs):
    await cmd_help(message, **kwargs)

@user_router.callback_query(F.data.startswith("lang_"))
async def process_language_selection(callback: CallbackQuery, state: FSMContext, **kwargs):
    try:
        session = kwargs['session']
        try:
            user = await get_or_create_user(session, callback.from_user)
            language = callback.data.split("_")[1]
            
            await user.update_language(session, language)
            await callback.message.delete()
            
            await callback.message.answer(get_text("name_request", language))
            await state.set_state(RegistrationStates.waiting_for_name)
            await state.update_data(language=language)
        except Exception as e:
            await session.rollback()
            logger.error(f"Database error in language selection: {e}", exc_info=True)
            raise
    except Exception as e:
        logger.error(f"Error processing language selection: {e}", exc_info=True)
        await callback.message.answer(get_text("error_occurred", "en"))

@user_router.message(RegistrationStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext, **kwargs):
    try:
        session = kwargs['session']
        user = await get_or_create_user(session, message.from_user)
        state_data = await state.get_data()
        language = state_data.get("language", "en")
        
        if not message.text or len(message.text) < 2:
            await message.answer(get_text("invalid_name", language))
            return
        
        user.real_name = message.text
        await session.commit()
        
        await message.answer(
            get_text("phone_request", language),
            reply_markup=get_phone_number_keyboard()
        )
        await state.set_state(RegistrationStates.waiting_for_phone)
        
    except Exception as e:
        logger.error(f"Error processing name: {e}", exc_info=True)
        await message.answer(get_text("error_occurred", language))

@user_router.message(RegistrationStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext, **kwargs):
    try:
        session = kwargs['session']
        user = await get_or_create_user(session, message.from_user)
        state_data = await state.get_data()
        language = state_data.get("language", "en")
        
        if not message.contact or not message.contact.phone_number:
            await message.answer(
                get_text("invalid_phone", language),
                reply_markup=get_phone_number_keyboard()
            )
            return
        
        user.phone_number = message.contact.phone_number
        await session.commit()
        
        await message.answer(
            get_text("country_request", language),
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(RegistrationStates.waiting_for_country)
        
    except Exception as e:
        logger.error(f"Error processing phone: {e}", exc_info=True)
        await message.answer(get_text("error_occurred", language))

@user_router.message(RegistrationStates.waiting_for_country)
async def process_country(message: Message, state: FSMContext, **kwargs):
    try:
        session = kwargs['session']
        user = await get_or_create_user(session, message.from_user)
        state_data = await state.get_data()
        language = state_data.get("language", "en")
        
        if message.text == "/skip":
            user.country = None
            await session.commit()
            await message.answer(get_text("skip_received", language))
            await message.answer(get_text("about_request", language))
            await state.set_state(RegistrationStates.waiting_for_about)
            return
        
        user.country = message.text
        await session.commit()
        await message.answer(get_text("about_request", language))
        await state.set_state(RegistrationStates.waiting_for_about)
        
    except Exception as e:
        logger.error(f"Error processing country: {e}", exc_info=True)
        await message.answer(get_text("error_occurred", language))

@user_router.message(RegistrationStates.waiting_for_about)
async def process_about(message: Message, state: FSMContext, **kwargs):
    try:
        session = kwargs['session']
        user = await get_or_create_user(session, message.from_user)
        state_data = await state.get_data()
        language = state_data.get("language", "en")
        
        if message.text == "/skip":
            user.about = None
            user.registration_complete = True
            await session.commit()
            await message.answer(get_text("skip_received", language))
            await message.answer(get_text("registration_complete", language))
            await state.clear()
            
            # Уведомляем админа о новом пользователе
            if message.from_user.id != ADMIN_ID:
                admin_message = (
                    f"New user registered:\n"
                    f"Name: {user.real_name}\n"
                    f"Phone: {user.phone_number}\n"
                    f"Country: {user.country or 'Not specified'}\n"
                    f"About: {user.about or 'Not specified'}\n"
                    f"Language: {user.language}\n"
                    f"Username: @{message.from_user.username or 'None'}\n"
                    f"Telegram ID: {message.from_user.id}"
                )
                await message.bot.send_message(
                    ADMIN_ID,
                    admin_message,
                    reply_markup=get_admin_chat_keyboard(message.from_user.id, message.from_user.username or "")
                )
            return
        
        user.about = message.text
        user.registration_complete = True
        await session.commit()
        await message.answer(get_text("registration_complete", language))
        await state.clear()
        
        # Уведомляем админа о новом пользователе
        if message.from_user.id != ADMIN_ID:
            admin_message = (
                f"New user registered:\n"
                f"Name: {user.real_name}\n"
                f"Phone: {user.phone_number}\n"
                f"Country: {user.country or 'Not specified'}\n"
                f"About: {user.about or 'Not specified'}\n"
                f"Language: {user.language}\n"
                f"Username: @{message.from_user.username or 'None'}\n"
                f"Telegram ID: {message.from_user.id}"
            )
            await message.bot.send_message(
                ADMIN_ID,
                admin_message,
                reply_markup=get_admin_chat_keyboard(message.from_user.id, message.from_user.username or "")
            )
        
    except Exception as e:
        logger.error(f"Error processing about: {e}", exc_info=True)
        await message.answer(get_text("error_occurred", language))

@user_router.message(Command("skip"))
async def process_skip(message: Message, state: FSMContext, **kwargs):
    try:
        session = kwargs['session']
        user = await get_or_create_user(session, message.from_user)
        state_data = await state.get_data()
        language = state_data.get("language", "en")
        
        current_state = await state.get_state()
        
        if current_state == RegistrationStates.waiting_for_country:
            user.country = None
            await session.commit()
            await message.answer(get_text("skip_received", language))
            await message.answer(get_text("about_request", language))
            await state.set_state(RegistrationStates.waiting_for_about)
            
        elif current_state == RegistrationStates.waiting_for_about:
            user.about = None
            user.registration_complete = True
            await session.commit()
            await message.answer(get_text("skip_received", language))
            await message.answer(get_text("registration_complete", language))
            await state.clear()
            
            # Уведомляем админа о новом пользователе
            if message.from_user.id != ADMIN_ID:
                admin_message = (
                    f"New user registered:\n"
                    f"Name: {user.real_name}\n"
                    f"Phone: {user.phone_number}\n"
                    f"Country: {user.country or 'Not specified'}\n"
                    f"About: {user.about or 'Not specified'}\n"
                    f"Language: {user.language}\n"
                    f"Username: @{message.from_user.username or 'None'}\n"
                    f"Telegram ID: {message.from_user.id}"
                )
                await message.bot.send_message(
                    ADMIN_ID,
                    admin_message,
                    reply_markup=get_admin_chat_keyboard(message.from_user.id, message.from_user.username or "")
                )
        
    except Exception as e:
        logger.error(f"Error processing skip command: {e}", exc_info=True)
        await message.answer(get_text("error_occurred", language))

# Обработка текстовых сообщений
@user_router.message(F.text)
async def handle_user_message(message: Message, state: FSMContext, **kwargs):
    try:
        session = kwargs['session']
        user = await get_or_create_user(session, message.from_user)
        
        # Логируем получение сообщения
        logger.info(f"Received message from user {message.from_user.id} ({message.from_user.username}): {message.text[:20]}...")
        
        # Проверяем текст сообщения на ключевые слова о мероприятиях
        if any(keyword in message.text.lower() for keyword in ["мероприятия", "события", "events"]):
            response = (
                "🎉 Добро пожаловать в систему управления мероприятиями!\n\n"
                "У нас вы можете:\n"
                "1. 📅 Создавать новые мероприятия\n"
                "2. 👥 Присоединяться к существующим\n"
                "3. 🎯 Управлять своими мероприятиями\n\n"
                "Доступные типы мероприятий:\n"
                "• 🎯 Квизы и викторины\n"
                "• 🎵 Музыкальные квизы\n"
                "• 🎤 Караоке-вечера\n"
                "• 🎉 Тематические вечеринки\n\n"
                "Для начала работы нажмите на кнопку '📅 События' в меню"
            )
            await message.answer(response, reply_markup=get_main_keyboard(user.language))
            return

        # Проверяем, завершена ли регистрация
        if not user.registration_complete and message.from_user.id != ADMIN_ID:
            await message.answer(get_text("registration_required", user.language))
            return
        
        if message.from_user.id == ADMIN_ID:
            current_state = await state.get_state()
            if current_state == BroadcastStates.waiting_for_message:
                broadcast_data[ADMIN_ID] = {"message": message.text}
                await message.answer(
                    "Выберите целевую аудиторию для рассылки:",
                    reply_markup=get_broadcast_target_keyboard()
                )
                await state.set_state(BroadcastStates.waiting_for_confirmation)
                return
            
            # Обычное сообщение от админа
            if message.reply_to_message:
                logger.info(f"Admin is replying to message: {message.reply_to_message.message_id}")
                if message.reply_to_message.forward_from:
                    target_user_id = message.reply_to_message.forward_from.id
                    logger.info(f"Got target user ID from forward_from: {target_user_id}")
                else:
                    try:
                        original_message = message.reply_to_message.text or message.reply_to_message.caption or ""
                        if "Telegram ID:" in original_message:
                            user_info = original_message.split("Telegram ID: ")[1].split("\n")[0]
                            target_user_id = int(user_info)
                            logger.info(f"Got target user ID from message text: {target_user_id}")
                        else:
                            logger.warning("Could not find user ID in message")
                            await message.answer("❌ Не удалось определить получателя сообщения")
                            return
                    except Exception as e:
                        logger.error(f"Error extracting user ID: {e}")
                        await message.answer("❌ Не удалось определить получателя сообщения")
                        return

                try:
                    await save_message(session, user, message.text, False)
                    await message.bot.send_message(target_user_id, message.text)
                    await message.answer("✅ Сообщение отправлено")
                    logger.info(f"Admin message sent to user {target_user_id}")
                except Exception as e:
                    logger.error(f"Error sending admin reply: {e}", exc_info=True)
                    await message.answer("❌ Ошибка при отправке сообщения")
            else:
                logger.warning("Admin message is not a reply")
                await message.answer("❌ Чтобы ответить пользователю, используйте ответ на его сообщение")
        else:
            # Сообщение от пользователя
            logger.info(f"Processing message from user {message.from_user.id}")
            try:
                # Сохраняем сообщение в базу
                await save_message(session, user, message.text, True)
                logger.info("Message saved to database")

                # Отправляем копию сообщения админу
                admin_message = (
                    f"Message from {user.real_name}\n"
                    f"Phone: {user.phone_number}\n"
                    f"Country: {user.country or 'Not specified'}\n"
                    f"Language: {user.language}\n"
                    f"Username: @{message.from_user.username or 'None'}\n"
                    f"Telegram ID: {message.from_user.id}\n\n"
                    f"{message.text}"
                )
                sent_message = await message.bot.send_message(
                    ADMIN_ID,
                    admin_message,
                    reply_markup=get_admin_chat_keyboard(message.from_user.id, message.from_user.username or "")
                )
                logger.info(f"Message forwarded to admin, message_id: {sent_message.message_id}")
                
                if message.from_user.id not in last_activity:
                    await message.answer(get_text("message_received", user.language))
                
                last_activity[message.from_user.id] = datetime.utcnow()
                logger.info(f"Message from user {message.from_user.id} processed successfully")
            except Exception as e:
                logger.error(f"Error handling user message: {e}", exc_info=True)
                await message.answer(get_text("error_occurred", user.language))
    except Exception as e:
        logger.error(f"General error in message handler: {e}", exc_info=True)
        await message.answer(get_text("error_occurred", user.language))

# Хендлеры для админа
@admin_router.message(Command("admin"))
async def admin_panel(message: Message, **kwargs):
    if message.from_user.id != ADMIN_ID:
        return
    
    logger.info(f"Admin panel accessed by {message.from_user.id}")
    await message.answer(
        "Панель администратора",
        reply_markup=get_admin_main_keyboard()
    )

@admin_router.callback_query(F.data == "create_broadcast")
async def create_broadcast(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    
    await callback.message.edit_text("Введите сообщение для рассылки:")
    await state.set_state(BroadcastStates.waiting_for_message)
    await callback.answer()

@admin_router.callback_query(F.data.startswith("broadcast_"))
async def process_broadcast(callback: CallbackQuery, state: FSMContext, **kwargs):
    if callback.from_user.id != ADMIN_ID:
        return
    
    action = callback.data.split("_")[1]
    
    if action == "cancel":
        await state.clear()
        await callback.message.edit_text("Рассылка отменена")
        return
    
    session = kwargs['session']
    broadcast_message = broadcast_data.get(ADMIN_ID, {}).get("message")
    
    if not broadcast_message:
        await callback.message.edit_text("Ошибка: сообщение для рассылки не найдено")
        await state.clear()
        return
    
    target_language = None if action == "all" else action
    users = await get_users_by_language(session, target_language)
    
    if not users:
        await callback.message.edit_text("Нет пользователей для рассылки")
        await state.clear()
        return
    
    broadcast = await save_broadcast_message(session, broadcast_message, target_language)
    
    success_count = 0
    for user in users:
        try:
            await callback.bot.send_message(user.telegram_id, broadcast_message)
            await mark_message_sent_to_user(session, broadcast.id, user.telegram_id)
            success_count += 1
        except Exception as e:
            logger.error(f"Error sending broadcast to user {user.telegram_id}: {e}")
    
    await callback.message.edit_text(
        f"Рассылка завершена\n"
        f"Успешно отправлено: {success_count} из {len(users)}"
    )
    await state.clear()
    broadcast_data.pop(ADMIN_ID, None)

@admin_router.callback_query(F.data == "list_chats")
async def list_chats(callback: CallbackQuery, **kwargs):
    if callback.from_user.id != ADMIN_ID:
        return
    
    session = kwargs['session']
    # Получаем пользователей с сообщениями за последние 24 часа
    yesterday = datetime.utcnow() - timedelta(days=1)
    result = await session.execute(
        select(User)
        .join(DBMessage)
        .where(DBMessage.created_at >= yesterday)
        .distinct()
    )
    users = result.scalars().all()
    
    if not users:
        await callback.message.edit_text("Нет активных чатов")
        return
    
    text = "Активные чаты:\n\n"
    for user in users:
        username = f"@{user.username}" if user.username else "Без username"
        text += f"{user.real_name} ({username})\n"
        text += f"Телефон: {user.phone_number}\n"
        text += f"Страна: {user.country or 'Не указана'}\n"
        text += f"Язык: {user.language}\n\n"
        keyboard = get_admin_chat_keyboard(user.telegram_id, user.username or "")
        await callback.message.answer(text, reply_markup=keyboard)
    
    await callback.answer()

@admin_router.callback_query(F.data.startswith("history_"))
async def show_chat_history(callback: CallbackQuery, **kwargs):
    if callback.from_user.id != ADMIN_ID:
        return
    
    session = kwargs['session']
    user_id = int(callback.data.split("_")[1])
    result = await session.execute(
        select(DBMessage)
        .join(User)
        .where(User.telegram_id == user_id)
        .order_by(DBMessage.created_at)
    )
    messages = result.scalars().all()
    
    if not messages:
        await callback.message.edit_text("История сообщений пуста")
        return
    
    text = "История сообщений:\n\n"
    for msg in messages:
        sender = "Пользователь" if msg.is_from_user else "Админ"
        date = msg.created_at.strftime("%d.%m.%Y %H:%M")
        text += f"{date} - {sender}:\n{msg.text}\n\n"
    
    # Разбиваем на части, если текст слишком длинный
    max_length = 4096
    for i in range(0, len(text), max_length):
        chunk = text[i:i + max_length]
        await callback.message.answer(chunk)
    
    await callback.answer()

@user_router.message(F.text.in_(["📅 Events", "📅 События"]))
async def show_events_menu(message: Message, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user)
    if not user.registration_complete:
        await message.answer(TEXTS[user.language]["user_not_registered"])
        return
    
    await message.answer(
        TEXTS[user.language]["events_menu"],
        reply_markup=get_events_keyboard(user.language)
    )

@user_router.message(F.text.in_(["🎯 My Events", "🎯 Мои события"]))
async def show_my_events(message: Message, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user)
    if not user.registration_complete:
        await message.answer(TEXTS[user.language]["user_not_registered"])
        return
    
    events = await get_user_events(session, user)
    if not events:
        await message.answer(TEXTS[user.language]["no_my_events"])
        return
    
    for event in events:
        is_creator = event.creator_id == user.id
        is_participant = user in event.participants
        await message.answer(
            format_event_info(event, user.language),
            reply_markup=get_event_actions_keyboard(event.id, is_participant, is_creator, user.language)
        )

@user_router.callback_query(F.data == "create_event")
async def create_event_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EventStates.waiting_for_type)
    user = callback.from_user
    session = callback.message.bot.get("session")
    db_user = await get_or_create_user(session, user)
    
    await callback.message.answer(
        TEXTS[db_user.language]["event_create_type"],
        reply_markup=get_event_type_keyboard()
    )
    await callback.answer()

@user_router.callback_query(F.data.startswith("event_type:"))
async def process_event_type(callback: CallbackQuery, state: FSMContext):
    event_type = callback.data.split(":")[1]
    await state.update_data(event_type=event_type)
    session = callback.message.bot.get("session")
    user = await get_or_create_user(session, callback.from_user)
    
    await callback.message.answer(TEXTS[user.language]["event_create_theme"])
    await state.set_state(EventStates.waiting_for_theme)
    await callback.answer()

@user_router.message(EventStates.waiting_for_theme)
async def process_event_theme(message: Message, state: FSMContext):
    await state.update_data(theme=message.text)
    session = message.bot.get("session")
    user = await get_or_create_user(session, message.from_user)
    
    state_data = await state.get_data()
    event_type = state_data.get("event_type")
    
    if event_type in ["quiz", "music_quiz"]:
        await message.answer(
            TEXTS[user.language]["event_create_difficulty"],
            reply_markup=get_difficulty_keyboard()
        )
        await state.set_state(EventStates.waiting_for_difficulty)
    elif event_type in ["karaoke", "music_quiz"]:
        await message.answer(TEXTS[user.language]["event_create_music_genre"])
        await state.set_state(EventStates.waiting_for_music_genre)
    else:
        await message.answer(TEXTS[user.language]["event_create_title"])
        await state.set_state(EventStates.waiting_for_title)

@user_router.callback_query(F.data.startswith("difficulty:"))
async def process_difficulty(callback: CallbackQuery, state: FSMContext):
    difficulty = callback.data.split(":")[1]
    await state.update_data(difficulty_level=difficulty)
    session = callback.message.bot.get("session")
    user = await get_or_create_user(session, callback.from_user)
    
    state_data = await state.get_data()
    if state_data.get("event_type") == "music_quiz":
        await callback.message.answer(TEXTS[user.language]["event_create_music_genre"])
        await state.set_state(EventStates.waiting_for_music_genre)
    else:
        await callback.message.answer(TEXTS[user.language]["event_create_max_teams"])
        await state.set_state(EventStates.waiting_for_max_teams)
    await callback.answer()

@user_router.message(EventStates.waiting_for_music_genre)
async def process_music_genre(message: Message, state: FSMContext):
    await state.update_data(music_genre=message.text)
    session = message.bot.get("session")
    user = await get_or_create_user(session, message.from_user)
    
    await message.answer(TEXTS[user.language]["event_create_max_teams"])
    await state.set_state(EventStates.waiting_for_max_teams)

@user_router.message(EventStates.waiting_for_max_teams)
async def process_max_teams(message: Message, state: FSMContext):
    session = message.bot.get("session")
    user = await get_or_create_user(session, message.from_user)
    
    if message.text == "/skip":
        await state.update_data(max_teams=None)
        await message.answer(TEXTS[user.language]["event_create_title"])
        await state.set_state(EventStates.waiting_for_title)
        return
    
    try:
        max_teams = int(message.text)
        await state.update_data(max_teams=max_teams)
        await message.answer(TEXTS[user.language]["event_create_team_size"])
        await state.set_state(EventStates.waiting_for_team_size)
    except ValueError:
        await message.answer(TEXTS[user.language]["invalid_number"])

@user_router.message(EventStates.waiting_for_team_size)
async def process_team_size(message: Message, state: FSMContext):
    session = message.bot.get("session")
    user = await get_or_create_user(session, message.from_user)
    
    if message.text == "/skip":
        await state.update_data(team_size=None)
        await message.answer(TEXTS[user.language]["event_create_title"])
        await state.set_state(EventStates.waiting_for_title)
        return
    
    try:
        team_size = int(message.text)
        await state.update_data(team_size=team_size)
        await message.answer(TEXTS[user.language]["event_create_title"])
        await state.set_state(EventStates.waiting_for_title)
    except ValueError:
        await message.answer(TEXTS[user.language]["invalid_number"])

@user_router.callback_query(F.data == "available_events")
async def show_available_events(callback: CallbackQuery, session: AsyncSession):
    user = await get_or_create_user(session, callback.from_user)
    events = await get_upcoming_events(session)
    
    if not events:
        await callback.message.answer(TEXTS[user.language]["no_events_available"])
        await callback.answer()
        return
    
    for event in events:
        is_participant = user in event.participants
        message_text = format_event_info(event, user.language)
        
        # Добавляем информацию о цене, если она есть
        if event.price:
            price_text = format_price(event.price, "usd")
            if user.language == "ru":
                message_text += f"\n💰 Цена: {price_text}"
            else:
                message_text += f"\n💰 Price: {price_text}"
        
        await callback.message.answer(
            message_text,
            reply_markup=get_event_actions_keyboard(event.id, is_participant, False, user.language)
        )
    
    await callback.answer()

@user_router.callback_query(F.data.startswith("join_event:"))
async def join_event_callback(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    event_id = int(callback.data.split(":")[1])
    user = await get_or_create_user(session, callback.from_user)
    event = await session.get(Event, event_id)
    
    if not event:
        await callback.answer(TEXTS[user.language]["event_not_found"])
        return
    
    # Если событие платное и пользователь еще не участник
    if event.price and user not in event.participants:
        # Создаем платежное намерение
        try:
            payment_intent_id, client_secret = await create_payment_intent(
                amount=event.price,
                currency="usd",
                metadata={"event_id": event_id, "user_id": user.telegram_id}
            )
            
            # Сохраняем платеж в базе
            await create_payment(
                session=session,
                user=user,
                event=event,
                stripe_payment_id=payment_intent_id,
                amount=event.price
            )
            
            # Отправляем сообщение с ссылкой на оплату
            payment_url = f"https://checkout.stripe.com/pay/{client_secret}"
            if user.language == "ru":
                message = (
                    f"Для участия в событии '{event.title}' необходимо оплатить "
                    f"{format_price(event.price, 'usd')}.\n\n"
                    f"Оплатить: {payment_url}"
                )
            else:
                message = (
                    f"To join the event '{event.title}', please pay "
                    f"{format_price(event.price, 'usd')}.\n\n"
                    f"Pay here: {payment_url}"
                )
            
            await callback.message.answer(message)
            await callback.answer()
            return
            
        except ValueError as e:
            logger.error(f"Error creating payment: {e}")
            await callback.answer(TEXTS[user.language]["payment_error"])
            return
    
    # Если событие бесплатное или пользователь уже участник
    success = await join_event(session, event, user)
    if success:
        await callback.message.edit_text(
            format_event_info(event, user.language),
            reply_markup=get_event_actions_keyboard(event.id, True, False, user.language)
        )
        await callback.answer(TEXTS[user.language]["event_joined"])
    else:
        await callback.answer(TEXTS[user.language]["event_full"])

@user_router.callback_query(F.data.startswith("leave_event:"))
async def leave_event_callback(callback: CallbackQuery, session: AsyncSession):
    event_id = int(callback.data.split(":")[1])
    user = await get_or_create_user(session, callback.from_user)
    event = await session.get(Event, event_id)
    
    if not event:
        await callback.answer(TEXTS[user.language]["event_not_found"])
        return
    
    await leave_event(session, event, user)
    await callback.message.edit_text(
        format_event_info(event, user.language),
        reply_markup=get_event_actions_keyboard(event.id, False, False, user.language)
    )
    await callback.answer(TEXTS[user.language]["event_left"])

@user_router.callback_query(F.data.startswith("cancel_event:"))
async def cancel_event_callback(callback: CallbackQuery, session: AsyncSession):
    event_id = int(callback.data.split(":")[1])
    user = await get_or_create_user(session, callback.from_user)
    event = await session.get(Event, event_id)
    
    if not event or event.creator_id != user.id:
        await callback.answer(TEXTS[user.language]["event_not_found"])
        return
    
    await cancel_event(session, event)
    await callback.message.edit_text(
        format_event_info(event, user.language) + "\n\n❌ " + TEXTS[user.language]["event_cancelled"]
    )
    await callback.answer()

@user_router.callback_query(F.data == "events_menu")
async def return_to_events_menu(callback: CallbackQuery, session: AsyncSession):
    user = await get_or_create_user(session, callback.from_user)
    await callback.message.edit_text(
        TEXTS[user.language]["events_menu"],
        reply_markup=get_events_keyboard(user.language)
    )
    await callback.answer()

# Обработчик успешной оплаты
@user_router.message(F.text == "/stripe/webhook")
async def stripe_webhook(message: Message, session: AsyncSession):
    """
    Обработчик вебхука от Stripe
    """
    try:
        # Получаем данные из сообщения
        if not message.web_app_data:
            return
        
        payload = message.web_app_data.data
        sig_header = message.web_app_data.button_text  # Используем button_text для передачи заголовка
        
        if not verify_webhook_signature(payload.encode(), sig_header):
            return
        
        event_json = json.loads(payload)
        event_type = event_json["type"]
        
        if event_type == "payment_intent.succeeded":
            payment_intent = event_json["data"]["object"]
            payment_intent_id = payment_intent["id"]
            
            # Обновляем статус платежа
            payment = await update_payment_status(session, payment_intent_id, "succeeded")
            if payment:
                # Добавляем пользователя к участникам события
                await join_event(session, payment.event, payment.user)
                
                # Отправляем уведомление пользователю
                success_message = TEXTS[payment.user.language]["payment_success"]
                try:
                    await message.bot.send_message(payment.user.telegram_id, success_message)
                except Exception as e:
                    logger.error(f"Error sending payment success message: {e}")
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return

async def setup_bot_commands(bot: Bot):
    commands_ru = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="help", description="Показать справку"),
        BotCommand(command="events", description="Управление событиями"),
        BotCommand(command="create", description="Создать новое событие"),
        BotCommand(command="list", description="Показать список событий"),
        BotCommand(command="my", description="Мои события"),
        BotCommand(command="settings", description="Настройки"),
    ]
    
    commands_en = [
        BotCommand(command="start", description="Start the bot"),
        BotCommand(command="help", description="Show help"),
        BotCommand(command="events", description="Event management"),
        BotCommand(command="create", description="Create new event"),
        BotCommand(command="list", description="Show events list"),
        BotCommand(command="my", description="My events"),
        BotCommand(command="settings", description="Settings"),
    ]
    
    await bot.set_my_commands(commands_ru, language_code="ru")
    await bot.set_my_commands(commands_en, language_code="en")
    logger.info("Bot commands have been set up")

@user_router.message(Command("settings"))
async def cmd_settings(message: Message, **kwargs):
    try:
        session = kwargs['session']
        user = await get_or_create_user(session, message.from_user)
        lang = user.language if user and user.registration_complete else "en"
        
        if not user or not user.registration_complete:
            await message.answer(
                "⚠️ Please complete registration first" if lang == "en" else 
                "⚠️ Пожалуйста, сначала завершите регистрацию"
            )
            return
        
        settings_text = (
            "⚙️ Settings:\n\n"
            "🌐 Language: {}\n"
            "📱 Phone: {}\n"
            "🌍 Country: {}\n"
            "ℹ️ About: {}"
        ) if lang == "en" else (
            "⚙️ Настройки:\n\n"
            "🌐 Язык: {}\n"
            "📱 Телефон: {}\n"
            "🌍 Страна: {}\n"
            "ℹ️ О себе: {}"
        )
        
        await message.answer(
            settings_text.format(
                "English" if user.language == "en" else "Русский",
                user.phone_number or "Not set" if lang == "en" else "Не указан",
                user.country or "Not set" if lang == "en" else "Не указана",
                user.about or "Not set" if lang == "en" else "Не указано"
            )
        )
    except Exception as e:
        logger.error(f"Error in settings command: {e}", exc_info=True)
        await message.answer("An error occurred. Please try again later.\n"
                           "Произошла ошибка. Пожалуйста, попробуйте позже.")

@user_router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, **kwargs):
    try:
        session = kwargs['session']
        user = await get_or_create_user(session, message.from_user)
        lang = user.language if user and user.registration_complete else "en"
        
        current_state = await state.get_state()
        if current_state is None:
            await message.answer(
                "🤔 There's nothing to cancel" if lang == "en" else
                "🤔 Нечего отменять"
            )
            return
            
        await state.clear()
        await message.answer(
            "❌ Current action cancelled" if lang == "en" else
            "❌ Текущее действие отменено",
            reply_markup=get_main_keyboard(lang) if user and user.registration_complete else None
        )
    except Exception as e:
        logger.error(f"Error in cancel command: {e}", exc_info=True)
        await message.answer("An error occurred. Please try again later.\n"
                           "Произошла ошибка. Пожалуйста, попробуйте позже.")

# Добавляем алиасы для существующих команд
@user_router.message(Command("events"))
async def cmd_events(message: Message, session: AsyncSession):
    await show_events_menu(message, session)

@user_router.message(Command("my_events"))
async def cmd_my_events(message: Message, session: AsyncSession):
    await show_my_events(message, session)

@user_router.message(Command("create_event"))
async def cmd_create_event(message: Message, state: FSMContext):
    callback = CallbackQuery(
        id="1",
        from_user=message.from_user,
        chat_instance="1",
        message=message,
        data="create_event"
    )
    await create_event_start(callback, state)

@user_router.message(Command("available_events"))
async def cmd_available_events(message: Message, session: AsyncSession):
    callback = CallbackQuery(
        id="1",
        from_user=message.from_user,
        chat_instance="1",
        message=message,
        data="available_events"
    )
    await show_available_events(callback, session)

@user_router.callback_query(F.data == "past_events")
async def show_past_events(callback: CallbackQuery, session: AsyncSession):
    user = await get_or_create_user(session, callback.from_user)
    past_events = await get_past_events(session)
    
    if not past_events:
        text = "Нет прошедших событий" if user.language == "ru" else "No past events"
        await callback.answer(text, show_alert=True)
        return
    
    text = "📜 Прошедшие события:\n\n" if user.language == "ru" else "📜 Past Events:\n\n"
    for event in past_events:
        text += format_event_info(event, user.language) + "\n\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=get_events_keyboard(user.language)
    )

@admin_router.message(Command("import_meetupshare"))
async def import_meetupshare(message: Message, session: AsyncSession):
    try:
        # Получаем пользователя из базы данных
        user = await get_or_create_user(session, message.from_user)
        
        # Создаем тестовое событие Meetupshare
        event = await import_meetupshare_event(
            session=session,
            creator=user,
            title="Не только про любовь",
            description="""Всем Туц 👋
Наконец может поспорить : кто круче – Комбинация или Ласковый май? Taylor Swift или Eminem? One Direction или Spice Girls?
Пора девочкам сразиться с мальчиками, чтобы определить, чьи песни мы любим больше! Выбирай, за кого болеешь, а подпевать можно всем!

Но победит, конечно, дружба!""",
            location="Lelé Cake Cafe (14178 Blossom Hill Rd, Los Gatos, CA 95032)",
            event_date=datetime(2025, 2, 26, 19, 0),  # 26 февраля 2025, 7 PM
            event_type="karaoke",
            theme="music_battle",
            max_participants=35,
            price=4900  # $49.00 в центах
        )
        await message.answer(
            f"✅ Событие успешно импортировано:\n\n{format_event_info(event)}"
        )
    except Exception as e:
        logging.error(f"Error importing Meetupshare event: {e}")
        await message.answer("❌ Ошибка при импорте события")

async def main():
    try:
        # Загружаем переменные окружения
        load_dotenv()
        TOKEN = os.getenv("BOT_TOKEN")
        ADMIN_ID = os.getenv("ADMIN_ID")
        
        logging.info(f"Token: {TOKEN}")
        logging.info(f"Admin ID: {ADMIN_ID}")
        logging.info("Starting bot initialization...")
        
        # Инициализируем бота с поддержкой HTML
        bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        
        # Создаем диспетчер
        dp = Dispatcher(storage=MemoryStorage())
        
        # Регистрируем роутеры
        dp.include_router(admin_router)
        dp.include_router(user_router)
        
        # Инициализируем базу данных
        await init_db()
        
        # Регистрируем middleware
        dp.message.middleware(DatabaseMiddleware())
        dp.callback_query.middleware(DatabaseMiddleware())
        
        # Устанавливаем команды бота
        await setup_bot_commands(bot)
        
        # Настраиваем планировщик
        setup_scheduler(bot)
        
        # Запускаем бота
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"Error in main: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True) 