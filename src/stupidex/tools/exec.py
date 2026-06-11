import asyncio
import os
import shlex
import signal
from stupidex.config import get_config
from stupidex.domain.tool import ExecutorResult, Tool, ToolParameter, ToolParameterProperties


execute_command_tool = Tool(
    name="execute_command",
    description="Execute a system command using subprocess and return the output",
    parameters=ToolParameter(
        properties={
            "command": ToolParameterProperties(
                type="string",
                description="The command to execute (e.g., 'ls -la', 'python script.py', 'git status')"
            ),
            "description": ToolParameterProperties(
                type="string",
                description="A brief description of what the command does(for display purposes)"
            ),
            "working_directory": ToolParameterProperties(
                type="string",
                description="The working directory to run the command in (default: current directory)"
            ),
            "timeout": ToolParameterProperties(
                type="integer",
                description="Timeout in seconds for the command execution (default: 30)"
            ),
            "shell": ToolParameterProperties(
                type="boolean",
                description="Whether to run the command through the shell (default: true)"
            ),
        },
        required=["command", "description"]
    ),
)


async def execute_command(
    command: str,
    description: str | None = None,
    working_directory: str = ".",
    timeout: int | None = None,
    shell: bool = True,
) -> ExecutorResult:
    """Execute a system command using asyncio subprocess."""
    if timeout is None:
        timeout = get_config().command_timeout
    try:
        if shell:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_directory,
                start_new_session=True,
            )
        else:
            args = shlex.split(command)
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_directory,
                start_new_session=True,
            )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (OSError, AttributeError):
                process.kill()
            await process.wait()
            return ExecutorResult(
                display=f"{description} - Timed out after {timeout} seconds",
                content=f"Error: Command '{command}' timed out after {timeout} seconds.",
            )

        stdout = stdout_bytes.decode(
            "utf-8", errors="replace").strip() if stdout_bytes else ""
        stderr = stderr_bytes.decode(
            "utf-8", errors="replace").strip() if stderr_bytes else ""

        if process.returncode == 0:
            output = stdout if stdout else "(no output)"
            if stderr:
                output += f"\n\nStderr:\n{stderr}"
            return ExecutorResult(
                display=f"{description} (exit code: {process.returncode})",
                content=output,
            )
        else:
            output = ""
            if stdout:
                output += f"Stdout:\n{stdout}\n\n"
            if stderr:
                output += f"Stderr:\n{stderr}"
            if not output:
                output = "(no output)"
            return ExecutorResult(
                display=f"{description} (exit code: {process.returncode})",
                content=output,
            )

    except Exception as e:
        return ExecutorResult(
            display=f"{description} - Execution error",
            content=f"Error executing command '{command}': {e}",
        )
