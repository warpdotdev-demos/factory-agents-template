#!/usr/bin/env python3
"""Unit tests for the Jira provider's markdown <-> ADF conversion.

Loads `scripts/jira` as a module and exercises the pure converter functions
(`markdown_to_adf`, `adf_to_text`) directly -- no network, no Jira credentials.
"""
import importlib.util
import os
import unittest
from importlib.machinery import SourceFileLoader

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JIRA_SCRIPT = os.path.join(REPO_ROOT, "scripts", "jira")


def _load_script(name, path):
    spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


jira = _load_script("jira_provider", JIRA_SCRIPT)


class MarkdownToAdfTest(unittest.TestCase):
    def test_empty_document(self):
        self.assertEqual(
            jira.markdown_to_adf(""),
            {"type": "doc", "version": 1, "content": []},
        )
        self.assertEqual(jira.markdown_to_adf(None)["content"], [])

    def test_paragraphs_split_on_blank_lines(self):
        doc = jira.markdown_to_adf("first line\nstill first\n\nsecond")
        self.assertEqual([b["type"] for b in doc["content"]], ["paragraph", "paragraph"])
        self.assertEqual(
            doc["content"][0]["content"],
            [{"type": "text", "text": "first line still first"}],
        )
        self.assertEqual(
            doc["content"][1]["content"],
            [{"type": "text", "text": "second"}],
        )

    def test_heading_levels(self):
        doc = jira.markdown_to_adf("## Rollout plan")
        (heading,) = doc["content"]
        self.assertEqual(heading["type"], "heading")
        self.assertEqual(heading["attrs"], {"level": 2})
        self.assertEqual(heading["content"], [{"type": "text", "text": "Rollout plan"}])

    def test_bold_italic_code_marks(self):
        doc = jira.markdown_to_adf("a **bold** and *ital* and `code` end")
        (para,) = doc["content"]
        self.assertEqual(
            para["content"],
            [
                {"type": "text", "text": "a "},
                {"type": "text", "text": "bold", "marks": [{"type": "strong"}]},
                {"type": "text", "text": " and "},
                {"type": "text", "text": "ital", "marks": [{"type": "em"}]},
                {"type": "text", "text": " and "},
                {"type": "text", "text": "code", "marks": [{"type": "code"}]},
                {"type": "text", "text": " end"},
            ],
        )

    def test_inline_code_protects_contents(self):
        doc = jira.markdown_to_adf("run `a_b_c` now")
        (para,) = doc["content"]
        self.assertEqual(
            para["content"][1],
            {"type": "text", "text": "a_b_c", "marks": [{"type": "code"}]},
        )

    def test_link(self):
        doc = jira.markdown_to_adf("see [the docs](https://example.com/x) now")
        (para,) = doc["content"]
        self.assertEqual(
            para["content"][1],
            {
                "type": "text",
                "text": "the docs",
                "marks": [{"type": "link", "attrs": {"href": "https://example.com/x"}}],
            },
        )

    def test_bare_url_becomes_link(self):
        doc = jira.markdown_to_adf("see https://example.com/x now")
        (para,) = doc["content"]
        self.assertEqual(
            para["content"],
            [
                {"type": "text", "text": "see "},
                {
                    "type": "text",
                    "text": "https://example.com/x",
                    "marks": [{"type": "link", "attrs": {"href": "https://example.com/x"}}],
                },
                {"type": "text", "text": " now"},
            ],
        )

    def test_bare_url_excludes_trailing_punctuation(self):
        doc = jira.markdown_to_adf("docs at https://example.com/x.")
        (para,) = doc["content"]
        self.assertEqual(
            para["content"][1],
            {
                "type": "text",
                "text": "https://example.com/x",
                "marks": [{"type": "link", "attrs": {"href": "https://example.com/x"}}],
            },
        )
        self.assertEqual(para["content"][2], {"type": "text", "text": "."})

    def test_bare_url_in_parens(self):
        doc = jira.markdown_to_adf("(see https://example.com/x)")
        (para,) = doc["content"]
        self.assertEqual(
            para["content"][1],
            {
                "type": "text",
                "text": "https://example.com/x",
                "marks": [{"type": "link", "attrs": {"href": "https://example.com/x"}}],
            },
        )
        self.assertEqual(para["content"][2], {"type": "text", "text": ")"})

    def test_bare_url_with_underscores_not_italicized(self):
        url = "https://example.com/a_b_c"
        doc = jira.markdown_to_adf(f"see {url} now")
        (para,) = doc["content"]
        self.assertEqual(
            para["content"][1],
            {
                "type": "text",
                "text": url,
                "marks": [{"type": "link", "attrs": {"href": url}}],
            },
        )

    def test_autolink_angle_brackets(self):
        doc = jira.markdown_to_adf("see <https://example.com/x> now")
        (para,) = doc["content"]
        self.assertEqual(
            para["content"][1],
            {
                "type": "text",
                "text": "https://example.com/x",
                "marks": [{"type": "link", "attrs": {"href": "https://example.com/x"}}],
            },
        )

    def test_url_inside_inline_code_stays_code(self):
        doc = jira.markdown_to_adf("run `curl https://example.com` now")
        (para,) = doc["content"]
        self.assertEqual(
            para["content"][1],
            {"type": "text", "text": "curl https://example.com", "marks": [{"type": "code"}]},
        )

    def test_url_inside_markdown_link_not_double_linked(self):
        doc = jira.markdown_to_adf("[docs](https://example.com/x)")
        (para,) = doc["content"]
        self.assertEqual(
            para["content"],
            [
                {
                    "type": "text",
                    "text": "docs",
                    "marks": [{"type": "link", "attrs": {"href": "https://example.com/x"}}],
                }
            ],
        )

    def test_mention_token_becomes_mention_node(self):
        doc = jira.markdown_to_adf(
            "[~accountid:712020:00000000-0000-0000-0000-000000000000] please review"
        )
        (para,) = doc["content"]
        self.assertEqual(
            para["content"],
            [
                {
                    "type": "mention",
                    "attrs": {"id": "712020:00000000-0000-0000-0000-000000000000"},
                },
                {"type": "text", "text": " please review"},
            ],
        )

    def test_mention_token_mid_sentence(self):
        doc = jira.markdown_to_adf("cc [~accountid:abc123] for visibility")
        (para,) = doc["content"]
        self.assertEqual(
            para["content"],
            [
                {"type": "text", "text": "cc "},
                {"type": "mention", "attrs": {"id": "abc123"}},
                {"type": "text", "text": " for visibility"},
            ],
        )

    def test_mention_token_inside_inline_code_stays_code(self):
        doc = jira.markdown_to_adf("write `[~accountid:abc123]` in the body")
        (para,) = doc["content"]
        self.assertEqual(
            para["content"][1],
            {"type": "text", "text": "[~accountid:abc123]", "marks": [{"type": "code"}]},
        )

    def test_bullet_list(self):
        doc = jira.markdown_to_adf("- one\n- two **bold**")
        (lst,) = doc["content"]
        self.assertEqual(lst["type"], "bulletList")
        self.assertEqual(len(lst["content"]), 2)
        first = lst["content"][0]
        self.assertEqual(first["type"], "listItem")
        self.assertEqual(
            first["content"],
            [{"type": "paragraph", "content": [{"type": "text", "text": "one"}]}],
        )
        second_para = lst["content"][1]["content"][0]
        self.assertIn(
            {"type": "text", "text": "bold", "marks": [{"type": "strong"}]},
            second_para["content"],
        )

    def test_ordered_list(self):
        doc = jira.markdown_to_adf("1. first\n2. second")
        (lst,) = doc["content"]
        self.assertEqual(lst["type"], "orderedList")
        self.assertEqual(len(lst["content"]), 2)

    def test_fenced_code_block_with_language(self):
        doc = jira.markdown_to_adf("```python\nprint('**not bold**')\nx = 1\n```")
        (block,) = doc["content"]
        self.assertEqual(block["type"], "codeBlock")
        self.assertEqual(block["attrs"], {"language": "python"})
        # Code text is verbatim: no inline-mark parsing inside fences.
        self.assertEqual(
            block["content"],
            [{"type": "text", "text": "print('**not bold**')\nx = 1"}],
        )

    def test_fenced_code_block_without_language(self):
        doc = jira.markdown_to_adf("```\nfoo\n```")
        (block,) = doc["content"]
        self.assertEqual(block["type"], "codeBlock")
        self.assertNotIn("attrs", block)
        self.assertEqual(block["content"], [{"type": "text", "text": "foo"}])

    def test_mixed_document_block_order(self):
        md = "# Title\n\npara text\n\n- a\n- b\n\n```\ncode\n```"
        doc = jira.markdown_to_adf(md)
        self.assertEqual(
            [b["type"] for b in doc["content"]],
            ["heading", "paragraph", "bulletList", "codeBlock"],
        )


