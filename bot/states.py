from aiogram.fsm.state import State, StatesGroup


class UserFlow(StatesGroup):
    waiting_for_photo = State()
    waiting_for_style = State()
    waiting_for_broadcast = State()


# Backward compatibility alias for legacy imports.
GenerationFlow = UserFlow
