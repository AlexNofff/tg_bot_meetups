from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, Optional, List

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Boolean, Text, Enum, Table, Column, and_, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
import enum
import logging

DATABASE_URL = "sqlite+aiosqlite:///feedback_bot.db"

class Base(DeclarativeBase):
    pass

# Таблица для связи many-to-many между пользователями и событиями
event_participants = Table(
    'event_participants',
    Base.metadata,
    Column('user_id', ForeignKey('users.id'), primary_key=True),
    Column('event_id', ForeignKey('events.id'), primary_key=True)
)

class Language(enum.Enum):
    EN = "en"
    RU = "ru"

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    real_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    language: Mapped[str] = mapped_column(String(2), default="en", index=True)
    about: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    registration_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    messages = relationship("Message", back_populates="user")
    created_events = relationship("Event", back_populates="creator")
    participated_events = relationship("Event", secondary=event_participants, back_populates="participants")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    async def update_language(self, session: AsyncSession, language: str):
        try:
            self.language = language
            await session.commit()
        except Exception as e:
            await session.rollback()
            logging.error(f"Error updating language: {e}", exc_info=True)
            raise

class Event(Base):
    __tablename__ = "events"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(200))
    event_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    max_participants: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    price: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)  # Цена в центах
    
    # Новые поля для Meetupshare
    event_type: Mapped[str] = mapped_column(String(50), index=True)  # quiz, karaoke, party
    difficulty_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # easy, medium, hard
    music_genre: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # для музыкальных мероприятий
    max_teams: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    team_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    theme: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # тематика мероприятия
    
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    creator = relationship("User", back_populates="created_events")
    participants = relationship("User", secondary=event_participants, back_populates="participated_events")
    payments = relationship("Payment", back_populates="event")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    notification_sent: Mapped[bool] = mapped_column(Boolean, default=False)

class Message(Base):
    __tablename__ = "messages"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user = relationship("User", back_populates="messages")
    text: Mapped[str] = mapped_column(String(4096))
    is_from_user: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class BroadcastMessage(Base):
    __tablename__ = "broadcast_messages"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    target_language: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sent_to_users: Mapped[str] = mapped_column(Text, default="")  # Хранит список ID пользователей через запятую

class Payment(Base):
    __tablename__ = "payments"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    stripe_payment_id: Mapped[str] = mapped_column(String(100))
    amount: Mapped[int] = mapped_column(BigInteger)  # Сумма в центах
    currency: Mapped[str] = mapped_column(String(3), default="usd")
    status: Mapped[str] = mapped_column(String(20))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    user = relationship("User")
    event = relationship("Event", back_populates="payments")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

class DatabaseMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        async with async_session() as session:
            async with session.begin():
                data["session"] = session
                return await handler(event, data)

# Функции для работы с рассылкой
async def save_broadcast_message(session: AsyncSession, text: str, target_language: Optional[str] = None) -> BroadcastMessage:
    broadcast = BroadcastMessage(
        text=text,
        target_language=target_language
    )
    session.add(broadcast)
    await session.commit()
    return broadcast

async def get_users_by_language(session: AsyncSession, language: Optional[str] = None):
    query = select(User)
    if language:
        query = query.where(User.language == language)
    result = await session.execute(query)
    return result.scalars().all()

async def mark_message_sent_to_user(session: AsyncSession, broadcast_id: int, user_id: int):
    broadcast = await session.get(BroadcastMessage, broadcast_id)
    if broadcast:
        sent_to = set(str(broadcast.sent_to_users).split(',')) if broadcast.sent_to_users else set()
        sent_to.add(str(user_id))
        broadcast.sent_to_users = ','.join(sent_to)
        await session.commit()

# Функции для работы с событиями
async def create_event(
    session: AsyncSession,
    creator: User,
    title: str,
    description: str,
    location: str,
    event_date: datetime,
    max_participants: Optional[int] = None,
    price: Optional[int] = None
) -> Event:
    event = Event(
        title=title,
        description=description,
        location=location,
        event_date=event_date,
        max_participants=max_participants,
        price=price,
        creator=creator
    )
    session.add(event)
    await session.commit()
    return event

