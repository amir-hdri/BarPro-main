"""
Parser to convert Persian number words to standard digits representation.
Supports numbers from 10,000 to 99,999 (which is the typical range of UTCMS captchas).
"""

WORDS_MAP = {
    "یک": 1,
    "یکی": 1,
    "دو": 2,
    "سه": 3,
    "چهار": 4,
    "پنج": 5,
    "شش": 6,
    "هفت": 7,
    "هشت": 8,
    "نه": 9,
    "ده": 10,
    "یازده": 11,
    "دوازده": 12,
    "سیزده": 13,
    "چهارده": 14,
    "پانزده": 15,
    "شانزده": 16,
    "هفده": 17,
    "هجده": 18,
    "نوزده": 19,
    "بیست": 20,
    "سی": 30,
    "چهل": 40,
    "پنجاه": 50,
    "شصت": 60,
    "هفتاد": 70,
    "هشتاد": 80,
    "نود": 90,
    "صد": 100,
    "یکصد": 100,
    "دویست": 200,
    "سیصد": 300,
    "چهارصد": 400,
    "پانصد": 500,
    "پنجصد": 500,
    "ششصد": 600,
    "هفتصد": 700,
    "هشتصد": 800,
    "نهصد": 900,
}

TYPOS_MAP = {
    "نوت": "نه",
    "هک": "یک",
    "شنصت": "شصت",
    "پنح": "پنج",
    "پنحاه": "پنجاه",
    "هزارت": "هزار",
    "هزا": "هزار",
    "شص": "شصت",
    "دویص": "دویست",
    "هفتص": "هفتصد",
    "هشتص": "هشتصد",
    "یکص": "یک",
    "هشاد": "هشتاد",
    "هفر": "هفت",
    "چهر": "چهار",
    "سیص": "سیصد",
    "چهارص": "چهارصد",
    "پانص": "پانصد",
    "نهص": "نهصد",
    "شاصت": "شصت",
}


def persian_words_to_number(text: str) -> str:
    """
    Converts a Persian word-based representation of a number to a digit string.
    Example: "هفتاد و نه هزار و هشتصد و شصت و نه" -> "79869"
    """
    if not text:
        return ""

    # Standardize spaces and remove conjunctions
    text = text.replace("‌", " ").replace("-", " ").strip()
    parts = [p.strip() for p in text.split(" ") if p.strip() and p.strip() != "و"]

    total = 0
    temp_sum = 0
    for part in parts:
        # Correct common OCR typos
        if part in TYPOS_MAP:
            part = TYPOS_MAP[part]

        if part == "هزار":
            if temp_sum == 0:
                temp_sum = 1
            total += temp_sum * 1000
            temp_sum = 0
        elif part in WORDS_MAP:
            temp_sum += WORDS_MAP[part]

    total += temp_sum
    return str(total)


ones = ["", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه"]
teens = ["ده", "یازده", "دوازده", "سیزده", "چهارده", "پانزده", "شانزده", "هفده", "هجده", "نوزده"]
tens = ["", "", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود"]
hundreds = ["", "صد", "دویست", "سیصد", "چهارصد", "پانصد", "ششصد", "هفتصد", "هشتصد", "نهصد"]


def parse_under_1000(n: int) -> str:
    if n == 0:
        return ""
    parts = []
    h = n // 100
    remainder = n % 100
    if h > 0:
        parts.append(hundreds[h])
    if remainder > 0:
        if 10 <= remainder < 20:
            parts.append(teens[remainder - 10])
        else:
            t = remainder // 10
            u = remainder % 10
            if t > 0:
                parts.append(tens[t])
            if u > 0:
                parts.append(ones[u])
    return " و ".join([p for p in parts if p])


def num_to_persian_words(num: int) -> str:
    if num == 0:
        return "صفر"
    parts = []
    thousands = num // 1000
    remainder = num % 1000
    if thousands > 0:
        parts.append(parse_under_1000(thousands) + " هزار")
    if remainder > 0:
        parts.append(parse_under_1000(remainder))
    return " و ".join(parts)


if __name__ == "__main__":
    # Test cases
    test_cases = [
        ("هفتاد و نه هزار و هشتصد و شصت و نه", "79869"),
        ("هشتاد و شش هزار و نهصد و هفتاد و هشت", "86978"),
        ("بیست و سه هزار و دویست و بیست و دو", "23222"),
        ("شصت و نه هزار و نهصد و پنجاه و یک", "69951"),
        ("چهل و هفت هزار و هشتصد و بیست و شش", "47826"),
        ("ده هزار", "10000"),
        ("نود و نه هزار و نهصد و نود و نه", "99999"),
    ]

    success = True
    for words, expected in test_cases:
        actual = persian_words_to_number(words)
        if actual != expected:
            print(f"❌ Failed: '{words}' -> expected '{expected}', got '{actual}'")
            success = False
        else:
            print(f"✅ Passed: '{words}' -> '{actual}'")

    # Test num_to_persian_words
    print("\nTesting num_to_persian_words:")
    for words, expected in test_cases:
        val = int(expected)
        actual = num_to_persian_words(val)
        if actual != words:
            print(f"❌ Failed: {val} -> expected '{words}', got '{actual}'")
            success = False
        else:
            print(f"✅ Passed: {val} -> '{actual}'")

    if success:
        print("\n🎉 All tests passed!")
