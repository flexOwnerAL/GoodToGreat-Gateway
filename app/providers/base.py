from abc import ABC, abstractmethod
from typing import Any


class BaseProvider(ABC):
    name: str

    @abstractmethod
    async def list_models(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def generate(
        self,
        model: str,
        messages: list[dict[str, str]],
        **options: Any,
    ) -> dict[str, Any]:
        raise NotImplementedError
