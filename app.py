import sys
from pathlib import Path

import streamlit as st


def load_markdown(md_path: Path) -> str:
    if not md_path.exists():
        st.error(f"File not found: {md_path}")
        st.stop()
    try:
        return md_path.read_text(encoding="utf-8")
    except Exception as exc:
        st.error(f"Failed to read markdown: {exc}")
        st.stop()


def main() -> None:
    st.set_page_config(page_title="LP One-Pager Viewer", layout="wide")

    # Default to latest generated nondet one-pager; allow override via CLI arg
    default_md = Path("output/LP_OnePager_Acme_Software_Inc_2025_09_30_nondet.md")
    md_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else default_md
    md_path = md_arg.resolve()

    st.title("LP One-Pager")
    st.caption(str(md_path))

    md = load_markdown(md_path)
    st.markdown(md, unsafe_allow_html=True)

    with st.expander("Download / Raw"):
        st.download_button("Download markdown", md, file_name=md_path.name)
        st.code(md)


if __name__ == "__main__":
    main()
