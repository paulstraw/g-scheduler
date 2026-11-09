import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent / "skills" / "g-scheduler"


class SkillMetadataTest(unittest.TestCase):
    def test_frontmatter_has_name_and_description(self):
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"), "SKILL.md must start with YAML frontmatter")
        header = text.split("---\n", 2)[1]
        fields = dict(line.split(":", 1) for line in header.splitlines() if ":" in line)
        self.assertEqual(fields.get("name", "").strip(), SKILL_DIR.name)
        self.assertTrue(fields.get("description", "").strip())


if __name__ == "__main__":
    unittest.main()
