from aiogram import Router
from bot.handlers.common import router as common_router
from bot.handlers.actions import router as actions_router
from bot.handlers.edit import router as edit_router
from bot.handlers.notes import router as notes_router

main_router = Router(name="main_router")

# Include routers in priority order: commands & specific callbacks first, catch-all text last
main_router.include_router(common_router)
main_router.include_router(actions_router)
main_router.include_router(edit_router)
main_router.include_router(notes_router)

__all__ = ["main_router"]
