import pytest
from pdfshrink.sizes import parse_size, format_size, describe_size

KO = 1024
MO = 1024 * 1024


@pytest.mark.parametrize("text,expected", [
    ("200", 200 * KO),          # a bare number means Ko
    ("200 Ko", 200 * KO),
    ("200ko", 200 * KO),
    ("200 KB", 200 * KO),
    ("200kb", 200 * KO),
    ("200 K", 200 * KO),
    ("1,5 Mo", int(1.5 * MO)),  # French decimal comma
    ("1.5MB", int(1.5 * MO)),
    ("0,5 mo", int(0.5 * MO)),
    ("  200   ko  ", 200 * KO),
])
def test_parse_accepts(text, expected):
    assert parse_size(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "abc", "200 Go", "-5 Ko", "0", "Ko", "1,2,3 Ko"])
def test_parse_rejects(text):
    with pytest.raises(ValueError):
        parse_size(text)


def test_format_size_uses_narrow_space():
    assert format_size(1648 * KO) == "1 648 Ko"
    assert format_size(199 * KO) == "199 Ko"


def test_describe_size_picks_unit():
    assert describe_size(200 * KO) == "200 Ko"
    assert describe_size(int(1.5 * MO)) == "1,5 Mo"
    assert describe_size(2 * MO) == "2 Mo"
