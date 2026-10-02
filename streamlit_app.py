"""쇼핑 리스트 Streamlit 버전.

웹 버전(index.html / app.js)과 같은 기능과 데이터 모델을 사용한다.
브라우저 localStorage 대신 같은 폴더의 shopping_list.json 파일에 저장한다.

실행: streamlit run streamlit_app.py
"""

import html
import json
import time
import uuid
from pathlib import Path

import streamlit as st

DATA_FILE = Path(__file__).with_name("shopping_list.json")
MAX_NAME_LENGTH = 100

EMPTY_TEXT = "쇼핑 리스트가 비어 있어요. 아이템을 추가해 보세요!"
FILTER_EMPTY_TEXT = {
    "active": "남은 아이템이 없어요. 모두 구매했어요!",
    "completed": "아직 완료한 아이템이 없어요.",
}
FILTER_LABELS = {"all": "전체", "active": "미완료", "completed": "완료"}

PAGE_STYLE = """
<style>
  .item-name { overflow-wrap: anywhere; font-size: 1rem; line-height: 1.5; }
  .item-name.checked { text-decoration: line-through; opacity: 0.55; }

  /* 터치 영역 최소 44x44px */
  [data-testid="stHorizontalBlock"] button { min-height: 44px; min-width: 44px; }
  [data-testid="stCheckbox"] label { min-height: 44px; min-width: 44px; justify-content: center; align-items: center; }

  /* Streamlit은 좁은 화면에서 열을 세로로 쌓는다. 한 줄 배치를 유지하고 이름/입력 열만 늘린다. */
  @media (max-width: 640px) {
    [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 0.25rem !important; }
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
      width: auto !important; min-width: 0 !important; flex: 0 0 auto !important;
    }
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:has(.item-name),
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:has([data-testid="stTextInput"]) {
      flex: 1 1 0 !important;
    }
    /* "Press Enter to submit form" 안내가 placeholder와 겹치므로 숨긴다. */
    [data-testid="InputInstructions"] { display: none; }
  }
</style>
"""

# Streamlit 위젯만으로는 안 되는 PRD 동작을 보완한다.
# 더블클릭으로 편집, Esc로 편집 취소, 편집 입력창 자동 포커스, 체크 후 포커스 복원.
PAGE_SCRIPT = """
<script>
(() => {
  if (window.__shoppingListEnhanced) return;
  window.__shoppingListEnhanced = true;

  const EDIT_INPUT = 'input[aria-label$=" 이름 수정"]';
  const findButton = (root, text) =>
    root && [...root.querySelectorAll('button')].find((b) => b.innerText.trim() === text);

  document.addEventListener('dblclick', (event) => {
    const name = event.target.closest && event.target.closest('.item-name');
    if (!name) return;
    const button = findButton(name.closest('[data-testid="stHorizontalBlock"]'), '수정');
    if (button) button.click();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || event.isComposing) return;
    const input = event.target.closest && event.target.closest(EDIT_INPUT);
    if (!input) return;
    event.preventDefault();
    const button = findButton(input.closest('[data-testid="stForm"]'), '취소');
    if (button) button.click();
  });

  // 체크박스를 바꾸면 다시 그려진 뒤 같은 체크박스로 포커스를 돌려준다. (키보드 사용자용)
  let pendingFocusLabel = null;
  document.addEventListener('change', (event) => {
    if (event.target.matches && event.target.matches('[data-testid="stCheckbox"] input')) {
      pendingFocusLabel = event.target.getAttribute('aria-label');
    }
  });

  let focusedEditInput = null;
  new MutationObserver(() => {
    const input = document.querySelector(EDIT_INPUT);
    if (input && input !== focusedEditInput) {
      focusedEditInput = input;
      // Streamlit이 렌더링 직후 값을 다시 넣으면서 선택을 풀기 때문에 한 틱 뒤에 선택한다.
      setTimeout(() => {
        if (!input.isConnected) return;
        input.focus();
        input.select();
      }, 50);
    } else if (!input) {
      focusedEditInput = null;
    }

    if (pendingFocusLabel && (!document.activeElement || document.activeElement === document.body)) {
      const target = [...document.querySelectorAll('[data-testid="stCheckbox"] input')]
        .find((el) => el.getAttribute('aria-label') === pendingFocusLabel);
      if (target) {
        target.focus();
        pendingFocusLabel = null;
      }
    }
  }).observe(document.body, { childList: true, subtree: true });
})();
</script>
"""


