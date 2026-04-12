import datetime
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage

from devin.agent.query import QueryEngine

@pytest.fixture
def mock_llm():
    mock = MagicMock()
    mock.ainvoke = AsyncMock()
    return mock

@pytest.mark.asyncio
async def test_query_success(mock_llm):
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="Success"))
    engine = QueryEngine(mock_llm)
    
    response = await engine.query([HumanMessage(content="Hello")])
    assert response.content == "Success"
    mock_llm.ainvoke.assert_awaited_once()

@pytest.mark.asyncio
async def test_query_rate_limit_retry(mock_llm):
    class RateLimitError(Exception):
        pass

    # Fail twice, succeed on third try
    mock_llm.ainvoke.side_effect = [
        RateLimitError("429 Too Many Requests"),
        RateLimitError("rate limit exceeded"),
        AIMessage(content="Third time is the charm")
    ]
    
    engine = QueryEngine(mock_llm)
    # mock asyncio.sleep so we don't actually wait
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        response = await engine.query([HumanMessage(content="Hello")])
    
    assert response.content == "Third time is the charm"
    assert mock_llm.ainvoke.call_count == 3
    assert engine.fail_count == 0  # resets on success

@pytest.mark.asyncio
async def test_query_max_failures(mock_llm):
    class RateLimitError(Exception):
        pass

    mock_llm.ainvoke.side_effect = RateLimitError("429 Too Many Requests")
    
    engine = QueryEngine(mock_llm)
    
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        response = await engine.query([HumanMessage(content="Hello")])
        
    assert mock_llm.ainvoke.call_count == 3
    assert engine.fail_count == 3
    assert "FAIL" in response.content
