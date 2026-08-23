"""Unit and integration tests for FORGE AI ReactGenerator component generation."""

import json
import pytest
from pathlib import Path

from backend.agents.react_generator import ReactGenerator
from backend.exceptions import MissingInputError, ValidationError, GenerationError


@pytest.fixture
def sample_ui_specs():
    """Provides sample UIOutput dictionary specifications for Task Management, Blog, and E-commerce applications."""
    return {
        "task_management": {
            "project_name": "TaskFlow",
            "pages": [
                {
                    "name": "DashboardPage",
                    "route_path": "/",
                    "layout": "MainLayout",
                    "description": "Task management dashboard overview",
                    "components_used": ["Navbar", "Sidebar", "TaskTable"],
                    "required_auth": True,
                    "state_requirements": ["currentUser"]
                }
            ],
            "components": [
                {
                    "name": "Navbar",
                    "type": "navbar",
                    "description": "Top navigation header",
                    "props": [
                        {"name": "user", "type": "UserObject", "required": "false"},
                        {"name": "onLogout", "type": "function", "required": "false"}
                    ],
                    "state_variables": [
                        {"name": "isProfileDropdownOpen", "type": "boolean", "default": "false"}
                    ],
                    "event_handlers": ["onToggleMenu", "onLogoutClick"],
                    "child_components": ["UserProfileDropdown", "ThemeToggle"]
                },
                {
                    "name": "Sidebar",
                    "type": "sidebar",
                    "description": "Collapsible side navigation bar",
                    "props": [
                        {"name": "activePath", "type": "string", "required": "true"}
                    ],
                    "state_variables": [
                        {"name": "isCollapsed", "type": "boolean", "default": "false"}
                    ],
                    "event_handlers": ["onNavigate"],
                    "child_components": []
                },
                {
                    "name": "TaskTable",
                    "type": "table",
                    "description": "Tabular display list for tasks",
                    "props": [
                        {"name": "items", "type": "Array", "required": "true"}
                    ],
                    "state_variables": [
                        {"name": "sortColumn", "type": "string", "default": "'id'"}
                    ],
                    "event_handlers": ["handleSort", "handleSelectRow"],
                    "child_components": []
                },
                {
                    "name": "StatsCard",
                    "type": "card",
                    "description": "Visual metric card",
                    "props": [
                        {"name": "title", "type": "string", "required": "true"},
                        {"name": "value", "type": "number", "required": "true"}
                    ],
                    "state_variables": [],
                    "event_handlers": [],
                    "child_components": []
                }
            ],
            "routes": [
                {
                    "path": "/",
                    "component_name": "DashboardPage",
                    "exact": True,
                    "protected": True,
                    "title": "TaskFlow - Dashboard"
                }
            ],
            "layouts": [
                {
                    "name": "MainLayout",
                    "description": "Standard layout",
                    "slots": ["main"],
                    "default_layout": True
                }
            ],
            "forms": [],
            "frontend_dependencies": [
                {"package_name": "react", "version": "^18.2.0", "purpose": "Core React", "category": "core"},
                {"package_name": "react-dom", "version": "^18.2.0", "purpose": "DOM renderer", "category": "core"},
                {"package_name": "axios", "version": "^1.6.2", "purpose": "HTTP client", "category": "http"},
                {"package_name": "lucide-react", "version": "^0.294.0", "purpose": "Icons", "category": "icons"}
            ],
            "api_requirements": [],
            "styling_requirements": {
                "theme_mode": "dark",
                "primary_color": "#6366F1",
                "font_family": "Inter, sans-serif",
                "design_system_notes": "Modern dark UI",
                "css_approach": "Vanilla CSS"
            }
        },
        "blog_app": {
            "project_name": "DevBlog Platform",
            "pages": [],
            "components": [
                {
                    "name": "PostCard",
                    "type": "card",
                    "description": "Article summary card",
                    "props": [
                        {"name": "post", "type": "Object", "required": "true"}
                    ],
                    "state_variables": [
                        {"name": "isLiked", "type": "boolean", "default": "false"}
                    ],
                    "event_handlers": ["onLikeClick"],
                    "child_components": []
                }
            ],
            "routes": [],
            "layouts": [],
            "forms": [],
            "frontend_dependencies": [
                {"package_name": "react", "version": "^18.2.0", "purpose": "Core React", "category": "core"},
                {"package_name": "swr", "version": "^2.2.0", "purpose": "Data fetching", "category": "state"}
            ],
            "api_requirements": [],
            "styling_requirements": {
                "theme_mode": "light",
                "primary_color": "#10B981",
                "font_family": "Roboto, sans-serif",
                "design_system_notes": "Clean blogging platform",
                "css_approach": "CSS Modules"
            }
        }
    }


