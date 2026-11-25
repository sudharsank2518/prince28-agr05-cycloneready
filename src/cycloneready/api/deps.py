"""Dependencies: endpoints ask for these instead of building them."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from cycloneready.config import Settings
from cycloneready.llm.gateway import LLMGateway


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_db_session(request: Request):
    async with request.app.state.sessionmaker() as session:
        yield session


def get_llm_gateway(request: Request) -> LLMGateway:
    """Return the application LLM gateway."""

    return request.app.state.llm_gateway


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
LLMGatewayDep = Annotated[LLMGateway, Depends(get_llm_gateway)]
