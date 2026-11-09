"""One text-folding function for indexed search text and for search queries.

Purpose:
Make ``cafe``/``café``, ``noi``/``Nội``, ``pho``/``Phố``, ``ﾈｵﾝ``/``ネオン``/``ねおん`` match each other
without depending on the SQLite version (the ``trigram`` tokenizer only gained ``remove_diacritics`` in
SQLite 3.45). Indexed documents and queries both go through ``fold_text``; display text is never folded.

Guarantees:
* NFKC first (full-width Latin, half-width katakana with voiced marks composed, ligatures)
* case folding (``casefold``: ``ß`` -> ``ss``)
* every combining mark in the Combining Diacritical Mark blocks is removed, including Vietnamese stacked
  marks; kana voiced/semi-voiced marks (U+3099/U+309A) and other scripts' marks are kept
* ``đ``/``Đ`` -> ``d``
* katakana -> hiragana (the prolonged-sound mark ``ー`` is shared and kept)
* the result is NFC, so composed kana (``が``) stay one character
* the function is pure and idempotent: ``fold_text(fold_text(x)) == fold_text(x)``

Run when:
* changing what text is indexed or how queries are tokenized; changing it requires rebuilding the folded
  index (``search_text_index.rebuild_search_text_index``) and a new schema version.
"""

from __future__ import annotations

import re
import unicodedata

# Combining Diacritical Marks, Extended, Supplement, For Symbols and Half Marks.
_STRIP_MARKS_RE = re.compile("[̀-ͯ᪰-᫿᷀-᷿⃐-⃿︠-︯]")
_KATAKANA_TO_HIRAGANA = {code: code - 0x60 for code in range(0x30A1, 0x30F7)}
_KATAKANA_TO_HIRAGANA.update({0x30FD: 0x309D, 0x30FE: 0x309E})
_EXTRA = {ord("đ"): "d", ord("Đ"): "d"}
_TRANSLATE = {**_KATAKANA_TO_HIRAGANA, **_EXTRA}


def fold_text(text: str | None) -> str:
    """Return the search-folded form of ``text`` ('' for ``None``)."""
    if not text:
        return ""
    folded = unicodedata.normalize("NFKC", text).casefold()
    if folded.isascii():
        return folded
    folded = unicodedata.normalize("NFD", folded)
    folded = _STRIP_MARKS_RE.sub("", folded)
    folded = unicodedata.normalize("NFC", folded)
    return folded.translate(_TRANSLATE)
