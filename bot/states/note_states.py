from aiogram.fsm.state import State, StatesGroup


class EditNoteState(StatesGroup):
    waiting_for_new_text = State()