def test_react_generator_missing_input_file(tmp_path):
    """Test exception raised when ui_output.json file does not exist."""
    generator = ReactGenerator(
        ui_output_path=str(tmp_path / "non_existent_ui.json"),
        output_dir=str(tmp_path / "frontend")
    )
    with pytest.raises(MissingInputError):
        generator.run()


def test_react_generator_invalid_json(tmp_path):
    """Test exception raised when ui_output.json contains malformed JSON."""
    bad_file = tmp_path / "bad_ui.json"
    bad_file.write_text("{ invalid json structure", encoding="utf-8")

    generator = ReactGenerator(
        ui_output_path=str(bad_file),
        output_dir=str(tmp_path / "frontend")
    )
    with pytest.raises(ValidationError):
        generator.run()


def test_react_generator_empty_input(tmp_path):
    """Test exception raised when ui_output.json file is empty."""
    empty_file = tmp_path / "empty_ui.json"
    empty_file.write_text("", encoding="utf-8")

    generator = ReactGenerator(
        ui_output_path=str(empty_file),
        output_dir=str(tmp_path / "frontend")
    )
    with pytest.raises(ValidationError):
        generator.run()


def test_react_generator_invalid_schema(tmp_path):
    """Test exception raised when ui_output.json lacks required schema fields."""
    incomplete_file = tmp_path / "incomplete_ui.json"
    incomplete_file.write_text(json.dumps({"invalid_field": True}), encoding="utf-8")

    generator = ReactGenerator(
        ui_output_path=str(incomplete_file),
        output_dir=str(tmp_path / "frontend")
    )
    with pytest.raises(ValidationError):
        generator.run()


def test_react_generator_valid_execution(tmp_path, sample_ui_specs):
    """Test valid execution of ReactGenerator producing foundation directory structure and component files."""
    ui_file = tmp_path / "ui_output.json"
    ui_file.write_text(json.dumps(sample_ui_specs["task_management"]), encoding="utf-8")

    out_dir = tmp_path / "frontend"
    generator = ReactGenerator(
        ui_output_path=str(ui_file),
        output_dir=str(out_dir)
    )

    result_path = generator.run()

    assert result_path == out_dir
    assert out_dir.is_dir()

    # Check foundation files existence
    assert (out_dir / "package.json").is_file()
    assert (out_dir / "index.html").is_file()
    assert (out_dir / "vite.config.js").is_file()
    assert (out_dir / "src" / "main.jsx").is_file()
    assert (out_dir / "src" / "App.jsx").is_file()
    assert (out_dir / "src" / "index.css").is_file()

    # Check directories existence
    assert (out_dir / "src" / "components").is_dir()
    assert (out_dir / "src" / "pages").is_dir()
    assert (out_dir / "src" / "layouts").is_dir()


def test_react_generator_package_json_dependencies(tmp_path, sample_ui_specs):
    """Test that package.json dynamically incorporates dependencies from ui_output.json."""
    ui_file = tmp_path / "ui_output.json"
    ui_file.write_text(json.dumps(sample_ui_specs["task_management"]), encoding="utf-8")

    out_dir = tmp_path / "frontend"
    generator = ReactGenerator(
        ui_output_path=str(ui_file),
        output_dir=str(out_dir)
    )
    generator.run()

    pkg_data = json.loads((out_dir / "package.json").read_text(encoding="utf-8"))

    assert pkg_data["name"] == "taskflow"
    assert "axios" in pkg_data["dependencies"]
    assert pkg_data["dependencies"]["axios"] == "^1.6.2"


