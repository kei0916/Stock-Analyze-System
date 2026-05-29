"""PageIndex ライブラリの optional import + pypdf 互換層."""
from __future__ import annotations

import sys


def _install_pypdf_compat() -> None:
    """Expose pypdf under the legacy PyPDF2 name for PageIndex compatibility."""
    if "PyPDF2" in sys.modules:
        return
    try:
        import pypdf
    except ImportError:  # pragma: no cover
        return
    sys.modules.setdefault("PyPDF2", pypdf)


_install_pypdf_compat()

try:
    from pageindex import page_index
except ImportError:  # pragma: no cover
    page_index = None  # type: ignore[assignment]

try:
    from pageindex import (
        ConfigLoader,
        add_node_text,
        get_page_tokens,
        get_pdf_name,
        remove_structure_text,
        tree_parser,
        write_node_id,
    )
    from pageindex.utils import (
        configure_litellm_timeout,
        configure_max_tokens,
        configure_thinking,
        extract_json as _pi_extract_json,
        llm_acompletion,
        structure_to_list,
    )

    _HAS_PAGEINDEX_ASYNC_HELPERS = True
except ImportError:  # pragma: no cover
    ConfigLoader = None  # type: ignore[assignment]
    add_node_text = None  # type: ignore[assignment]
    get_page_tokens = None  # type: ignore[assignment]
    get_pdf_name = None  # type: ignore[assignment]
    remove_structure_text = None  # type: ignore[assignment]
    tree_parser = None  # type: ignore[assignment]
    write_node_id = None  # type: ignore[assignment]
    configure_litellm_timeout = None  # type: ignore[assignment]
    configure_max_tokens = None  # type: ignore[assignment]
    configure_thinking = None  # type: ignore[assignment]
    _pi_extract_json = None  # type: ignore[assignment]
    llm_acompletion = None  # type: ignore[assignment]
    structure_to_list = None  # type: ignore[assignment]
    _HAS_PAGEINDEX_ASYNC_HELPERS = False
