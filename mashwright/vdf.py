"""Valve KeyValues (text VDF/ACF) parser: "key" "value" pairs and "key" { ... } blocks.

Tolerates comments (//), unquoted tokens, escaped quotes and conditional suffixes like [$WIN32].
Keys are kept as written; lookups with get_ci() ignore case (Steam is inconsistent).
"""

from typing import Dict, List, Optional, Union

Value = Union[str, Dict[str, "Value"]]


def _tokens(text: str) -> List[str]:
    out: List[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
        elif c in "{}":
            out.append(c)
            i += 1
        elif c == '"':
            i += 1
            buf = []
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    nxt = text[i + 1]
                    buf.append({"n": "\n", "t": "\t", "\\": "\\", '"': '"'}.get(nxt, "\\" + nxt))
                    i += 2
                    continue
                buf.append(text[i])
                i += 1
            i += 1
            out.append("\x00" + "".join(buf))  # \x00 marks a string token (vs. braces)
        elif c == "[":
            while i < n and text[i] != "]":  # conditional like [$WIN32]: ignore
                i += 1
            i += 1
        else:
            j = i
            while j < n and text[j] not in ' \t\r\n{}"':
                j += 1
            out.append("\x00" + text[i:j])
            i = j
    return out


def loads(text: str) -> Dict[str, Value]:
    toks = _tokens(text.lstrip("﻿"))
    pos = 0

    def block() -> Dict[str, Value]:
        nonlocal pos
        d: Dict[str, Value] = {}
        while pos < len(toks):
            t = toks[pos]
            if t == "}":
                pos += 1
                return d
            if t == "{":  # stray brace: skip
                pos += 1
                continue
            key = t[1:]
            pos += 1
            if pos >= len(toks):
                break
            nxt = toks[pos]
            if nxt == "{":
                pos += 1
                d[key] = block()
            elif nxt == "}":
                d[key] = ""
            else:
                d[key] = nxt[1:]
                pos += 1
        return d

    return block()


def load_file(path) -> Dict[str, Value]:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return loads(f.read())


def get_ci(d: Dict[str, Value], *keys: str, default=None):
    """Nested lookup ignoring key case: get_ci(d, "AppState", "installdir")."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        found = None
        for kk, vv in cur.items():
            if kk.lower() == k.lower():
                found = vv
                break
        if found is None:
            return default
        cur = found
    return cur
