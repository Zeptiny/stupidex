from textual.app import App
from textual.widgets import RichLog, Static

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
        
    if app.model:
        app.query_one("#model", Static).update(f"{app.model}")
    else:
        app.query_one("#model", Static).update("No Model")

def full_rerender(app: App) -> None:
    sessions = app.sessions
    if not sessions.active:
        return

    # Title
    app.query_one("#title", Static).update(sessions.active.name)

    # Messages
    output = app.query_one("#output", RichLog)
    output.clear()
    for msg in sessions.active.messages:
        output.write(msg.render())

    rerender_footer(app)