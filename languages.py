"""
Per-language settings for the C-family lexer.

The scanning ALGORITHM is the same for C and C++ (and later Java), so instead of
writing a separate lexer for each language we keep one lexer and give it a
"language config": which words are keywords, which operators exist, and a sample
program for the UI. Adding a language = adding another config here.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LanguageConfig:
    id: str
    name: str
    keywords: dict          # word -> group name (shown in the token table)
    literal_words: dict     # words that are literals, e.g. true -> "boolean"
    alt_operators: frozenset  # operators spelled as words, e.g. "and", "not" (C++)
    ops3: frozenset
    ops2: frozenset
    ops1: frozenset
    string_prefixes: frozenset = frozenset({"L", "u", "U", "u8"})
    sample: str = ""
    notes: str = ""


# ---------------------------------------------------------------- C keywords
_C_GROUPS = {
    "data type": "char double float int long short signed unsigned void _Bool _Complex _Imaginary",
    "type declaration": "struct union enum typedef",
    "control flow": "if else for while do switch case default break continue goto return",
    "storage / qualifier": "auto const extern register static volatile inline restrict _Atomic _Thread_local _Noreturn",
    "other": "sizeof _Alignof _Alignas _Generic _Static_assert",
}

# ------------------------------------------------- extra / changed in C++
_CPP_ONLY_GROUPS = {
    "data type": "bool wchar_t char8_t char16_t char32_t auto",
    "class / OOP": "class this virtual friend public private protected explicit operator mutable",
    "exception handling": "try catch throw noexcept",
    "memory": "new delete",
    "namespace / template": "namespace using template typename concept requires export",
    "cast": "static_cast dynamic_cast const_cast reinterpret_cast",
    "other": ("alignas alignof asm decltype typeid constexpr consteval constinit "
              "static_assert thread_local co_await co_return co_yield"),
}
# These C keywords are NOT keywords in C++ (they would just be identifiers).
_C_ONLY = set("restrict _Bool _Complex _Imaginary _Atomic _Thread_local _Noreturn "
              "_Alignof _Alignas _Generic _Static_assert".split())


def _flatten(groups: dict) -> dict:
    out = {}
    for group, words in groups.items():
        for w in words.split():
            out[w] = group
    return out


C_KEYWORDS = _flatten(_C_GROUPS)
CPP_KEYWORDS = {w: g for w, g in C_KEYWORDS.items() if w not in _C_ONLY}
CPP_KEYWORDS.update(_flatten(_CPP_ONLY_GROUPS))  # `auto` moves to "data type"

# ----------------------------------------------------------------- operators
_C_OPS3 = frozenset({"<<=", ">>=", "..."})
_C_OPS2 = frozenset({"++", "--", "->", "<<", ">>", "<=", ">=", "==", "!=", "&&", "||",
                     "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^="})
_OPS1 = frozenset("+-*/%=<>!~&|^?:.,;(){}[]")

_CPP_OPS3 = _C_OPS3 | {"->*", "<=>"}
_CPP_OPS2 = _C_OPS2 | {"::", ".*"}

# --------------------------------------------------------------- sample code
C_SAMPLE = """#include <stdio.h>
#define MAX 10

/* sum of the first MAX even numbers */
int main() {
    int sum = 0;
    float avg = 2.5f;
    for (int i = 1; i <= MAX; i++) {
        sum += i * 2;   // running total
    }
    printf("Sum = %d\\n", sum);
    return 0;
}
"""

CPP_SAMPLE = """#include <iostream>
using namespace std;

bool isEven(int n) {
    return n % 2 == 0;
}

int main() {
    int total = 0;
    for (int i = 1; i <= 5; i++) {
        if (isEven(i)) total += i;
    }
    cout << "Even total: " << total << endl;
    return 0;
}
"""

LANGUAGES = {
    "c": LanguageConfig(
        id="c",
        name="C",
        keywords=C_KEYWORDS,
        literal_words={},
        alt_operators=frozenset(),
        ops3=_C_OPS3,
        ops2=_C_OPS2,
        ops1=_OPS1,
        sample=C_SAMPLE,
        notes="C11 subset",
    ),
    "cpp": LanguageConfig(
        id="cpp",
        name="C++",
        keywords=CPP_KEYWORDS,
        literal_words={"true": "boolean", "false": "boolean", "nullptr": "null pointer"},
        alt_operators=frozenset({"and", "or", "not", "xor", "bitand", "bitor", "compl",
                                 "and_eq", "or_eq", "xor_eq", "not_eq"}),
        ops3=_CPP_OPS3,
        ops2=_CPP_OPS2,
        ops1=_OPS1,
        sample=CPP_SAMPLE,
        notes="C++17 subset",
    ),
}


def get_language(lang_id: str) -> LanguageConfig:
    try:
        return LANGUAGES[lang_id.lower()]
    except KeyError:
        raise ValueError(f"Unsupported language '{lang_id}'. Available: {', '.join(LANGUAGES)}")
