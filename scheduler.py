from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot

from database import async_session, get_events_for_notification, mark_notification_sent

scheduler = AsyncIOScheduler()

async def send_event_notifications(bot: Bot):
    """
    Отправляет уведомления о предстоящих событиях
    """
    async with async_session() as session:
        events = await get_events_for_notification(session)
        for event in events:
            # Отправляем уведомление создателю события
            creator_message = (
                f"🔔 Напоминание!\n\n"
                f"Ваше событие '{event.title}' начнется через 24 часа.\n"
                f"Место: {event.location}\n"
                f"Участники: {len(event.participants)}"
            )
            try:
                await bot.send_message(event.creator.telegram_id, creator_message)
            except Exception as e:
                print(f"Error sending notification to creator: {e}")

            # Отправляем уведомления участникам
            participant_message = (
                f"🔔 Напоминание!\n\n"
                f"Событие '{event.title}' начнется через 24 часа.\n"
                f"Место: {event.location}"
            )
            for participant in event.participants:
                try:
                    await bot.send_message(participant.telegram_id, participant_message)
                except Exception as e:
                    print(f"Error sending notification to participant: {e}")

            # Отмечаем, что уведомления отправлены
            await mark_notification_sent(session, event)

async def send_events_digest(bot: Bot):
    """
    Отправляет еженедельный дайджест событий
    """
    async with async_session() as session:
        # Получаем всех пользователей с их языковыми настройками
        result = await session.execute("SELECT DISTINCT telegram_id, language FROM users WHERE registration_complete = true")
        users = result.fetchall()

        # Получаем предстоящие события
        now = datetime.utcnow()
        next_week = now + timedelta(days=7)
        result = await session.execute(
            "SELECT * FROM events WHERE event_date BETWEEN :start AND :end AND is_active = true ORDER BY event_date",
            {"start": now, "end": next_week}
        )
        events = result.fetchall()

        if not events:
            return

        for user_id, language in users:
            # Формируем сообщение на нужном языке
            if language == "ru":
                message = "📅 Предстоящие события на следующую неделю:\n\n"
            else:
                message = "📅 Upcoming events for the next week:\n\n"

            for event in events:
                event_date = event.event_date.strftime("%d.%m.%Y %H:%M")
                if language == "ru":
                    message += (
                        f"🎯 {event.title}\n"
                        f"📍 Место: {event.location}\n"
                        f"🕒 Дата: {event_date}\n"
                        f"👥 Участники: {len(event.participants)}"
                    )
                else:
                    message += (
                        f"🎯 {event.title}\n"
                        f"📍 Location: {event.location}\n"
                        f"🕒 Date: {event_date}\n"
                        f"👥 Participants: {len(event.participants)}"
                    )
                
                if event.price:
                    if language == "ru":
                        message += f"\n💰 Цена: {event.price/100:.2f} руб."
                    else:
                        message += f"\n💰 Price: ${event.price/100:.2f}"
                
                message += "\n\n"

            try:
                await bot.send_message(user_id, message)
            except Exception as e:
                print(f"Error sending digest to user {user_id}: {e}")

def setup_scheduler(bot: Bot):
    """
    Настраивает планировщик задач
    """
    # Проверяем события каждый час
    scheduler.add_job(
        send_event_notifications,
        trigger=CronTrigger(hour='*'),
        args=[bot],
        id='event_notifications',
        replace_existing=True
    )

    # Отправляем дайджест каждый понедельник в 10:00
    scheduler.add_job(
        send_events_digest,
        trigger=CronTrigger(day_of_week='mon', hour=10),
        args=[bot],
        id='events_digest',
        replace_existing=True
    )

    scheduler.start() 