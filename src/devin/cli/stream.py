"""
Stream processing for the LangGraph agent.
Parses astream_events from the agent and prints responses sequentially.
"""
import re
from devin.cli.renderer import (
    console,
    print_tool_call,
    print_tool_result,
    print_error,
    ThoughtBuffer,
)

async def _process_stream(agent, agent_status, full_messages, executed_tasks):
    final_response = ""
    final_response_str = ""
    already_rendered = False
    iteration = 0
    thought_buffer = ThoughtBuffer()
    printed_thoughts = 0
    total_token_usage = {}

    async for event in agent.astream_events(
        {"messages": full_messages, "iteration_count": 0},
        version="v2",
    ):
        event_type = event.get("event")
        
        if event_type == "on_chain_start":
            name = event.get("name", "")
            if name in ["editor_tools", "worker_tools"]:
                agent_status.stop()

        elif event_type == "on_chain_end":
            name = event.get("name", "")
            if name in ["editor_tools", "worker_tools"]:
                agent_status.start()
                agent_status.update("  [cyan]🧠 Thinking...[/]")
            
            if name == "LangGraph":
                final_state = event.get("data", {}).get("output", {})
                if isinstance(final_state, dict):
                    if "messages" in final_state:
                        convo = list(final_state["messages"])
                        if convo:
                            last_msg = convo[-1]
                            if hasattr(last_msg, "content") and last_msg.content:
                                already_rendered = True
                                final_response_str = str(last_msg.content)
                    if "token_usage" in final_state:
                        total_token_usage = final_state["token_usage"]

        elif event_type in ["on_chat_model_stream", "on_llm_stream"]:
            data = event.get("data", {})
            chunk = data.get("chunk")
            chunk_content = ""
            if chunk:
                if hasattr(chunk, "content"):
                    c = chunk.content
                    if isinstance(c, str):
                        chunk_content = c
                    elif isinstance(c, list):
                        for item in c:
                            if isinstance(item, dict) and "text" in item:
                                chunk_content += item["text"]
                            elif isinstance(item, str):
                                chunk_content += item
                elif isinstance(chunk, dict):
                    c = chunk.get("content", "")
                    if isinstance(c, str):
                        chunk_content = c
                    elif isinstance(c, list):
                        for item in c:
                            if isinstance(item, dict) and "text" in item:
                                chunk_content += item["text"]
                elif isinstance(chunk, str):
                    chunk_content = chunk
            
            if chunk_content:
                final_response += chunk_content
                thought_buffer.add_chunk(chunk_content)
                
                complete_thoughts = thought_buffer.get_complete_thoughts()
                if len(complete_thoughts) > printed_thoughts:
                    agent_status.stop()
                    for t in complete_thoughts[printed_thoughts:]:
                        inner = re.sub(r'<thought>|</thought>', '', t).strip()
                        if inner:
                            console.print(f"  [dim italic]💭 {inner[:200]}...[/]" if len(inner) > 200 else f"  [dim italic]💭 {inner}[/]")
                    agent_status.start()
                    printed_thoughts = len(complete_thoughts)

        elif event_type == "on_tool_start":
            data = event.get("data", {})
            name = event.get("name", "")
            input_data = data.get("input", {})
            if name and name not in ["RunnableSequence", "ToolNode", "editor_tools", "architect_tools", "worker_tools"]:
                iteration += 1
                agent_status.stop()
                print_tool_call(name, input_data)
                agent_status.start()
                agent_status.update(f"  [magenta]🔧 Using tool: {name}...[/]")
                task_entry = {"tool": name, "input": input_data, "result": None, "run_id": event.get("run_id")}
                executed_tasks.append(task_entry)

        elif event_type == "on_tool_end":
            name = event.get("name", "")
            if name in ["RunnableSequence", "ToolNode", "editor_tools", "architect_tools", "worker_tools"]:
                continue
            
            data = event.get("data", {})
            run_id = event.get("run_id")
            if "output" in data:
                output = data["output"]
                res = ""
                if isinstance(output, dict) and "messages" in output:
                    messages_out = output["messages"]
                    if messages_out and hasattr(messages_out[-1], 'content'):
                        res = str(messages_out[-1].content)
                elif hasattr(output, 'content'):
                    res = str(output.content)
                else:
                    res = str(output)
                    
                res = res.strip()
                for task in reversed(executed_tasks):
                    if (task.get("run_id") == run_id or task["tool"] == name) and task["result"] is None:
                        task["result"] = res
                        break
                
                agent_status.stop()
                print_tool_result(res)
                agent_status.start()
                    
            agent_status.update("  [cyan]🧠 Thinking...[/]")

    return {
        "final_response": final_response,
        "final_response_str": final_response_str,
        "already_rendered": already_rendered,
        "iteration": iteration,
        "total_token_usage": total_token_usage
    }
