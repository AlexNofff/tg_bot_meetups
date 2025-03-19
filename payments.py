import os
from typing import Optional, Tuple

import stripe
from dotenv import load_dotenv

load_dotenv()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLIC_KEY = os.getenv("STRIPE_PUBLIC_KEY")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

async def create_payment_intent(
    amount: int,
    currency: str = "usd",
    metadata: Optional[dict] = None
) -> Tuple[str, str]:
    """
    Создает платежное намерение в Stripe
    :param amount: сумма в центах
    :param currency: валюта
    :param metadata: дополнительные данные
    :return: (payment_intent_id, client_secret)
    """
    try:
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency=currency,
            metadata=metadata or {},
            automatic_payment_methods={"enabled": True}
        )
        return intent.id, intent.client_secret
    except stripe.error.StripeError as e:
        raise ValueError(f"Error creating payment intent: {str(e)}")

def verify_webhook_signature(payload: bytes, sig_header: str) -> bool:
    """
    Проверяет подпись вебхука от Stripe
    """
    try:
        stripe.Webhook.construct_event(
            payload, sig_header, WEBHOOK_SECRET
        )
        return True
    except Exception:
        return False

def get_payment_status(payment_intent_id: str) -> str:
    """
    Получает статус платежа
    """
    try:
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        return intent.status
    except stripe.error.StripeError as e:
        raise ValueError(f"Error retrieving payment status: {str(e)}")

def format_price(amount: int, currency: str = "usd") -> str:
    """
    Форматирует цену для отображения
    :param amount: сумма в центах
    :param currency: валюта
    :return: отформатированная строка с ценой
    """
    if currency.lower() == "usd":
        return f"${amount/100:.2f}"
    elif currency.lower() == "eur":
        return f"€{amount/100:.2f}"
    elif currency.lower() == "rub":
        return f"{amount/100:.0f}₽"
    return f"{amount/100:.2f} {currency.upper()}" 