async def get_user_events(session: AsyncSession, user: User, include_participated: bool = True) -> List[Event]:
    query = select(Event).where(
        (Event.creator_id == user.id) if not include_participated
        else ((Event.creator_id == user.id) | (Event.id.in_([e.id for e in user.participated_events])))
    ).where(Event.is_active == True)
    result = await session.execute(query)
    return list(result.scalars().all())

async def get_available_events(session: AsyncSession, exclude_user_id: Optional[int] = None) -> List[Event]:
    query = select(Event).where(Event.is_active == True)
    if exclude_user_id:
        query = query.where(Event.creator_id != exclude_user_id)
    result = await session.execute(query)
    return list(result.scalars().all())

async def join_event(session: AsyncSession, event: Event, user: User) -> bool:
    if event.max_participants and len(event.participants) >= event.max_participants:
        return False
    if user not in event.participants:
        event.participants.append(user)
        await session.commit()
    return True

async def leave_event(session: AsyncSession, event: Event, user: User):
    if user in event.participants:
        event.participants.remove(user)
        await session.commit()

async def cancel_event(session: AsyncSession, event: Event):
    event.is_active = False
    await session.commit()

async def get_upcoming_events(session: AsyncSession) -> List[Event]:
    now = datetime.utcnow()
    query = select(Event).where(
        Event.event_date > now,
        Event.is_active == True
    ).order_by(Event.event_date)
    result = await session.execute(query)
    return list(result.scalars().all())

async def get_events_for_notification(session: AsyncSession) -> List[Event]:
    now = datetime.utcnow()
    one_day_from_now = now + timedelta(days=1)
    query = select(Event).where(
        Event.event_date.between(now, one_day_from_now),
        Event.notification_sent == False,
        Event.is_active == True
    )
    result = await session.execute(query)
    return list(result.scalars().all())

async def mark_notification_sent(session: AsyncSession, event: Event):
    event.notification_sent = True
    await session.commit()

async def create_payment(
    session: AsyncSession,
    user: User,
    event: Event,
    stripe_payment_id: str,
    amount: int,
    currency: str = "usd",
    status: str = "pending"
) -> Payment:
    payment = Payment(
        stripe_payment_id=stripe_payment_id,
        amount=amount,
        currency=currency,
        status=status,
        user=user,
        event=event
    )
    session.add(payment)
    await session.commit()
    return payment

async def update_payment_status(
    session: AsyncSession,
    stripe_payment_id: str,
    status: str
) -> Optional[Payment]:
    result = await session.execute(
        select(Payment).where(Payment.stripe_payment_id == stripe_payment_id)
    )
    payment = result.scalar_one_or_none()
    if payment:
        payment.status = status
        await session.commit()
    return payment

async def get_past_events(session: AsyncSession) -> List[Event]:
    # Получаем текущую дату
    current_date = datetime.utcnow()
    
    # Проверяем, есть ли события в базе
    events = await session.execute(
        select(Event)
        .where(
            and_(
                Event.event_date < current_date,
                Event.is_active == True
            )
        )
        .order_by(Event.event_date.desc())
    )
    
    return list(events.scalars().all())

async def import_meetupshare_event(
    session: AsyncSession,
    creator: User,
    title: str,
    description: str,
    location: str,
    event_date: datetime,
    event_type: str,
    theme: Optional[str] = None,
    difficulty_level: Optional[str] = None,
    music_genre: Optional[str] = None,
    max_teams: Optional[int] = None,
    team_size: Optional[int] = None,
    max_participants: Optional[int] = None,
    price: Optional[int] = None
) -> Event:
    event = Event(
        title=title,
        description=description,
        location=location,
        event_date=event_date,
        event_type=event_type,
        theme=theme,
        difficulty_level=difficulty_level,
        music_genre=music_genre,
        max_teams=max_teams,
        team_size=team_size,
        max_participants=max_participants,
        price=price,
        creator=creator
    )
    session.add(event)
    await session.commit()
    return event

async def get_or_create_user(session: AsyncSession, telegram_user: Any) -> User:
    """
    Получает существующего пользователя или создает нового
    """
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
        logging.error(f"Error in get_or_create_user: {e}", exc_info=True)
        raise 