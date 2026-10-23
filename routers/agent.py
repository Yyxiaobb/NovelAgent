"""Aggregate routes for AI-assisted novel generation."""

from fastapi import APIRouter

from routers.agent_generation import router as agent_generation_router
from routers.chapter_generation import router as chapter_generation_router

router = APIRouter()
router.include_router(agent_generation_router)
router.include_router(chapter_generation_router)
