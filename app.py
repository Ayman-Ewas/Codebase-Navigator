import re
import requests
import streamlit as st

# ------------------------------------------------------------------
# Page config
# ------------------------------------------------------------------
st.set_page_config(
    page_title="Codebase Navigator",
    layout="wide",
)

# ------------------------------------------------------------------
# Session state
# ------------------------------------------------------------------
defaults = {
    "messages": [],
    "repo_loaded": False,
    "loaded_repo": "",
    "files_indexed": 0,
}
for k, v in defaults.items():
    st.session_state.setdefault(k, v)

# ------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------
with st.sidebar:
    st.header("Configuration")

    api_base = st.text_input(
        "API Base URL",
        value="https://shakily-smooth-scrubbed.ngrok-free.dev",
        help="Paste the ngrok public URL printed by your notebook.",
    ).rstrip("/")

    st.divider()
    st.header("Load Repository")

    repo_url = st.text_input(
        "GitHub repository URL",
        placeholder="https://github.com/owner/repo",
        value=st.session_state.loaded_repo,
    )

    load_btn = st.button(
        "Load Repository",
        type="primary",
        use_container_width=True,
    )

    if st.session_state.repo_loaded:
        st.success(f"✅ `{st.session_state.loaded_repo}`")
        st.caption(f"Files indexed: **{st.session_state.files_indexed}**")

    st.divider()
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ------------------------------------------------------------------
# Load repo handler
# ------------------------------------------------------------------
def load_repository(api_base: str, repo_url: str):
    """Call /load_repo and update session state. Returns (ok, message)."""
    try:
        r = requests.post(
            f"{api_base}/load_repo",
            json={"repo_url": repo_url},
            headers={"ngrok-skip-browser-warning": "true"},
            timeout=1800,
        )
    except requests.exceptions.ConnectionError:
        return False, f"Cannot reach API at `{api_base}`. Is the notebook cell still running?"

    if r.status_code != 200:
        return False, f"API error {r.status_code}: {r.text}"

    data = r.json()
    st.session_state.repo_loaded = True
    st.session_state.loaded_repo = repo_url
    st.session_state.files_indexed = data.get("files_indexed", 0)
    st.session_state.messages = []
    return True, data.get("message", "Repository loaded.")


if load_btn:
    if not repo_url.strip():
        st.sidebar.error("Please enter a GitHub URL.")
    else:
        with st.sidebar, st.spinner("Cloning + indexing... (may take a few minutes)"):
            ok, msg = load_repository(api_base, repo_url.strip())
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

# ------------------------------------------------------------------
# Header
# ------------------------------------------------------------------
st.title("Codebase Mind")
st.caption("Ask questions about any GitHub repository — RAG + Mistral-7B-Instruct.")

if not st.session_state.repo_loaded:
    st.info("👈 Load a repository from the sidebar to start asking questions.")
    st.stop()

# ------------------------------------------------------------------
# Optional: turn `path/to/file.ext` into GitHub links
# ------------------------------------------------------------------
def linkify_files(markdown_text: str, repo_url: str) -> str:
    """
    Convert inline-code file references (`` `app/models/task.rb` ``)
    into markdown links to the GitHub blob view.
    """
    if not repo_url:
        return markdown_text

    # strip trailing slash, build blob base
    base = repo_url.rstrip("/")
    # naive but effective: match any `something.ext` inside backticks
    pattern = re.compile(r"`([\w][\w./-]*\.\w{1,6})`")

    def repl(m):
        path = m.group(1)
        return f"[`{path}`]({base}/blob/main/{path})"

    return pattern.sub(repl, markdown_text)


# ------------------------------------------------------------------
# Chat history
# ------------------------------------------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        content = msg["content"]
        if msg["role"] == "assistant":
            content = linkify_files(content, st.session_state.loaded_repo)
        st.markdown(content)

# ------------------------------------------------------------------
# Chat input
# ------------------------------------------------------------------
if prompt := st.chat_input("Ask something about the codebase..."):
    # 1. Show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Ask the API
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                r = requests.post(
                    f"{api_base}/ask",
                    json={"question": prompt},
                    headers={"ngrok-skip-browser-warning": "true"},
                    timeout=600,
                )
                if r.status_code == 200:
                    answer = r.json().get("answer", "_(empty response)_")
                elif r.status_code == 400:
                    answer = f"⚠️ {r.json().get('detail', r.text)}"
                else:
                    answer = f"❌ API error {r.status_code}: {r.text}"
            except requests.exceptions.ConnectionError:
                answer = f"❌ Cannot reach API at `{api_base}`."
            except Exception as e:
                answer = f"❌ Unexpected error: {e}"

        rendered = linkify_files(answer, st.session_state.loaded_repo)
        st.markdown(rendered)
        st.session_state.messages.append(
            {"role": "assistant", "content": answer}
        )