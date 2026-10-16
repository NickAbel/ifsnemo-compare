"""PATH handling for the tools installed by tools/install_*.sh."""
import os


def tool_dirs(root):
    return [f"{root}/tools", f"{root}/tools/psubmit"]


def append_tools_to_path(root):
    """Append root's tool dirs to this process's PATH, so a tool already in PATH is found first."""
    os.environ["PATH"] = os.pathsep.join([os.environ["PATH"], *tool_dirs(root)])
