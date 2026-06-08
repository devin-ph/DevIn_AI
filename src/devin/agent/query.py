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
    def __init__(self, primary_llm: Any, fallback_models: list[str] = None, max_tokens: int = TOKEN_BUDGET):
        self.primary_llm = primary_llm
        self.fallback_models = fallback_models or []
        self._current_llm = primary_llm
        self._consecutive_failures = 0
        self.max_tokens = max_tokens
        self.fail_count = 0

    def _estimate_tokens(self, messages: list) -> int:
        total_chars = sum(len(str(m.content)) for m in messages if hasattr(m, 'content'))
        return total_chars // 4

    def get_context_ratio(self, messages: list) -> float:
        estimated = self._estimate_tokens(messages)
        return min(1.0, estimated / self.max_tokens)

    def is_near_limit(self, messages: list) -> bool:
        return self.get_context_ratio(messages) >= 0.70

    async def query(self, messages: list, tools: list = None) -> AIMessage:
        ratio = self.get_context_ratio(messages)
        est = self._estimate_tokens(messages)
        
        percent = int(ratio * 100)
        log_str = f"Context: {percent}% ({est:,} / {self.max_tokens:,} tokens)"
        
        if ratio >= 0.95:
            logger.error(f"{log_str} - STOPPING")
            return AIMessage(content="FAIL: Context budget exceeded (>=95%). Stopping to prevent overflow.")
        elif ratio >= 0.85:
            logger.warning(f"{log_str} - COMPRESSING")
            from devin.cli.renderer import console
            console.print(f"\n  [yellow]⚠️ Context budget at {percent}% — compression needed![/]")
        elif ratio >= 0.70:
            logger.info(f"{log_str} - WARNING")
        else:
            logger.debug(log_str)

        llms_to_try = [self._current_llm]
        
        for model_name in self.fallback_models:
            from devin.agent.llm_provider import create_llm
            fallback = create_llm(model=model_name)
            llms_to_try.append(fallback)
        
        last_error = None
        for attempt, llm in enumerate(llms_to_try):
            llm_to_use = llm
            if tools:
                llm_to_use = llm.bind_tools(tools)
                
            for retry in range(4):
                try:
                    if hasattr(llm_to_use, "ainvoke"):
                        response = await llm_to_use.ainvoke(messages)
                    else:
                        response = await asyncio.to_thread(llm_to_use.invoke, messages)
                    
                    self._consecutive_failures = 0
                    if attempt > 0:
                        logger.info(f"Switched to fallback model after primary failed")
                        self._current_llm = llm  # Remember working model
                        
                    if hasattr(response, "response_metadata"):
                        meta = response.response_metadata
                        usage = meta.get("token_usage", {})
                        if usage:
                            logger.debug(f"Actual token usage: {usage}")
                            
                    return response
                    
                except Exception as e:
                    error_str = str(e)
                    if "429" in error_str or "rate_limit" in error_str.lower() or "quota" in error_str.lower():
                        if retry < 3:
                            wait_time = 5 * (retry + 1)
                            logger.warning(f"Rate limit hit. Retrying in {wait_time}s... (Attempt {retry+1}/4)")
                            from devin.cli.renderer import console
                            console.print(f"  [dim]⏳ Rate limit hit. Sleeping for {wait_time}s...[/]")
                            import asyncio
                            await asyncio.sleep(wait_time)
                        else:
                            last_error = e
                            break 
                    else:
                        last_error = e
                        if retry < 3:
                            wait_time = 2 ** retry
                            logger.warning(f"LLM error. Retrying in {wait_time}s.")
                            import asyncio
                            await asyncio.sleep(wait_time)
                        else:
                            break
        
        self._consecutive_failures += 1
        if self._consecutive_failures >= 3:
            return AIMessage(content=f"FAIL: API Error. All models exhausted. Last error: {last_error}")
        
        return AIMessage(content=f"FAIL: API Error. Last error: {last_error}")