class AdfToTextTest(unittest.TestCase):
    def test_non_document_input(self):
        self.assertEqual(jira.adf_to_text(None), "")
        self.assertEqual(jira.adf_to_text("nope"), "")

    def test_paragraph_marks_roundtrip(self):
        md = "a **bold** and *ital* and `code` end"
        self.assertEqual(jira.adf_to_text(jira.markdown_to_adf(md)), md)

    def test_link_roundtrip(self):
        md = "see [the docs](https://example.com/x) now"
        self.assertEqual(jira.adf_to_text(jira.markdown_to_adf(md)), md)

    def test_bare_url_roundtrip(self):
        md = "see https://example.com/x now"
        self.assertEqual(jira.adf_to_text(jira.markdown_to_adf(md)), md)

    def test_mention_roundtrip_without_text_attr(self):
        md = "cc [~accountid:abc123] for visibility"
        self.assertEqual(jira.adf_to_text(jira.markdown_to_adf(md)), md)

    def test_mention_with_text_attr_reads_as_display_text(self):
        doc = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "mention", "attrs": {"id": "abc123", "text": "@Alex"}},
                        {"type": "text", "text": " done"},
                    ],
                }
            ],
        }
        self.assertEqual(jira.adf_to_text(doc), "@Alex done")

    def test_heading_list_code_roundtrip(self):
        md = "# Title\n\npara text\n\n- one\n- two\n\n```python\nx = 1\n```"
        self.assertEqual(jira.adf_to_text(jira.markdown_to_adf(md)), md)

    def test_ordered_list_numbering(self):
        md = "1. first\n2. second"
        self.assertEqual(jira.adf_to_text(jira.markdown_to_adf(md)), md)

    def test_hard_break(self):
        doc = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "a"},
                        {"type": "hardBreak"},
                        {"type": "text", "text": "b"},
                    ],
                }
            ],
        }
        self.assertEqual(jira.adf_to_text(doc), "a\nb")

    def test_unknown_block_renders_children(self):
        doc = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "panel",
                    "attrs": {"panelType": "info"},
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "note"}]}
                    ],
                }
            ],
        }
        self.assertEqual(jira.adf_to_text(doc), "note")


if __name__ == "__main__":
    unittest.main()
