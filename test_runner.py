#!/usr/bin/env python3
"""
Test runner module for ifsnemo-compare pipeline.

Loads test definitions from YAML and executes test suites.
"""
import yaml
from pathlib import Path
from shlex import quote


def load_test_definitions(path: str) -> dict:
    """
    Load test definitions from a YAML file.

    Args:
        path: Path to the test definitions YAML file

    Returns:
        Dictionary containing test suite definitions

    Raises:
        FileNotFoundError: If the definitions file doesn't exist
        yaml.YAMLError: If the file is not valid YAML
    """
    definitions_path = Path(path)
    if not definitions_path.exists():
        raise FileNotFoundError(f"Test definitions file not found: {path}")

    with open(definitions_path, 'r') as f:
        return yaml.safe_load(f) or {}


def validate_test_definitions(defs: dict, cfg: dict, requested_suites: list, suite_type: str = 'test_suites') -> None:
    """
    Validate that the test definitions and pipeline config are compatible.

    Args:
        defs: Loaded test definitions
        cfg: Pipeline configuration
        requested_suites: List of suite names requested to run
        suite_type: Type of suites to validate against ('test_suites' or 'build_suites')

    Raises:
        ValueError: If validation fails
    """
    available_suites = defs.get(suite_type, {})

    # Check that all requested suites exist in definitions
    for suite_name in requested_suites:
        if suite_name not in available_suites:
            available = list(available_suites.keys())
            raise ValueError(
                f"Requested suite '{suite_name}' not found in {suite_type}. "
                f"Available: {available}"
            )


def render_command(suite_def: dict, cmd_name: str, context: dict) -> str:
    """
    Build a command string from a suite definition and context.

    Args:
        suite_def: The test suite definition dict
        cmd_name: Name of the command to render (e.g., 'run-tests', 'compare')
        context: Dictionary of parameter values to substitute

    Returns:
        The rendered command string ready for execution

    Raises:
        KeyError: If the command is not found or a required parameter is missing
    """
    commands = suite_def.get('commands', {})
    if cmd_name not in commands:
        raise KeyError(f"Command '{cmd_name}' not found in suite definition")

    cmd_def = commands[cmd_name]
    script = suite_def.get('script', '')
    working_dir = suite_def.get('working_dir', '').format(**context)
    args_template = cmd_def.get('args', '')

    # Build quoted context for shell safety
    quoted_context = {}
    for key, value in context.items():
        if key == 'gpu_flag':
            # gpu_flag is already formatted with --gpus prefix or empty
            quoted_context[key] = value
        else:
            quoted_context[key] = quote(str(value))

    # Render the args template
    rendered_args = args_template.format(**quoted_context)

    # Build the full command
    cmd = f"cd {quote(working_dir)} && {script} {cmd_name} {rendered_args}"

    return cmd


def get_output_filename(suite_def: dict, cmd_name: str, test_id: str) -> str:
    """
    Get the output filename for a command execution.

    Args:
        suite_def: The test suite definition dict
        cmd_name: Name of the command
        test_id: The test identifier string

    Returns:
        The output filename
    """
    commands = suite_def.get('commands', {})
    cmd_def = commands.get(cmd_name, {})
    output_prefix = cmd_def.get('output_prefix', cmd_name.replace('-', '_'))
    return f"{output_prefix}_{test_id}.log"


def get_result_keys(suite_def: dict, cmd_name: str) -> tuple:
    """
    Get the result dictionary keys for a command.

    Args:
        suite_def: The test suite definition dict
        cmd_name: Name of the command

    Returns:
        Tuple of (passed_key, output_key) for storing results
    """
    commands = suite_def.get('commands', {})
    cmd_def = commands.get(cmd_name, {})
    output_prefix = cmd_def.get('output_prefix', cmd_name.replace('-', '_'))
    return (f"{output_prefix}_passed", f"{output_prefix}_output")


def execute_test(conn, suite_def: dict, cmd_name: str, context: dict,
                 test_id: str, verbose: bool = False) -> dict:
    """
    Execute a single test command and return results.

    Args:
        conn: Fabric connection to the remote machine
        suite_def: The test suite definition dict
        cmd_name: Name of the command to execute
        context: Dictionary of parameter values
        test_id: The test identifier string
        verbose: Whether to print verbose output

    Returns:
        Dictionary with result keys mapping to pass/fail and output file
    """
    cmd = render_command(suite_def, cmd_name, context)
    output_file = get_output_filename(suite_def, cmd_name, test_id)
    passed_key, output_key = get_result_keys(suite_def, cmd_name)

    print(cmd)
    result = conn.run(cmd, warn=True, pty=True)

    with open(output_file, "w") as f:
        f.write(result.stdout)

    if verbose:
        print(f"Output of {cmd_name} saved to local file {output_file}")

    return {
        passed_key: result.return_code == 0,
        output_key: output_file,
    }
