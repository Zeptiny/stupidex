from stupidex.domain.message import Message, MessageRole, MessageType
import platform

# TODO: Improve this bullshit prompt
# Tools definition will be included here when they are added


def build_static_system_prompt() -> Message:
    content = f"""
    <instructions>
    You are running inside Stupidex, a terminal-based coding assistant.
    You are a coding agent designed to help users with coding tasks. 
    You can understand and write code in various programming languages, debug code, and provide explanations for coding concepts. 
    Always provide clear and concise answers, and if you don't know something, it's okay to say so.
    </instructions>
    
    <user_operating_system>{_get_os_info()}</user_operating_system>
    """

    return Message(
        role=MessageRole.SYSTEM,
        content=content,
        type=MessageType.TEXT,
    )


def _get_os_info() -> str:
    system = platform.system()
    machine = platform.machine()

    if system == "Windows":
        win_ver = platform.win32_ver()
        return f"Windows {win_ver[0]} (build {win_ver[1]}, {machine})"

    if system == "Darwin":
        mac_ver = platform.mac_ver()
        return f"macOS {mac_ver[0]} ({machine})"

    if system == "Linux":
        try:
            info = platform.freedesktop_os_release()
            distro = f"{info.get('NAME', 'Unknown')} {info.get('VERSION_ID', '')}".strip(
            )
        except (OSError, AttributeError):
            distro = "Unknown"
        kernel = platform.release()
        return f"Linux {distro} (kernel {kernel}, {machine})"

    return f"{system} {platform.release()} ({machine})"
