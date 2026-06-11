import subprocess
from stupidex.domain.tool import ExecutorResult, Tool, ToolParameter, ToolParameterProperties

execute_command_tool = Tool(
    name="execute_command",
    description="Execute a system command using subprocess.run and return the output",
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


def execute_command(
    command: str,
    description: str | None = None,
    working_directory: str = ".",
    timeout: int = 30,
    shell: bool = True,
) -> ExecutorResult:
    """Execute a system command using subprocess.run."""
    try:
        result = subprocess.run(
            command,
            shell=shell,
            cwd=working_directory,
            timeout=timeout,
            capture_output=True,
            text=True,
        )

        stdout = result.stdout.strip() if result.stdout else ""
        stderr = result.stderr.strip() if result.stderr else ""

        if result.returncode == 0:
            output = stdout if stdout else "(no output)"
            if stderr:
                output += f"\n\nStderr:\n{stderr}"
            return ExecutorResult(
                display=f"{description} (exit code: {result.returncode})",
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
                display=f"{description} (exit code: {result.returncode})",
                content=output,
            )

    except subprocess.TimeoutExpired:
        return ExecutorResult(
            display=f"{description} - Timed out after {timeout} seconds",
            content=f"Error: Command '{command}' timed out after {timeout} seconds.",
        )
    except Exception as e:
        return ExecutorResult(
            display=f"{description} - Execution error",
            content=f"Error executing command '{command}': {e}",
        )