# ---------- 데이터 ----------

def normalize_name(name) -> str:
    """앞뒤 공백을 제거하고 최대 길이로 자른다."""
    return str(name).strip()[:MAX_NAME_LENGTH]


def now_ms() -> int:
    return int(time.time() * 1000)


def is_valid_item(item) -> bool:
    return (
        isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and isinstance(item.get("name"), str)
        and item["name"].strip() != ""
    )


def load_items() -> list[dict]:
    """파일에서 목록을 불러온다. 파일이 없거나 손상되면 빈 목록을 반환한다."""
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []

    items = []
    seen_ids = set()
    for item in filter(is_valid_item, data):
        # id가 중복되면 위젯 key가 겹쳐 오류가 나므로 처음 것만 남긴다.
        if item["id"] in seen_ids:
            continue
        seen_ids.add(item["id"])
        created_at = item.get("createdAt")
        if isinstance(created_at, bool) or not isinstance(created_at, (int, float)):
            created_at = now_ms()
        items.append({
            "id": item["id"],
            "name": normalize_name(item["name"]),
            "checked": item.get("checked") is True,
            "createdAt": created_at,
        })
    return items


def save_items(items: list[dict]) -> None:
    """임시 파일에 쓴 뒤 교체해서 저장 도중 파일이 깨지지 않게 한다."""
    tmp_file = DATA_FILE.with_suffix(".tmp")
    tmp_file.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_file.replace(DATA_FILE)


def find_item(items: list[dict], item_id: str):
    return next((item for item in items if item["id"] == item_id), None)


# ---------- 콜백 (위젯 이벤트 처리) ----------

def add_item() -> None:
    name = normalize_name(st.session_state.get("new_item", ""))
    if not name:
        st.toast("살 물건을 입력해 주세요.", icon="✏️")
        return
    items = load_items()
    items.append({"id": str(uuid.uuid4()), "name": name, "checked": False, "createdAt": now_ms()})
    save_items(items)
    st.session_state.editing_id = None
    # 완료 필터에서는 새 아이템이 보이지 않으므로 전체 보기로 돌린다.
    if st.session_state.get("filter") == "completed":
        st.session_state.filter = "all"


def set_checked(item_id: str) -> None:
    items = load_items()
    item = find_item(items, item_id)
    if item:
        item["checked"] = st.session_state[f"check_{item_id}"]
        save_items(items)


def start_editing(item_id: str) -> None:
    item = find_item(load_items(), item_id)
    if item:
        st.session_state.editing_id = item_id
        st.session_state[f"edit_{item_id}"] = item["name"]


def save_editing(item_id: str) -> None:
    items = load_items()
    item = find_item(items, item_id)
    new_name = normalize_name(st.session_state.get(f"edit_{item_id}", ""))
    # 빈 값이면 원래 이름을 유지한다.
    if item and new_name:
        item["name"] = new_name
        save_items(items)
    st.session_state.editing_id = None


def cancel_editing() -> None:
    st.session_state.editing_id = None


def delete_item(item_id: str) -> None:
    save_items([item for item in load_items() if item["id"] != item_id])
    if st.session_state.get("editing_id") == item_id:
        st.session_state.editing_id = None


def clear_completed() -> None:
    save_items([item for item in load_items() if not item["checked"]])
    st.session_state.editing_id = None


def change_filter() -> None:
    st.session_state.editing_id = None


# ---------- 화면 ----------

def visible_items(items: list[dict], current_filter: str) -> list[dict]:
    """미체크 아이템을 위에, 체크된 아이템을 아래에 두고 각 그룹은 추가한 순서대로 정렬한다."""
    if current_filter == "active":
        items = [item for item in items if not item["checked"]]
    elif current_filter == "completed":
        items = [item for item in items if item["checked"]]
    return sorted(items, key=lambda item: (item["checked"], item["createdAt"]))


