"""
Centralized LLM orchestration and querying.
Handles backoff, retries, rate limits, and context budget monitoring.
"""

import asyncio
import logging
from typing import Any
from langchain_core.messages import AIMessage

logger = logging.getLogger("devin.query")

from devin.constants import TOKEN_BUDGET

class QueryEngine:
    def __init__(self, llm: Any, max_tokens: int = TOKEN_BUDGET):
        self.llm = llm
        self.max_tokens = max_tokens
        self.fail_count = 0

    def _estimate_tokens(self, messages: list) -> int:
        # A simple approximation: ~4 chars per token
        total_chars = sum(len(str(m.content)) for m in messages if hasattr(m, 'content'))
        return total_chars // 4

    def get_context_ratio(self, messages: list) -> float:
        estimated = self._estimate_tokens(messages)
        return min(1.0, estimated / self.max_tokens)

    def is_near_limit(self, messages: list) -> bool:
        return self.get_context_ratio(messages) >= 0.70

    async def query(self, messages: list, tools: list = None) -> AIMessage:
        # Bind tools if provided
        llm_to_use = self.llm
        if tools:
            llm_to_use = self.llm.bind_tools(tools)

        ratio = self.get_context_ratio(messages)
        est = self._estimate_tokens(messages)
        
        percent = int(ratio * 100)
        log_str = f"Context: {percent}% ({est:,} / {self.max_tokens:,} tokens)"
        
        if ratio >= 0.95:
            logger.error(f"{log_str} - STOPPING")
            return AIMessage(content="FAIL: Context budget exceeded (>=95%). Stopping to prevent overflow.")
        elif ratio >= 0.85:
            logger.warning(f"{log_str} - COMPRESSING")
            print(f"\n  [devin.system]⚠️ Context budget at {percent}% — compression needed![/]")
        elif ratio >= 0.70:
            logger.info(f"{log_str} - WARNING")
            print(f"\n  [devin.system]⚠️ Context budget reaching {percent}%.[/]")
        else:
            logger.debug(log_str)
            print(f"\n  [dim]📊 {log_str}[/]")

        # Exponential backoff retry loop (4 attempts)
        max_attempts = 4
        base_delay = 2.0
        
        for attempt in range(max_attempts):
            try:
                if asyncio.iscoroutinefunction(llm_to_use.invoke):
                    response = await llm_to_use.invoke(messages)
                else:
                    # Run sync invoke in thread pool if needed, but langchain ChatOpenAI/Anthropic supports ainvoke
                    if hasattr(llm_to_use, "ainvoke"):
                        response = await llm_to_use.ainvoke(messages)
                    else:
                        response = await asyncio.to_thread(llm_to_use.invoke, messages)

                self.fail_count = 0  # reset on success
                
                # Try to log actual usage if returned
                if hasattr(response, "response_metadata"):
                    meta = response.response_metadata
                    usage = meta.get("token_usage", {})
                    # Add to response for extraction by caller
                    if usage:
                        logger.debug(f"Actual token usage: {usage}")

                return response

            except Exception as e:
                self.fail_count += 1
                error_str = str(e).lower()
                
                # Rate limit detection
                is_rate_limit = "rate" in error_str or "429" in error_str or "quota" in error_str
                
                delay = base_delay * (2 ** attempt)
                if is_rate_limit:
                    delay = max(delay, 5.0)  # at least 5s for rate limits
                    logger.warning(f"Rate limit detected. Retrying in {delay}s... (Attempt {attempt+1}/{max_attempts})")
                    print(f"\n  [devin.system]⏳ Rate limit hit. Sleeping for {delay}s...[/]")
                else:
                    logger.warning(f"LLM Error: {e}. Retrying in {delay}s... (Attempt {attempt+1}/{max_attempts})")
                
                if attempt == max_attempts - 1 or self.fail_count >= 3:
                    # 3 consecutive failures immediately escalates
                    print(f"\n  [devin.error]❌ 3 consecutive API failures. Escalating to user. Error: {e}[/]")
                    return AIMessage(content=f"FAIL: API Error: {e}")

                await asyncio.sleep(delay)
        
        # Fallback if loop exits
        return AIMessage(content="FAIL: Max retries exceeded.")
