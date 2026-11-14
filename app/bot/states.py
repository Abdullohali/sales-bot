from aiogram.fsm.state import State, StatesGroup


class SaleFlow(StatesGroup):
    choose_client = State()
    choose_product = State()
    enter_qty = State()
    enter_price = State()
    draft = State()
    saving = State()  # guards against double "✅ Завершить"
