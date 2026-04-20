# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for storage.system.expand_vars and expand_vars_in_tree."""

from __future__ import annotations

import pytest

from storage.system import expand_vars, expand_vars_in_tree


def test_no_placeholder_returns_unchanged() -> None:
    assert expand_vars("hello", {"x": "y"}) == "hello"


def test_simple_substitution() -> None:
    assert expand_vars("{{hostname}}-root", {"hostname": "foo"}) == "foo-root"


def test_multiple_substitutions() -> None:
    assert expand_vars("{{a}}-{{b}}", {"a": "1", "b": "2"}) == "1-2"


def test_whitespace_inside_braces() -> None:
    assert expand_vars("{{  hostname  }}", {"hostname": "foo"}) == "foo"


def test_undefined_variable_raises() -> None:
    with pytest.raises(KeyError, match="undefined template variable: missing"):
        expand_vars("{{missing}}", {})


def test_partial_braces_not_substituted() -> None:
    assert expand_vars("{one}", {"one": "x"}) == "{one}"
    assert expand_vars("{{one", {"one": "x"}) == "{{one"


def test_template_without_variables_dict_raises() -> None:
    with pytest.raises(KeyError):
        expand_vars("{{key}}", {})


def test_tree_walk_dict() -> None:
    tree = {"label": "{{hostname}}-root", "size": 8}
    out = expand_vars_in_tree(tree, {"hostname": "foo"})
    assert out == {"label": "foo-root", "size": 8}


def test_tree_walk_list() -> None:
    tree = ["{{a}}", "{{b}}", 42]
    out = expand_vars_in_tree(tree, {"a": "x", "b": "y"})
    assert out == ["x", "y", 42]


def test_tree_walk_nested() -> None:
    tree = {
        "storage": [
            {"type": "filesystem", "label": "{{hostname}}-root", "flags": ["boot"]},
            {"type": "hardware", "path": "/dev/sda"},
        ],
    }
    out = expand_vars_in_tree(tree, {"hostname": "foo"})
    assert out == {
        "storage": [
            {"type": "filesystem", "label": "foo-root", "flags": ["boot"]},
            {"type": "hardware", "path": "/dev/sda"},
        ],
    }


def test_tree_walk_non_string_leaves_untouched() -> None:
    tree = {"n": 42, "b": True, "none": None, "f": 1.5}
    out = expand_vars_in_tree(tree, {})
    assert out == {"n": 42, "b": True, "none": None, "f": 1.5}


def test_invalid_identifier_not_matched() -> None:
    # Digits as first char → doesn't match, string preserved.
    assert expand_vars("{{1bad}}", {}) == "{{1bad}}"


def test_underscore_and_digits_in_name() -> None:
    assert expand_vars("{{_a1_B}}", {"_a1_B": "v"}) == "v"


def test_tree_walk_keys_not_expanded() -> None:
    tree = {"{{key}}": "value"}
    out = expand_vars_in_tree(tree, {"key": "expanded"})
    assert "{{key}}" in out
    assert "expanded" not in out
