from aiogram.fsm.state import State, StatesGroup

class RegistrationStates(StatesGroup):
    waiting_for_language = State()
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_country = State()
    waiting_for_about = State()

class BroadcastStates(StatesGroup):
    waiting_for_message = State()
    waiting_for_confirmation = State()

class EventStates(StatesGroup):
    waiting_for_type = State()
    waiting_for_theme = State()
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_location = State()
    waiting_for_date = State()
    waiting_for_max_participants = State()
    waiting_for_music_genre = State()
    waiting_for_max_teams = State()
    waiting_for_team_size = State()
    waiting_for_difficulty = State() 