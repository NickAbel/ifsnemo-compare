#!/usr/bin/env python3
"""
Bundle YAML vs CMake Configuration Validation Tool

This tool compares version information and CMake flags between the intended input:
- bundle.yml configuration file
- The command line arguments to `ifs-bundle build`, which are then passed into `configure.sh` in build directory
And the build directory output, consisting of:
- CMake config-version files in build directory
- CMakeCache.txt in build directory
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


class BundleConfig:
    """Configuration constants for the bundle comparer."""

    # Directory and file names
    BUNDLE_NAME = "ifs-bundle"
    CONFIG_VERSION_FILENAME_TEMPLATE = "{project}-config-version.cmake"
    CMAKE_CACHE_FILENAME = "CMakeCache.txt"
    CONFIGURE_SCRIPT_FILENAME = "configure.sh"

    # Regex patterns
    PACKAGE_VERSION_PATTERN = r'set\s*\(\s*PACKAGE_VERSION\s+"([^"]+)"\s*\)'
    CMAKE_FLAG_PATTERN = r'^([^:]+):([^=]+)=(.*)$'

    # Reasons a project may not have a config-version file
    SKIP_REASONS = {
        'bundle_false': lambda proj: proj.get('bundle') is False,
        'build_off': lambda proj: _has_build_flag_off(proj),
        'no_version': lambda proj: not proj.get('version') or str(proj.get('version', '')).strip() == ''
    }

    # Placeholder for normalized paths
    PATH_PLACEHOLDER = "{BUILD_ROOT}"


def normalize_paths(data: Any, root_path: str) -> Any:
    """
    Recursively normalize paths in data by replacing root_path with placeholder.

    Args:
        data: JSON-like data structure (dict, list, or primitive)
        root_path: The absolute path to replace with {BUILD_ROOT}

    Returns:
        Data with paths normalized
    """
    if isinstance(data, dict):
        return {k: normalize_paths(v, root_path) for k, v in data.items()}
    elif isinstance(data, list):
        return [normalize_paths(item, root_path) for item in data]
    elif isinstance(data, str):
        if root_path in data:
            return data.replace(root_path, BundleConfig.PATH_PLACEHOLDER)
        return data
    else:
        return data


def _has_build_flag_off(project: Dict) -> bool:
    """Check if project has BUILD_<PROJECT_NAME>=OFF in cmake flags."""
    cmake_str = project.get('cmake', '')
    if not cmake_str:
        return False

    project_name = project.get('name', '')
    if not project_name:
        return False

    # Normalize whitespace for matching
    cmake_str_normalized = ' '.join(cmake_str.split())
    build_flag = f"BUILD_{project_name}=OFF"

    return build_flag in cmake_str_normalized


def load_yaml(yaml_path: Path) -> Dict:
    """Load and parse YAML file."""
    try:
        with open(yaml_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"ERROR: Failed to load YAML file {yaml_path}: {e}", file=sys.stderr)
        sys.exit(1)


def extract_package_version_from_cmake(cmake_file: Path) -> Optional[str]:
    """Extract PACKAGE_VERSION from a CMake config-version file."""
    if not cmake_file.exists():
        return None

    try:
        content = cmake_file.read_text()
        # Remove leading/trailing whitespace from each line before matching
        content_normalized = '\n'.join(line.strip() for line in content.splitlines())

        match = re.search(BundleConfig.PACKAGE_VERSION_PATTERN, content_normalized)
        if match:
            return match.group(1).strip()
    except Exception as e:
        print(f"WARNING: Failed to read {cmake_file}: {e}", file=sys.stderr)

    return None


def parse_cmake_flags(cmake_str: str) -> Dict[str, List[str]]:
    """
    Parse CMake flags from a string.

    Returns a dict mapping FLAG names to list of VALUES.
    Multiple occurrences of the same flag are preserved.
    """
    if not cmake_str:
        return {}

    flags = {}
    # Normalize whitespace and split by whitespace
    parts = cmake_str.split()

    for part in parts:
        part = part.strip()
        if '=' in part:
            flag, value = part.split('=', 1)
            flag = flag.strip()
            value = value.strip()

            if flag not in flags:
                flags[flag] = []
            flags[flag].append(value)

    return flags


def parse_configure_script(configure_path: Path) -> Dict[str, List[str]]:
    """
    Parse configure.sh to extract actual cmake command-line arguments.

    Looks for the cmake command line with -D flags and extracts all FLAG=VALUE pairs.
    Returns a dict mapping FLAG names to list of VALUES.
    """
    if not configure_path.exists():
        return {}

    try:
        content = configure_path.read_text()

        # Find lines that contain 'cmake' followed by arguments
        # Look for pattern: cmake ... -DFLAG=VALUE -DFLAG2=VALUE2 ...
        cmake_flags = {}

        for line in content.splitlines():
            line = line.strip()

            # Look for cmake command lines
            if 'cmake' in line.lower() and '-D' in line:
                # Extract all -DFLAG=VALUE patterns
                # Pattern: -D followed by FLAG=VALUE (may have quotes around value)
                import re
                pattern = r'-D([A-Za-z_][A-Za-z0-9_]*)=("[^"]*"|\'[^\']*\'|[^\s]+)'
                matches = re.findall(pattern, line)

                for flag, value in matches:
                    # Remove quotes from value if present
                    value = value.strip('"').strip("'")

                    if flag not in cmake_flags:
                        cmake_flags[flag] = []
                    cmake_flags[flag].append(value)

        return cmake_flags

    except Exception as e:
        print(f"WARNING: Failed to parse {configure_path}: {e}", file=sys.stderr)
        return {}


def load_cmake_cache(cache_path: Path) -> Dict[str, List[Tuple[str, str]]]:
    """
    Load CMakeCache.txt and extract all flags.

    Returns a dict mapping FLAG names to list of (TYPE, VALUE) tuples.
    """
    if not cache_path.exists():
        print(f"ERROR: CMakeCache.txt not found at {cache_path}", file=sys.stderr)
        sys.exit(1)

    cache_flags = {}

    try:
        with open(cache_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#') or line.startswith('//'):
                    continue

                match = re.match(BundleConfig.CMAKE_FLAG_PATTERN, line)
                if match:
                    flag = match.group(1).strip()
                    flag_type = match.group(2).strip()
                    value = match.group(3).strip()

                    if flag not in cache_flags:
                        cache_flags[flag] = []
                    cache_flags[flag].append((flag_type, value))
    except Exception as e:
        print(f"ERROR: Failed to read CMakeCache.txt: {e}", file=sys.stderr)
        sys.exit(1)

    return cache_flags


def check_bundle_version(bundle_data: Dict, build_dir: Path) -> Dict[str, Any]:
    """
    Routine 1: Check that bundle.yml version matches ifs-bundle-config-version.cmake.

    Returns a dict with check results.
    """
    bundle_name = bundle_data.get('name', '')
    bundle_version = bundle_data.get('version', '')

    if not bundle_version:
        bundle_version = str(bundle_version) if bundle_version is not None else ''
    else:
        bundle_version = str(bundle_version).strip()

    # Construct path to config-version file
    config_file = build_dir / BundleConfig.CONFIG_VERSION_FILENAME_TEMPLATE.format(
        project=bundle_name
    )

    cmake_version = extract_package_version_from_cmake(config_file)

    passed = False
    difference = None

    if cmake_version is None:
        difference = f"CMake config file not found: {config_file}"
    elif bundle_version == cmake_version:
        passed = True
    else:
        difference = f"bundle.yml: '{bundle_version}' != cmake: '{cmake_version}'"

    return {
        'package_name': bundle_name,
        'bundle_version': bundle_version,
        'cmake_version': cmake_version,
        'passed': passed,
        'difference': difference
    }


def check_project_versions(bundle_data: Dict, build_dir: Path) -> Dict[str, Any]:
    """
    Routine 2: Check that all project versions match their config-version files.

    Returns a dict with check results for all projects.
    """
    projects = bundle_data.get('projects', [])

    results = []
    routine_passed = True

    for project_entry in projects:
        if not isinstance(project_entry, dict):
            continue

        # Extract project name (first key in the dict)
        project_name = list(project_entry.keys())[0]
        project_data = project_entry[project_name]

        # Add name to project_data for convenience
        project_data['name'] = project_name

        # Get version from bundle.yml
        bundle_version = project_data.get('version', '')
        if not bundle_version:
            bundle_version = str(bundle_version) if bundle_version is not None else ''
        else:
            bundle_version = str(bundle_version).strip()

        # Check for skip reasons
        skip_reason = None
        for reason_name, reason_check in BundleConfig.SKIP_REASONS.items():
            if reason_check(project_data):
                skip_reason = reason_name
                break

        result = {
            'project_name': project_name,
            'bundle_version': bundle_version,
            'cmake_version': None,
            'passed': False,
            'skip_reason': skip_reason,
            'difference': None
        }

        if skip_reason:
            # Don't fail the routine if we have a valid skip reason
            result['passed'] = True  # Considered passing because it's expected
        else:
            # Look for config-version file
            config_file = build_dir / project_name / BundleConfig.CONFIG_VERSION_FILENAME_TEMPLATE.format(
                project=project_name
            )

            cmake_version = extract_package_version_from_cmake(config_file)
            result['cmake_version'] = cmake_version

            if cmake_version is None:
                result['difference'] = f"CMake config file not found: {config_file}"
                routine_passed = False
            elif bundle_version == cmake_version:
                result['passed'] = True
            else:
                result['difference'] = f"bundle.yml: '{bundle_version}' != cmake: '{cmake_version}'"
                routine_passed = False

        results.append(result)

    return {
        'passed': routine_passed,
        'projects': results
    }


def check_cmake_flags(bundle_data: Dict, build_dir: Path) -> Dict[str, Any]:
    """
    Routine 3: Check that CMake flags from bundle.yml appear in CMakeCache.txt.

    Also incorporates flags from configure.sh (actual command-line arguments).

    Returns a dict with check results for all flags.
    """
    cache_path = build_dir / BundleConfig.CMAKE_CACHE_FILENAME
    cache_flags = load_cmake_cache(cache_path)

    # Collect all CMake flags from bundle.yml
    all_bundle_flags = {}

    # 1. Top-level cmake flags
    top_cmake = bundle_data.get('cmake', '')
    if top_cmake:
        top_flags = parse_cmake_flags(top_cmake)
        for flag, values in top_flags.items():
            if flag not in all_bundle_flags:
                all_bundle_flags[flag] = []
            all_bundle_flags[flag].extend(values)

    # 2. Project-level cmake flags
    projects = bundle_data.get('projects', [])
    for project_entry in projects:
        if not isinstance(project_entry, dict):
            continue

        project_name = list(project_entry.keys())[0]
        project_data = project_entry[project_name]
        project_cmake = project_data.get('cmake', '')

        if project_cmake:
            proj_flags = parse_cmake_flags(project_cmake)
            for flag, values in proj_flags.items():
                if flag not in all_bundle_flags:
                    all_bundle_flags[flag] = []
                all_bundle_flags[flag].extend(values)

    # 3. Command-line flags from configure.sh (these override/supplement bundle.yml)
    configure_path = build_dir / BundleConfig.CONFIGURE_SCRIPT_FILENAME
    configure_flags = parse_configure_script(configure_path)

    # Merge configure.sh flags (these take precedence as they are actual arguments used)
    for flag, values in configure_flags.items():
        if flag not in all_bundle_flags:
            all_bundle_flags[flag] = []
        # Add configure.sh values - these are what was actually used
        all_bundle_flags[flag].extend(values)

    # Now check each flag
    results = []
    routine_passed = True

    for flag, bundle_values in sorted(all_bundle_flags.items()):
        result = {
            'flag': flag,
            'bundle_values': bundle_values,
            'cache_values': [],
            'passed': False,
            'difference': None,
            'note': None,
            'from_configure_script': flag in configure_flags
        }

        if flag not in cache_flags:
            result['difference'] = f"Flag '{flag}' not found in CMakeCache.txt"
            routine_passed = False
        else:
            cache_entries = cache_flags[flag]
            result['cache_values'] = [value for _, value in cache_entries]

            # Check if there are multiple different values in cache
            unique_cache_values = list(set(result['cache_values']))
            if len(unique_cache_values) > 1:
                result['difference'] = f"Multiple different values in CMakeCache.txt: {unique_cache_values}"
                routine_passed = False
            else:
                # Check if at least one cache value matches a bundle value
                cache_value = unique_cache_values[0]

                # Check for exact match first
                if cache_value in bundle_values:
                    result['passed'] = True
                else:
                    # Check if any bundle value contains ${...} variable expansion
                    has_variable = any('${' in bv and '}' in bv for bv in bundle_values)

                    if has_variable:
                        # Variable expansion detected - don't fail, just note it
                        result['passed'] = True
                        result['note'] = f"Bundle value(s) contain variable expansion: {bundle_values}. Cache has expanded value: '{cache_value}'"
                    else:
                        result['difference'] = f"Cache value '{cache_value}' not in bundle values {bundle_values}"
                        routine_passed = False

        results.append(result)

    # Add metadata about configure.sh
    configure_flags_found = len(configure_flags) > 0

    return {
        'passed': routine_passed,
        'configure_script_parsed': configure_flags_found,
        'configure_script_flags_count': len(configure_flags),
        'flags': results
    }


def run_validation(bundle_yaml: Path, build_dir: Path) -> Dict[str, Any]:
    """
    Run all validation routines and return results.

    Args:
        bundle_yaml: Path to bundle.yml file
        build_dir: Path to build directory

    Returns:
        Dictionary with validation results
    """
    # Validate inputs
    if not bundle_yaml.exists():
        print(f"ERROR: Bundle YAML file not found: {bundle_yaml}", file=sys.stderr)
        sys.exit(1)

    if not build_dir.exists():
        print(f"ERROR: Build directory not found: {build_dir}", file=sys.stderr)
        sys.exit(1)

    if not build_dir.is_dir():
        print(f"ERROR: Build path is not a directory: {build_dir}", file=sys.stderr)
        sys.exit(1)

    # Load bundle.yml
    bundle_data = load_yaml(bundle_yaml)

    # Run all three routines
    routine1_result = check_bundle_version(bundle_data, build_dir)
    routine2_result = check_project_versions(bundle_data, build_dir)
    routine3_result = check_cmake_flags(bundle_data, build_dir)

    # Determine overall pass/fail
    all_passed = (
        routine1_result['passed'] and
        routine2_result['passed'] and
        routine3_result['passed']
    )

    return {
        'overall_passed': all_passed,
        'bundle_version': routine1_result,
        'project_versions': routine2_result,
        'cmake_flags': routine3_result
    }


def cmd_validate(args):
    """Run validation (original behavior)."""
    output = run_validation(args.bundle_yaml, args.build_dir)

    # Normalize if requested
    if args.normalize:
        root_path = str(args.build_dir.resolve().parent)
        output = normalize_paths(output, root_path)

    json_output = json.dumps(output)

    if args.output:
        try:
            args.output.write_text(json_output)
            print(f"Results written to: {args.output}")
        except Exception as e:
            print(f"ERROR: Failed to write output file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(json_output)

    sys.exit(0 if output['overall_passed'] else 1)


def cmd_create_refs(args):
    """Run validation and save normalized output as reference."""
    output = run_validation(args.bundle_yaml, args.build_dir)

    # Normalize paths using build_dir's parent as root
    root_path = str(args.build_dir.resolve().parent)
    output = normalize_paths(output, root_path)

    # Save to output directory
    output_path = Path(args.output_dir) / "bundle_validation.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    json_output = json.dumps(output)
    output_path.write_text(json_output)
    print(f"Reference saved to: {output_path}")


def cmd_run_tests(args):
    """Run validation and save normalized output as test result."""
    output = run_validation(args.bundle_yaml, args.build_dir)

    # Normalize paths using build_dir's parent as root
    root_path = str(args.build_dir.resolve().parent)
    output = normalize_paths(output, root_path)

    # Save to output directory
    output_path = Path(args.output_dir) / "bundle_validation.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    json_output = json.dumps(output)
    output_path.write_text(json_output)
    print(f"Test result saved to: {output_path}")


def cmd_compare(args):
    """Compare test result against reference."""
    ref_path = Path(args.ref_dir) / "bundle_validation.json"
    test_path = Path(args.test_dir) / "bundle_validation.json"

    if not ref_path.exists():
        print(f"ERROR: Reference file not found: {ref_path}", file=sys.stderr)
        sys.exit(1)

    if not test_path.exists():
        print(f"ERROR: Test file not found: {test_path}", file=sys.stderr)
        sys.exit(1)

    with open(ref_path) as f:
        ref_data = json.load(f)
    with open(test_path) as f:
        test_data = json.load(f)

    # Compare the two
    if ref_data == test_data:
        print("MATCH: Test output matches reference")
    else:
        print("DIFF: Test output differs from reference")
        import difflib
        ref_str = json.dumps(ref_data, indent=2, sort_keys=True).splitlines(keepends=True)
        test_str = json.dumps(test_data, indent=2, sort_keys=True).splitlines(keepends=True)
        diff = difflib.unified_diff(ref_str, test_str, fromfile='reference', tofile='test')
        print(''.join(diff))
    sys.exit(0)


def main():
    """Main entry point for the bundle validator tool."""
    parser = argparse.ArgumentParser(
        description='Bundle YAML vs CMake configuration validation tool',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    # validate subcommand (original behavior)
    p_validate = subparsers.add_parser('validate', help='Run validation checks')
    p_validate.add_argument('bundle_yaml', type=Path, help='Path to bundle.yml file')
    p_validate.add_argument('build_dir', type=Path, help='Path to build directory')
    p_validate.add_argument('-o', '--output', type=Path, help='Output JSON file (default: stdout)')
    p_validate.add_argument('--normalize', action='store_true', help='Normalize machine-specific paths')
    p_validate.set_defaults(func=cmd_validate)

    # create-refs subcommand
    p_create = subparsers.add_parser('create-refs', help='Run validation and save as reference')
    p_create.add_argument('bundle_yaml', type=Path, help='Path to bundle.yml file')
    p_create.add_argument('build_dir', type=Path, help='Path to build directory')
    p_create.add_argument('-og', '--output-dir', required=True, help='Output directory for reference')
    p_create.set_defaults(func=cmd_create_refs)

    # run-tests subcommand
    p_run = subparsers.add_parser('run-tests', help='Run validation and save as test result')
    p_run.add_argument('bundle_yaml', type=Path, help='Path to bundle.yml file')
    p_run.add_argument('build_dir', type=Path, help='Path to build directory')
    p_run.add_argument('-ot', '--output-dir', required=True, help='Output directory for test result')
    p_run.set_defaults(func=cmd_run_tests)

    # compare subcommand
    p_compare = subparsers.add_parser('compare', help='Compare test result against reference')
    p_compare.add_argument('-og', '--ref-dir', required=True, help='Reference directory')
    p_compare.add_argument('-ot', '--test-dir', required=True, help='Test result directory')
    p_compare.set_defaults(func=cmd_compare)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
