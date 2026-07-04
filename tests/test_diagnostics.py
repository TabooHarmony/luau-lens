#!/usr/bin/env python3
"""Test luau-lens against real luau-lsp + selene with known-bad Luau code."""

import json
import os
import sys
import tempfile

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from luau_lens import bootstrap, runners, parsers


def test() -> bool:
    """Run all tests. Returns True if all pass."""
    print("=== luau-lens test suite ===\n")

    # Ensure tools are downloaded
    print("1. Bootstrap: downloading tools if needed...")
    bootstrap.ensure_tools()
    paths = bootstrap.get_paths()
    print(f"   luau-lsp: {paths['luau_lsp']} ({'exists' if paths['luau_lsp'].exists() else 'MISSING'})")
    print(f"   selene:   {paths['selene']} ({'exists' if paths['selene'].exists() else 'MISSING'})")
    print(f"   stylua:   {paths['stylua']} ({'exists' if paths['stylua'].exists() else 'MISSING'})")
    print(f"   defs:     {paths['defs']} ({'exists' if paths['defs'].exists() else 'MISSING'})")
    print()

    all_pass = True

    # Test 1: type error
    print("2. Test: type mismatch (number = string)")
    result = runners.check_code('local x: number = "hello"')
    errors = result.get("summary", {}).get("errors", 0)
    total = result.get("summary", {}).get("total", 0)
    print(f"   errors={errors}, total={total}")
    for d in result.get("diagnostics", []):
        print(f"   [{d['severity']}] {d['source']}: {d['message']}")
    if errors < 1:
        print("   FAIL: expected at least 1 error")
        all_pass = False
    else:
        print("   PASS")
    print()

    # Test 2: unused variable (selene lint)
    print("3. Test: unused variable")
    result = runners.check_code('local function foo()\n    local unused = 42\n    return unused\nend\n')
    warnings = result.get("summary", {}).get("warnings", 0)
    print(f"   warnings={warnings}, total={result.get('summary', {}).get('total', 0)}")
    for d in result.get("diagnostics", []):
        print(f"   [{d['severity']}] {d['source']}: {d['message']}")
    if warnings < 1:
        print("   FAIL: expected at least 1 warning")
        all_pass = False
    else:
        print("   PASS")
    print()

    # Test 3: clean code (no errors, unused warnings are expected for standalone functions)
    print("4. Test: clean code (no errors)")
    result = runners.check_code('local function add(a: number, b: number): number\n    return a + b\nend\n')
    errors = result.get("summary", {}).get("errors", 0)
    print(f"   errors={errors}, total={result.get('summary', {}).get('total', 0)}")
    for d in result.get("diagnostics", []):
        print(f"   [{d['severity']}] {d['source']}: {d['message']}")
    if errors != 0:
        print("   FAIL: expected 0 errors")
        all_pass = False
    else:
        print("   PASS (unused-function warnings are expected for standalone snippets)")
    print()

    # Test 4: Roblox API type error (requires type definitions)
    print("5. Test: Roblox API type error (property mismatch)")
    result = runners.check_code(
        'local part = Instance.new("Part")\n'
        'part.Transparency = "hello"\n'
        'part.NonExistentProperty = true\n',
        filename="test_roblox.luau"
    )
    total = result.get("summary", {}).get("total", 0)
    print(f"   total={total}")
    for d in result.get("diagnostics", []):
        print(f"   [{d['severity']}] {d['source']}: {d['message']}")
    if total < 1:
        print("   FAIL: expected at least 1 diagnostic for bad Roblox API usage")
        all_pass = False
    else:
        print("   PASS")
    print()

    # Test 5: divide by zero (selene lint)
    print("6. Test: divide by zero (selene)")
    result = runners.check_code('local x = 1 / 0\nprint(x)\n')
    warnings = result.get("summary", {}).get("warnings", 0)
    print(f"   warnings={warnings}, total={result.get('summary', {}).get('total', 0)}")
    for d in result.get("diagnostics", []):
        print(f"   [{d['severity']}] {d['source']}: {d['message']}")
    if warnings < 1:
        print("   FAIL: expected divide_by_zero warning")
        all_pass = False
    else:
        print("   PASS")
    print()

    # Test 6: file on disk
    print("7. Test: check_file with temp file on disk")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".luau", delete=False, encoding="utf-8") as f:
        f.write('local x: number = "oops"\n')
        f.flush()
        tmp_path = f.name
    try:
        result = runners.check_file(tmp_path)
        errors = result.get("summary", {}).get("errors", 0)
        print(f"   errors={errors}, total={result.get('summary', {}).get('total', 0)}")
        for d in result.get("diagnostics", []):
            print(f"   [{d['severity']}] {d['source']}: {d['message']}")
        if errors < 1:
            print("   FAIL: expected at least 1 error")
            all_pass = False
        else:
            print("   PASS")
    finally:
        os.unlink(tmp_path)
    print()

    # Test 7: parser unit tests
    print("8. Test: parser — luau-lsp plain format")
    sample = 'test.luau:1:1-25: (W0) TypeError: Expected this to be \'number\', but got \'string\'\n'
    sample += 'test.luau:5:7-12: (W0) LocalUnused: Variable \'result\' is never used\n'
    sample += '[INFO] Loading definitions file: @roblox\n'
    sample += 'WARNING: --platform is set to \'roblox\'\n'
    diags = parsers.parse_luau_lsp(sample, "")
    print(f"   parsed {len(diags)} diagnostics (expected 2)")
    for d in diags:
        print(f"   {d.severity} {d.code} line={d.line} col={d.column}: {d.message}")
    if len(diags) != 2:
        print("   FAIL: expected 2 diagnostics, INFO/WARNING lines should be filtered")
        all_pass = False
    elif diags[0].severity != "error" or diags[1].severity != "warning":
        print("   FAIL: wrong severity mapping")
        all_pass = False
    else:
        print("   PASS")
    print()

    # Test 8: selene JSON parser
    print("9. Test: parser — selene JSON format")
    sample = '{"severity":"Warning","code":"divide_by_zero","message":"dividing by zero is not allowed","primary_label":{"filename":"test.luau","span":{"start":0,"start_line":0,"start_column":14,"end":5,"end_line":0,"end_column":19}},"notes":[],"secondary_labels":[]}\n'
    sample += 'Results:\n0 errors\n1 warnings\n0 parse errors\n'
    diags = parsers.parse_selene(sample)
    print(f"   parsed {len(diags)} diagnostics (expected 1)")
    for d in diags:
        print(f"   {d.severity} {d.code} line={d.line} col={d.column}: {d.message}")
    if len(diags) != 1:
        print("   FAIL: expected 1 diagnostic, Results: line should be filtered")
        all_pass = False
    elif diags[0].code != "divide_by_zero":
        print("   FAIL: wrong code")
        all_pass = False
    elif diags[0].line != 1:  # 0-indexed → 1-indexed
        print(f"   FAIL: wrong line number (expected 1, got {diags[0].line})")
        all_pass = False
    else:
        print("   PASS")
    print()

    # Test 9: StyLua format — already formatted code
    print("10. Test: format_code — already formatted code")
    clean_code = 'local function add(a: number, b: number): number\n\treturn a + b\nend\n'
    result = runners.run_stylua_format(clean_code)
    changed = result.get("changed", True)
    formatted = result.get("formatted_code", "")
    print(f"   changed={changed}")
    print(f"   formatted matches input: {formatted == clean_code}")
    if "error" in result:
        print(f"   FAIL: {result['error']}")
        all_pass = False
    elif changed:
        print("   FAIL: code was already formatted, changed should be False")
        all_pass = False
    else:
        print("   PASS")
    print()

    # Test 10: StyLua format — unformatted code
    print("11. Test: format_code — unformatted code gets fixed")
    bad_code = 'local function add(a:number,b:number)\nreturn a+b\nend'
    result = runners.run_stylua_format(bad_code)
    changed = result.get("changed", False)
    formatted = result.get("formatted_code", "")
    print(f"   changed={changed}")
    print(f"   formatted code:\n   {repr(formatted)}")
    if "error" in result:
        print(f"   FAIL: {result['error']}")
        all_pass = False
    elif not changed:
        print("   FAIL: code needed formatting, changed should be True")
        all_pass = False
    elif formatted == bad_code:
        print("   FAIL: formatted code is identical to input")
        all_pass = False
    else:
        print("   PASS")
    print()

    # Test 11: check_code includes formatting diagnostic for unformatted code
    print("12. Test: check_code detects formatting issues")
    bad_format = 'local x=1\nlocal y    =    2\n'
    result = runners.check_code(bad_format)
    stylua_diags = [d for d in result.get("diagnostics", []) if d.get("source") == "stylua"]
    print(f"   stylua diagnostics: {len(stylua_diags)}")
    for d in stylua_diags:
        print(f"   [{d['severity']}] {d['source']}: {d['message']}")
    if len(stylua_diags) < 1:
        print("   FAIL: expected at least 1 stylua formatting diagnostic")
        all_pass = False
    else:
        print("   PASS")
    print()

    # Summary
    print("=== Results ===")
    if all_pass:
        print("ALL TESTS PASSED")
        return True
    else:
        print("SOME TESTS FAILED")
        return False


if __name__ == "__main__":
    success = test()
    sys.exit(0 if success else 1)