def test_react_generator_component_files_creation(tmp_path, sample_ui_specs):
    """Test component files generation matches specifications in UIOutput.components."""
    ui_file = tmp_path / "ui_output.json"
    ui_file.write_text(json.dumps(sample_ui_specs["task_management"]), encoding="utf-8")

    out_dir = tmp_path / "frontend"
    generator = ReactGenerator(
        ui_output_path=str(ui_file),
        output_dir=str(out_dir)
    )
    generator.run()

    components_dir = out_dir / "src" / "components"
    generated_files = list(components_dir.glob("*.jsx"))

    # Number of generated files matches components count (4 specs: Navbar, Sidebar, TaskTable, StatsCard)
    assert len(generated_files) == 4

    expected_filenames = {"Navbar.jsx", "Sidebar.jsx", "TaskTable.jsx", "StatsCard.jsx"}
    actual_filenames = {f.name for f in generated_files}
    assert actual_filenames == expected_filenames


def test_react_generator_component_stateful_vs_non_stateful(tmp_path, sample_ui_specs):
    """Test props, useState hooks, event handlers, and React imports generation."""
    ui_file = tmp_path / "ui_output.json"
    ui_file.write_text(json.dumps(sample_ui_specs["task_management"]), encoding="utf-8")

    out_dir = tmp_path / "frontend"
    generator = ReactGenerator(
        ui_output_path=str(ui_file),
        output_dir=str(out_dir)
    )
    generator.run()

    components_dir = out_dir / "src" / "components"

    # Stateful component: Navbar
    navbar_code = (components_dir / "Navbar.jsx").read_text(encoding="utf-8")
    assert "import React, { useState } from 'react';" in navbar_code
    assert "function Navbar({ user, onLogout })" in navbar_code
    assert "const [isProfileDropdownOpen, setIsProfileDropdownOpen] = useState(false);" in navbar_code
    assert "const onToggleMenu = (event) => {" in navbar_code
    assert "export default Navbar;" in navbar_code

    # Non-stateful component: StatsCard
    stats_code = (components_dir / "StatsCard.jsx").read_text(encoding="utf-8")
    assert "import React from 'react';" in stats_code
    assert "useState" not in stats_code
    assert "function StatsCard({ title, value })" in stats_code
    assert "export default StatsCard;" in stats_code


def test_react_generator_child_components_safe_handling(tmp_path, sample_ui_specs):
    """Test child component imports and placeholders handling."""
    ui_file = tmp_path / "ui_output.json"
    ui_file.write_text(json.dumps(sample_ui_specs["task_management"]), encoding="utf-8")

    out_dir = tmp_path / "frontend"
    generator = ReactGenerator(
        ui_output_path=str(ui_file),
        output_dir=str(out_dir)
    )
    generator.run()

    components_dir = out_dir / "src" / "components"
    navbar_code = (components_dir / "Navbar.jsx").read_text(encoding="utf-8")

    # UserProfileDropdown and ThemeToggle are child components not defined in sample components list,
    # so they should NOT cause broken imports.
    assert "import UserProfileDropdown from" not in navbar_code
    assert "Child component UserProfileDropdown placeholder" in navbar_code


def test_react_generator_generic_multi_domain(tmp_path, sample_ui_specs):
    """Test that different UI outputs (TaskFlow vs DevBlog) produce generic domain-specific component sets."""
    blog_file = tmp_path / "ui_blog.json"
    blog_file.write_text(json.dumps(sample_ui_specs["blog_app"]), encoding="utf-8")

    out_dir = tmp_path / "frontend_blog"
    generator = ReactGenerator(
        ui_output_path=str(blog_file),
        output_dir=str(out_dir)
    )
    generator.run()

    components_dir = out_dir / "src" / "components"
    generated_files = list(components_dir.glob("*.jsx"))

    assert len(generated_files) == 1
    assert generated_files[0].name == "PostCard.jsx"

    post_code = (components_dir / "PostCard.jsx").read_text(encoding="utf-8")
    assert "function PostCard({ post })" in post_code
    assert "const [isLiked, setIsLiked] = useState(false);" in post_code
    assert "const onLikeClick = (event) => {" in post_code
    assert "export default PostCard;" in post_code