def render_name(item: dict) -> None:
    # 마크다운이나 HTML로 해석되지 않도록 이스케이프한 텍스트만 출력한다.
    css_class = "item-name checked" if item["checked"] else "item-name"
    st.html(f'<div class="{css_class}">{html.escape(item["name"])}</div>')


def render_view_row(item: dict) -> None:
    item_id = item["id"]
    check_col, name_col, edit_col, delete_col = st.columns(
        [0.7, 6, 1, 1], vertical_alignment="center", gap="small"
    )
    with check_col:
        # 파일 내용(다른 탭에서 바뀌었을 수 있음)에 체크박스 상태를 맞춘다.
        st.session_state[f"check_{item_id}"] = item["checked"]
        st.checkbox(
            f"{item['name']} 구매 완료",
            key=f"check_{item_id}",
            on_change=set_checked,
            args=(item_id,),
            label_visibility="collapsed",
        )
    with name_col:
        render_name(item)
    # 아이콘(material 글자가 접근 이름에 섞임)과 help(숨은 버튼이 하나 더 생김)는 쓰지 않는다.
    with edit_col:
        st.button(
            "수정", key=f"edit_btn_{item_id}", on_click=start_editing, args=(item_id,),
            type="tertiary",
        )
    with delete_col:
        st.button(
            "삭제", key=f"delete_btn_{item_id}", on_click=delete_item, args=(item_id,),
            type="tertiary",
        )


def render_edit_row(item: dict) -> None:
    item_id = item["id"]
    # 폼 안의 입력창에서 Enter를 누르면 첫 번째 제출 버튼(저장)이 실행된다.
    with st.form(key=f"edit_form_{item_id}", border=False):
        input_col, save_col, cancel_col = st.columns([6, 1, 1], vertical_alignment="bottom")
        with input_col:
            st.text_input(
                f"{item['name']} 이름 수정",
                key=f"edit_{item_id}",
                max_chars=MAX_NAME_LENGTH,
                label_visibility="collapsed",
            )
        with save_col:
            st.form_submit_button(
                "저장", on_click=save_editing, args=(item_id,), type="primary", width="stretch"
            )
        with cancel_col:
            st.form_submit_button("취소", on_click=cancel_editing, width="stretch")


def main() -> None:
    st.set_page_config(page_title="쇼핑 리스트", page_icon="🛒", layout="centered")
    st.html(PAGE_STYLE)
    st.html(PAGE_SCRIPT, unsafe_allow_javascript=True)

    st.session_state.setdefault("editing_id", None)
    st.session_state.setdefault("filter", "all")

    st.title("🛒 쇼핑 리스트")

    # 추가 폼: Enter 또는 [추가] 버튼으로 제출하고, 제출 후 입력창을 비운다.
    with st.form("add_form", clear_on_submit=True, border=False):
        input_col, button_col = st.columns([5, 1], vertical_alignment="bottom")
        with input_col:
            st.text_input(
                "살 물건",
                key="new_item",
                placeholder="살 물건을 입력하세요...",
                max_chars=MAX_NAME_LENGTH,
                label_visibility="collapsed",
            )
        with button_col:
            st.form_submit_button("추가", on_click=add_item, type="primary", width="stretch")

    items = load_items()
    checked_count = sum(item["checked"] for item in items)
    total = len(items)

    st.progress(checked_count / total if total else 0.0, text=f"{checked_count} / {total} 완료")

    current_filter = st.segmented_control(
        "목록 필터",
        options=list(FILTER_LABELS),
        format_func=FILTER_LABELS.get,
        key="filter",
        required=True,  # 선택된 필터를 다시 눌러도 선택이 해제되지 않게 한다.
        on_change=change_filter,
        label_visibility="collapsed",
    ) or "all"

    shown = visible_items(items, current_filter)

    if not shown:
        st.info(EMPTY_TEXT if total == 0 else FILTER_EMPTY_TEXT.get(current_filter, EMPTY_TEXT), icon="🧺")

    for item in shown:
        with st.container(border=True):
            if item["id"] == st.session_state.editing_id:
                render_edit_row(item)
            else:
                render_view_row(item)

    if total:
        st.button(
            "완료 항목 삭제", icon=":material/delete_sweep:",
            on_click=clear_completed, disabled=checked_count == 0,
        )


main()
