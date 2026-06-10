from textual.app import App
from textual.widgets import RichLog, Static
from stupidex.llm.models import listModels

def rerender_footer(app: App) -> None:
    sessions = app.sessions
    if not sessions.active:
        return
    
    last_msg = sessions.active.messages[-1] if sessions.active.messages else None
    if last_msg and last_msg.usage:
        u = last_msg.usage
        app.query_one("#status", Static).update(
            f"Context: {u.prompt_tokens} | Response: {u.completion_tokens} | Total: {u.total_tokens}"
        )
    else:
        app.query_one("#status", Static).update("Context: 0 | Response: 0 | Total: 0")
        
    if sessions.active.model:
        app.query_one("#model", Static).update(f"{sessions.active.model}")
    else:
        app.query_one("#model", Static).update("No Model Selected")

def full_rerender(app: App) -> None:
    sessions = app.sessions
    if not sessions.active:
        return

    # Auto-select model if none selected
    if not sessions.active.model:
        models = listModels()
        if models:
            sessions.active.model = models[0].id

    # Title
    app.query_one("#title", Static).update(sessions.active.name)

    # Messages
    output = app.query_one("#output", RichLog)
    output.clear()
    for msg in sessions.active.messages:
        output.write(msg.render())

    rerender_footer(app)