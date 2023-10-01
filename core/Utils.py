# -*- coding: utf-8 -*-
from logging import getLogger
from typing import Coroutine, Any


log = getLogger(__name__)


async def execute_suppress(coro: Coroutine) -> Any:
    try:
        return await coro
    except KeyboardInterrupt:
        raise
    except Exception as error:
        log.exception(error)


def show_odd(odd: float) -> str:
    return f"{round(odd, 2):.2f}"