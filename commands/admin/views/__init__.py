"""
Admin Panel Views using Discord Components v2.

Provides the PanelNode engine and base layout utilities per
ADMIN_PANEL_STANDARD.md.
"""

from .base import (
    AdminLayoutBuilder as AdminLayoutBuilder,
    cid as cid,
    create_empty_layout as create_empty_layout,
    create_error_layout as create_error_layout,
    create_success_layout as create_success_layout,
    readonly_container as readonly_container,
    editable_container as editable_container,
    notice_container as notice_container,
    premium_container as premium_container,
    build_notice_layout as build_notice_layout,
    build_premium_layout as build_premium_layout,
    safe_edit as safe_edit,
    safe_followup_notice as safe_followup_notice,
    READONLY_COLOR as READONLY_COLOR,
    NOTICE_COLOR as NOTICE_COLOR,
    PREMIUM_COLOR as PREMIUM_COLOR,
)

from .panel_engine import (
    PanelNode as PanelNode,
    PanelInputModal as PanelInputModal,
    PanelFileUploadModal as PanelFileUploadModal,
    build_menu_view as build_menu_view,
    build_select_view as build_select_view,
    build_modal_trigger_view as build_modal_trigger_view,
    build_dual_modal_trigger_view as build_dual_modal_trigger_view,
    build_file_upload_view as build_file_upload_view,
    build_dict_editor_view as build_dict_editor_view,
    build_overview_view as build_overview_view,
)

from .panel_views import PanelSession as PanelSession
