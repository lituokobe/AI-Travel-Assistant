"""Built-in travel skills are present and discoverable under skills/."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = PROJECT_ROOT / "skills"

EXPECTED_SKILL_DIRS = [
    "main/compound-travel-package",
    "main/change-of-plans",
    "main/pre-trip-checklist",
    "main/compare-destinations",
    "flights/round-trip-assembler",
    "flights/flexible-date-finder",
    "flights/connection-airport-strategy",
    "hotels/stay-aligned-to-flights",
    "hotels/room-need-translator",
    "car/one-way-multi-day-rental-shaping",
    "activity/day-fit-curator",
    "activity/theme-packs",
]


def test_builtin_skill_md_files_exist():
    missing = []
    for rel in EXPECTED_SKILL_DIRS:
        path = SKILLS_ROOT / rel / "SKILL.md"
        if not path.is_file():
            missing.append(rel)
    assert not missing, f"Missing SKILL.md: {missing}"


def test_skill_frontmatter_has_name_and_description():
    for rel in EXPECTED_SKILL_DIRS:
        text = (SKILLS_ROOT / rel / "SKILL.md").read_text(encoding="utf-8")
        assert text.startswith("---"), rel
        assert "name:" in text.split("---", 2)[1], rel
        assert "description:" in text.split("---", 2)[1], rel
