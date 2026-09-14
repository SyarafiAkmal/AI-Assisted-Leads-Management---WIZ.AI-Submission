import os
from typing import Optional, Type, TypeVar

from langchain.chat_models import init_chat_model
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


DEFAULT_LLM_MODEL = os.getenv(
    "DEFAULT_LLM_MODEL",
    "mock",
)

DEDUPE_LLM_MODEL = os.getenv(
    "DEDUPE_LLM_MODEL",
    DEFAULT_LLM_MODEL,
)

EXTRACTION_LLM_MODEL = os.getenv(
    "EXTRACTION_LLM_MODEL",
    DEFAULT_LLM_MODEL,
)


def get_llm(
    model: Optional[str] = None,
    temperature: float = 0.0,
):
    """
    Return a LangChain chat model based on the configured model.

    Examples:
        get_llm()
        get_llm(model="openai:gpt-5.4-mini")

    If model == "mock", use FakeListChatModel so development/testing
    can run without an API call.
    """
    model = model or DEFAULT_LLM_MODEL

    if model == "mock":
        return FakeListChatModel(
            responses=["(mock LLM response)"]
        )

    return init_chat_model(
        model,
        temperature=temperature,
    )


def get_dedupe_llm(
    temperature: float = 0.0,
):
    """
    Return the LLM configured specifically for dedupe.
    """
    return get_llm(
        model=DEDUPE_LLM_MODEL,
        temperature=temperature,
    )


def get_extraction_llm(
    temperature: float = 0.0,
):
    """
    Return the LLM configured specifically for extraction.
    """
    return get_llm(
        model=EXTRACTION_LLM_MODEL,
        temperature=temperature,
    )


def get_structured_llm(
    schema: Type[T],
    model: Optional[str] = None,
):
    """
    Return an LLM with structured output enabled.

    Used by extraction where the result must conform to
    a Pydantic schema.

    Mock does not support structured output natively, so the
    caller should handle mock mode separately.
    """
    llm = get_llm(model=model)

    if isinstance(llm, FakeListChatModel):
        return llm

    return llm.with_structured_output(schema)


def is_mock_provider(
    model: Optional[str] = None,
) -> bool:
    """
    Check whether the specified model is mock.

    If no model is supplied, checks DEFAULT_LLM_MODEL.
    """
    model = model or DEFAULT_LLM_MODEL
    return model == "mock"


def is_dedupe_mock() -> bool:
    """
    Check whether the configured dedupe model is mock.
    """
    return DEDUPE_LLM_MODEL == "mock"


def is_extraction_mock() -> bool:
    """
    Check whether the configured extraction model is mock.
    """
    return EXTRACTION_LLM_MODEL == "mock"