from __future__ import annotations


def _tool(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": False,
        },
    }


def get_tool_schemas() -> list[dict]:
    return [
        _tool("volume_up", "Increase system volume.", {"step": {"type": "integer", "minimum": 1, "maximum": 50}}),
        _tool("volume_down", "Decrease system volume.", {"step": {"type": "integer", "minimum": 1, "maximum": 50}}),
        _tool("mute_audio", "Mute system audio.", {}),
        _tool("unmute_audio", "Unmute system audio.", {}),
        _tool("toggle_mute", "Toggle mute state.", {}),
        _tool("media_play_pause", "Play or pause media.", {}),
        _tool("media_next", "Play next track.", {}),
        _tool("media_previous", "Play previous track.", {}),
        _tool(
            "take_screenshot",
            "Take a screenshot and save as PNG.",
            {"save_path": {"type": "string", "description": "Optional output file path."}},
        ),
        _tool(
            "find_file_by_name",
            "Find files by name in allowed directories.",
            {
                "name": {"type": "string"},
                "scope_dirs": {"type": "array", "items": {"type": "string"}},
            },
            required=["name"],
        ),
        _tool(
            "rename_file",
            "Rename a file.",
            {"path": {"type": "string"}, "new_name": {"type": "string"}},
            required=["path", "new_name"],
        ),
        _tool(
            "move_file",
            "Move a file.",
            {"src": {"type": "string"}, "dst": {"type": "string"}},
            required=["src", "dst"],
        ),
        _tool(
            "copy_file",
            "Copy a file.",
            {"src": {"type": "string"}, "dst": {"type": "string"}},
            required=["src", "dst"],
        ),
        _tool(
            "delete_file",
            "Delete a file or folder. Requires confirmation.",
            {"path": {"type": "string"}, "safe_mode": {"type": "boolean"}},
            required=["path"],
        ),
        _tool("create_folder", "Create a folder.", {"path": {"type": "string"}}, required=["path"]),
        _tool(
            "extract_archive",
            "Extract a zip archive.",
            {"path": {"type": "string"}, "dst": {"type": "string"}},
            required=["path", "dst"],
        ),
        _tool(
            "create_archive",
            "Create a zip archive from files.",
            {
                "paths": {"type": "array", "items": {"type": "string"}},
                "archive_name": {"type": "string"},
            },
            required=["paths", "archive_name"],
        ),
        _tool("extract_text_docx", "Extract text from .docx.", {"path": {"type": "string"}}, required=["path"]),
        _tool("extract_text_pdf", "Extract text from .pdf.", {"path": {"type": "string"}}, required=["path"]),
        _tool("summarize_document", "Summarize a document.", {"path": {"type": "string"}}, required=["path"]),
        _tool("open_document", "Open a document with default app.", {"path": {"type": "string"}}, required=["path"]),
        _tool(
            "search_docs_by_keyword",
            "Search indexed documents by keyword.",
            {"query": {"type": "string"}},
            required=["query"],
        ),
        _tool(
            "search_filename",
            "Search file index by filename.",
            {"query": {"type": "string"}},
            required=["query"],
        ),
        _tool(
            "search_file_content",
            "Search file index by full text.",
            {
                "query": {"type": "string"},
                "file_types": {"type": "array", "items": {"type": "string"}},
            },
            required=["query"],
        ),
        _tool("rebuild_index", "Rebuild local file index.", {}),
        _tool(
            "schedule_shutdown",
            "Schedule Windows shutdown in N minutes. Requires confirmation.",
            {"minutes": {"type": "integer", "minimum": 1, "maximum": 1440}},
            required=["minutes"],
        ),
        _tool("cancel_shutdown", "Cancel shutdown schedule.", {}),
        _tool(
            "schedule_open_app",
            "Schedule app launch in N minutes.",
            {
                "app": {"type": "string"},
                "minutes": {"type": "integer", "minimum": 1, "maximum": 1440},
            },
            required=["app", "minutes"],
        ),
        _tool("open_app", "Open whitelisted app immediately.", {"app": {"type": "string"}}, required=["app"]),
        _tool("enable_startup", "Enable app autostart in Windows. Requires confirmation.", {}),
        _tool("disable_startup", "Disable app autostart in Windows. Requires confirmation.", {}),
        _tool("get_system_info", "Get system information via safe shell template.", {}),
        _tool("get_local_ip", "Get local IP address.", {}),
        _tool("get_public_ip", "Get external IP address.", {}),
        _tool("check_internet", "Check internet connectivity.", {}),
        _tool("ping_host", "Ping allowed host.", {"host": {"type": "string"}}, required=["host"]),
        _tool(
            "restart_network_adapter",
            "Restart network adapter. Requires confirmation.",
            {"adapter_name": {"type": "string"}},
        ),
        _tool(
            "create_txt",
            "Create .txt file in allowed directory.",
            {"filename": {"type": "string"}, "content": {"type": "string"}},
            required=["filename", "content"],
        ),
        _tool(
            "create_docx",
            "Create .docx file in allowed directory.",
            {"filename": {"type": "string"}, "content": {"type": "string"}},
            required=["filename", "content"],
        ),
        _tool(
            "create_markdown",
            "Create .md file in allowed directory.",
            {"filename": {"type": "string"}, "content": {"type": "string"}},
            required=["filename", "content"],
        ),
        _tool(
            "create_ps1",
            "Create .ps1 script in allowed directory. Requires confirmation.",
            {"filename": {"type": "string"}, "content": {"type": "string"}},
            required=["filename", "content"],
        ),
        _tool(
            "create_email_template",
            "Create email template as text file.",
            {"filename": {"type": "string"}, "content": {"type": "string"}},
            required=["filename", "content"],
        ),
        _tool("clean_downloads", "Clean Downloads folder. Requires confirmation.", {}),
        _tool("cancel_scheduled_task", "Cancel scheduled task by id.", {"job_id": {"type": "string"}}, required=["job_id"]),
        _tool("list_scheduled_tasks", "List scheduled tasks.", {}),
        _tool(
            "send_file_to_chat",
            "Send a local file to the Telegram chat.",
            {"path": {"type": "string"}},
            required=["path"],
        ),
    ]
