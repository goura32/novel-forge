# Placeholder Consistency Report: Prompt Templates vs Implementation

## Summary

Checked all 25 prompt templates in `/mnt/hdd/projects/novel-forge/prompts/` against their implementations in `/mnt/hdd/projects/novel-forge/src/novel_forge/`.

**Key finding:** The most pervasive issue is that `{schema}` is present in almost every prompt template but is NEVER passed by the implementation. Additionally, `{lang}` is passed by implementations but not declared in most templates. Several review prompts have many more placeholders in the template than what the implementation provides.

---

## Detailed Findings Per File

---

### 1. `system.md`
**Placeholders in template:** None  
**Implementation:** `plan.py:106`, `design.py:72`, `scene_writer.py:103,178,209,234` — passes `{"lang": engine._lang}`  
**Status:** ✅ OK (template has no placeholders; the `lang` param is simply ignored)

---

### 2. `chapter_design.md`
**Placeholders in template:** `{series_plan}`, `{volume_number}`, `{volume_title}`, `{volume_premise}`, `{chapter_number}`, `{chapter_title}`, `{chapter_purpose}`, `{previous_chapter_outcome}`, `{previous_volume_summary}`, `{schema}`

**Implementation:** `design.py:132-138`
```python
{"series_plan": series_plan, "volume_number": str(vol_num),
 "chapter_number": str(ch_idx), "chapter_title": ch_data.get("title", ""),
 "chapter_purpose": ch_data.get("purpose", ""),
 "previous_chapter_outcome": prev_chapter_outcome,
 "previous_volume_summary": prev_volume_summary,
 "lang": engine._lang}
```

| Placeholder | Status | Notes |
|---|---|---|
| `{series_plan}` | ✅ Passed | |
| `{volume_number}` | ✅ Passed | |
| `{volume_title}` | ❌ MISSING | Not passed by implementation |
| `{volume_premise}` | ❌ MISSING | Not passed by implementation |
| `{chapter_number}` | ✅ Passed | |
| `{chapter_title}` | ✅ Passed | |
| `{chapter_purpose}` | ✅ Passed | |
| `{previous_chapter_outcome}` | ✅ Passed | |
| `{previous_volume_summary}` | ✅ Passed | |
| `{schema}` | ❌ MISSING | Not passed by implementation |

---

### 3. `chapter_design_revision.md`
**Placeholders in template:** `{current_chapter}`, `{review}`, `{schema}`

**Implementation:** `design.py:145-146`
```python
{"current_chapter": json.dumps(r, ensure_ascii=False), "review": format_review_text(rv)}
```

| Placeholder | Status |
|---|---|
| `{current_chapter}` | ✅ Passed |
| `{review}` | ✅ Passed |
| `{schema}` | ❌ MISSING |

---

### 4. `chapter_design_review.md`
**Placeholders in template:** `{series_plan}`, `{volume_title}`, `{volume_premise}`, `{chapter_number}`, `{chapter_title}`, `{chapter_purpose}`, `{chapter_theme}`, `{chapter_emotional_arc}`, `{foreshadowing_notes}`, `{subplot_notes}`, `{scene_list}`, `{schema}`

**Implementation:** `design.py:259-260`
```python
{"design": text, "lang": engine._lang}
```

| Placeholder | Status |
|---|---|
| `{series_plan}` | ❌ MISSING |
| `{volume_title}` | ❌ MISSING |
| `{volume_premise}` | ❌ MISSING |
| `{chapter_number}` | ❌ MISSING |
| `{chapter_title}` | ❌ MISSING |
| `{chapter_purpose}` | ❌ MISSING |
| `{chapter_theme}` | ❌ MISSING |
| `{chapter_emotional_arc}` | ❌ MISSING |
| `{foreshadowing_notes}` | ❌ MISSING |
| `{subplot_notes}` | ❌ MISSING |
| `{scene_list}` | ❌ MISSING |
| `{schema}` | ❌ MISSING |

⚠️ **CRITICAL:** Only a pre-summary `design` text is passed. All individual field placeholders will remain unrendered.

---

### 5. `volume_design.md`
**Placeholders in template:** `{series_plan}`, `{volume_number}`, `{genre}`, `{previous_design}`, `{schema}`

**Implementation:** `design.py:97-99`
```python
{"series_plan": series_plan, "volume_number": str(vol_num), "genre": genre,
 "previous_design": prev_design, "lang": engine._lang}
```

| Placeholder | Status |
|---|---|
| `{series_plan}` | ✅ Passed |
| `{volume_number}` | ✅ Passed |
| `{genre}` | ✅ Passed |
| `{previous_design}` | ✅ Passed |
| `{schema}` | ❌ MISSING |

---

### 6. `volume_design_revision.md`
**Placeholders in template:** `{current_volume}`, `{review}`, `{series_plan}`, `{previous_design}`, `{schema}`

**Implementation:** `design.py:92-95`
```python
{"current_volume": json.dumps(r, ensure_ascii=False), "review": format_review_text(rv),
 "previous_design": prev_design}
```

| Placeholder | Status |
|---|---|
| `{current_volume}` | ✅ Passed |
| `{review}` | ✅ Passed |
| `{series_plan}` | ❌ MISSING |
| `{previous_design}` | ✅ Passed |
| `{schema}` | ❌ MISSING |

---

### 7. `volume_design_review.md`
**Placeholders in template:** `{design}`, `{schema}`

**Implementation:** `design.py:251-252`
```python
{"design": text, "lang": engine._lang}
```

| Placeholder | Status |
|---|---|
| `{design}` | ✅ Passed |
| `{schema}` | ❌ MISSING |

---

### 8. `scene_design.md`
**Placeholders in template:** `{series_plan}`, `{volume_number}`, `{volume_title}`, `{volume_premise}`, `{chapter_number}`, `{chapter_title}`, `{chapter_purpose}`, `{chapter_theme}`, `{chapter_emotional_arc}`, `{chapter_foreshadowing_notes}`, `{chapter_subplot_notes}`, `{scene_number}`, `{scene_count}`, `{chapter_scene_number}`, `{chapter_scene_count}`, `{previous_outcome}`, `{previous_volume_summary}`, `{schema}`

**Implementation:** `design.py:175-182`
```python
{"series_plan": series_plan, "volume_number": str(vol_num),
 "chapter_number": str(ch_num), "scene_number": str(scene_counter),
 "scene_count": str(est_scenes),
 "chapter_scene_number": str(scene_counter),
 "chapter_scene_count": str(ch_est),
 "previous_outcome": prev_outcome,
 "lang": engine._lang}
```

| Placeholder | Status |
|---|---|
| `{series_plan}` | ✅ Passed |
| `{volume_number}` | ✅ Passed |
| `{volume_title}` | ❌ MISSING |
| `{volume_premise}` | ❌ MISSING |
| `{chapter_number}` | ✅ Passed |
| `{chapter_title}` | ❌ MISSING |
| `{chapter_purpose}` | ❌ MISSING |
| `{chapter_theme}` | ❌ MISSING |
| `{chapter_emotional_arc}` | ❌ MISSING |
| `{chapter_foreshadowing_notes}` | ❌ MISSING |
| `{chapter_subplot_notes}` | ❌ MISSING |
| `{scene_number}` | ✅ Passed |
| `{scene_count}` | ✅ Passed |
| `{chapter_scene_number}` | ✅ Passed |
| `{chapter_scene_count}` | ✅ Passed |
| `{previous_outcome}` | ✅ Passed |
| `{previous_volume_summary}` | ❌ MISSING |
| `{schema}` | ❌ MISSING |

⚠️ **CRITICAL:** 9 of 18 placeholders are missing.

---

### 9. `scene_design_revision.md`
**Placeholders in template:** `{current_scene}`, `{review}`, `{schema}`

**Implementation:** `design.py:190-191`
```python
{"current_scene": json.dumps(r, ensure_ascii=False), "review": format_review_text(rv)}
```

| Placeholder | Status |
|---|---|
| `{current_scene}` | ✅ Passed |
| `{review}` | ✅ Passed |
| `{schema}` | ❌ MISSING |

---

### 10. `scene_design_review.md`
**Placeholders in template:** `{series_plan}`, `{volume_title}`, `{volume_premise}`, `{chapter_title}`, `{chapter_purpose}`, `{scene_title}`, `{scene_goal}`, `{scene_outcome}`, `{scene_conflict}`, `{scene_pov}`, `{scene_characters}`, `{scene_key_events}`, `{scene_setting}`, `{scene_emotional_arc}`, `{previous_outcome}`, `{schema}`

**Implementation:** `design.py:269-270`
```python
{"design": text, "lang": engine._lang}
```

| Placeholder | Status |
|---|---|
| All 16 placeholders | ❌ MISSING |

⚠️ **CRITICAL:** Only a pre-summary `design` text is passed. All individual field placeholders will remain unrendered.

---

### 11. `scene_draft.md`
**Placeholders in template:** `{series_plan}`, `{design}`, `{chapter_title}`, `{chapter_purpose}`, `{scene}`, `{context}`, `{continuity}`, `{subplots}`, `{relationships}`, `{foreshadowing_to_resolve}`, `{schema}`

**Implementation:** `scene_writer.py:104-118`
```python
{
    "series_plan": ctx.get_series_plan_summary_fn(),
    "outline": ctx.get_outline_summary_fn(design_obj),  # ← keyed as "outline" not "design"
    "scene": ctx.get_scene_summary_fn(scene),
    "chapter_title": chapter.title,
    "chapter_purpose": chapter.purpose,
    "context": ctx.build_context_fn(),
    "continuity": ctx.build_continuity_fn(record.scene_number, ctx.vol_num),
    "subplots": self._get_subplots_text(),
    "relationships": self._get_relationships_text(),
    "foreshadowing_to_resolve": self._get_foreshadowing_to_resolve_text(),
    "lang": ctx.lang,
}
```

| Placeholder | Status | Notes |
|---|---|---|
| `{series_plan}` | ✅ Passed | |
| `{design}` | ⚠️ MISMATCH | Implementation passes `outline` instead of `design` |
| `{chapter_title}` | ✅ Passed | |
| `{chapter_purpose}` | ✅ Passed | |
| `{scene}` | ✅ Passed | |
| `{context}` | ✅ Passed | |
| `{continuity}` | ✅ Passed | |
| `{subplots}` | ✅ Passed | |
| `{relationships}` | ✅ Passed | |
| `{foreshadowing_to_resolve}` | ✅ Passed | |
| `{schema}` | ❌ MISSING | |

---

### 12. `scene_revision.md`
**Placeholders in template:** `{scene}`, `{review}`, `{schema}`

**Implementation:** `scene_writer.py:211-217`
```python
{"scene": draft_text, "review": review_text, "lang": lang}
```

| Placeholder | Status |
|---|---|
| `{scene}` | ✅ Passed |
| `{review}` | ✅ Passed |
| `{schema}` | ❌ MISSING |

---

### 13. `scene_review.md`
**Placeholders in template:** `{scene}`, `{design}`, `{context}`, `{subplots}`, `{relationships}`, `{schema}`

**Implementation:** `scene_writer.py:179-188`
```python
{
    "scene": draft_text,
    "outline": ctx.get_outline_summary_fn(design_obj),  # ← keyed as "outline" not "design"
    "context": ctx.build_context_fn(),
    "subplots": self._get_subplots_text(),
    "relationships": self._get_relationships_text(),
    "lang": ctx.lang,
}
```

| Placeholder | Status | Notes |
|---|---|---|
| `{scene}` | ✅ Passed | |
| `{design}` | ⚠️ MISMATCH | Implementation passes `outline` instead of `design` |
| `{context}` | ✅ Passed | |
| `{subplots}` | ✅ Passed | |
| `{relationships}` | ✅ Passed | |
| `{schema}` | ❌ MISSING | |

---

### 14. `scene_summary_and_bible_update.md`
**Placeholders in template:** `{scene}`, `{current_bible}`, `{schema}`

**Implementation:** `scene_writer.py:237-243`
```python
{"scene": draft_text, "current_bible": current_bible_text, "lang": lang}
```

| Placeholder | Status |
|---|---|
| `{scene}` | ✅ Passed |
| `{current_bible}` | ✅ Passed |
| `{schema}` | ❌ MISSING |

---

### 15. `series_plan_concept.md`
**Placeholders in template:** `{keywords}`, `{existing_slugs}`, `{schema}`

**Implementation:** `plan.py:177-179`
```python
{"keywords": keywords, "lang": engine._lang, "existing_slugs": slugs_text}
```

| Placeholder | Status |
|---|---|
| `{keywords}` | ✅ Passed |
| `{existing_slugs}` | ✅ Passed |
| `{schema}` | ❌ MISSING |

---

### 16. `series_plan_concept_revision.md`
**Placeholders in template:** `{current_plan}`, `{review}`, `{schema}`

**Implementation:** `plan.py:215-217`
```python
{"current_plan": json.dumps(core, ensure_ascii=False), "review": review_text}
```

| Placeholder | Status |
|---|---|
| `{current_plan}` | ✅ Passed |
| `{review}` | ✅ Passed |
| `{schema}` | ❌ MISSING |

---

### 17. `series_plan_concept_review.md`
**Placeholders in template:** `{plan_text}`, `{schema}`

**Implementation:** `plan.py:205-206`
```python
{"plan_text": text, "lang": engine._lang}
```

| Placeholder | Status |
|---|---|
| `{plan_text}` | ✅ Passed |
| `{schema}` | ❌ MISSING |

---

### 18. `series_plan_characters.md`
**Placeholders in template:** `{world_summary}`, `{world_rules}`, `{used_names}`, `{schema}`

**Implementation:** `plan.py:224-230`
```python
{
    "world_summary": core.get("world", {}).get("summary", ""),
    "world_rules": "; ".join(core.get("world", {}).get("rules", [])),
    "lang": engine._lang,
    "used_names": ", ".join(sorted(used_names)) if used_names else "（なし）",
}
```

| Placeholder | Status |
|---|---|
| `{world_summary}` | ✅ Passed |
| `{world_rules}` | ✅ Passed |
| `{used_names}` | ✅ Passed |
| `{schema}` | ❌ MISSING |

---

### 19. `series_plan_characters_revision.md`
**Placeholders in template:** `{current_characters}`, `{review}`, `{schema}`

**Implementation:** `plan.py:273-277`
```python
{"current_characters": json.dumps(characters, ensure_ascii=False), "review": review_text}
```

| Placeholder | Status |
|---|---|
| `{current_characters}` | ✅ Passed |
| `{review}` | ✅ Passed |
| `{schema}` | ❌ MISSING |

---

### 20. `series_plan_characters_review.md`
**Placeholders in template:** `{characters}`, `{schema}`

**Implementation:** `plan.py:257-258`
```python
{"characters": text, "lang": engine._lang}
```

| Placeholder | Status |
|---|---|
| `{characters}` | ✅ Passed |
| `{schema}` | ❌ MISSING |

---

### 21. `series_plan_volumes.md`
**Placeholders in template:** `{concept_text}`, `{characters_text}`, `{schema}`

**Implementation:** `plan.py:288-294`
```python
{
    "core_text": f"タイトル: {core.get('title', '')}\n...",
    "characters_text": "\n".join(char_lines),
    "lang": engine._lang,
}
```

| Placeholder | Status |
|---|---|
| `{concept_text}` | ✅ Passed |
| `{characters_text}` | ✅ Passed |
| `{schema}` | ❌ MISSING |

---

### 22. `series_plan_volumes_revision.md`
**Placeholders in template:** `{current_volumes}`, `{review}`, `{schema}`

**Implementation:** `plan.py:335-337`
```python
{"current_volumes": json.dumps(volumes, ensure_ascii=False), "review": review_text}
```

| Placeholder | Status |
|---|---|
| `{current_volumes}` | ✅ Passed |
| `{review}` | ✅ Passed |
| `{schema}` | ❌ MISSING |

---

### 23. `series_plan_volumes_review.md`
**Placeholders in template:** `{volumes}`, `{schema}`

**Implementation:** `plan.py:323-324`
```python
{"volumes": text, "lang": engine._lang}
```

| Placeholder | Status |
|---|---|
| `{volumes}` | ✅ Passed |
| `{schema}` | ❌ MISSING |

---

### 24. `kdp_metadata.md`
**Placeholders in template:** `{series_plan}`, `{design}`, `{schema}`

**Implementation:** ❌ **NOT USED** — No code references `kdp_metadata.md`. The export function `_generate_kdp_metadata()` in `export.py:94` generates metadata directly in Python without using a prompt template.

---

### 25. `cover_prompt.md`
**Placeholders in template:** `{series_plan}`, `{design}`, `{schema}`

**Implementation:** ❌ **NOT USED** — No code references `cover_prompt.md`. This template is never rendered.

---

## Cross-Cutting Issues

### Issue 1: `{schema}` is NEVER passed
**Severity:** HIGH  
**Affected files:** All 21 prompt templates that contain `{schema}`  
**Description:** Every prompt template includes `{schema}` as a placeholder to output the expected JSON schema. However, NO implementation file ever passes a `schema` key in the render variables. The schemas are loaded via `get_schema(...)` in the `complete_json()` call (LLM client level), not injected into the prompt text.  
**Impact:** The literal text `{schema}` will appear in prompts sent to the LLM, which may confuse it or cause it to output schema-like text instead of the actual data.

### Issue 2: `{lang}` is passed but not in most templates
**Severity:** LOW  
**Affected files:** `plan.py`, `design.py`, `scene_writer.py`  
**Description:** The implementation passes `"lang": engine._lang` to most `render()` calls, but `lang` is not a placeholder in most templates (except `system.md` which has no placeholders). This is harmless — the extra key is simply ignored by the renderer.

### Issue 3: Key name mismatch — `design` vs `outline`
**Severity:** MEDIUM  
**Affected files:** `scene_draft.md`, `scene_review.md`  
**Description:** Templates use `{design}` but the implementation passes the value under the key `"outline"` (via `ctx.get_outline_summary_fn(design_obj)`). This means `{design}` will remain unrendered in the prompt.

### Issue 4: Review prompts have extensive unrendered placeholders
**Severity:** HIGH  
**Affected files:** `chapter_design_review.md`, `scene_design_review.md`  
**Description:** These templates have many individual field placeholders (e.g., `{chapter_title}`, `{scene_goal}`, `{foreshadowing_notes}`) but the implementation only passes a single pre-formatted summary string under the key `"design"`. All individual field placeholders will remain as literal `{...}` text in the prompt.

### Issue 5: Orphan templates
**Severity:** MEDIUM  
**Affected files:** `kdp_metadata.md`, `cover_prompt.md`  
**Description:** These templates exist but are never rendered by any code. They may be intended for future use or manual CLI workflows.

---

## Summary Table

| Template | Placeholders | Passed | Missing | Status |
|---|---|---|---|---|
| `system.md` | 0 | 0 | 0 | ✅ |
| `chapter_design.md` | 10 | 8 | 2 | ⚠️ |
| `chapter_design_revision.md` | 3 | 2 | 1 | ⚠️ |
| `chapter_design_review.md` | 12 | 1 | 11 | 🔴 |
| `volume_design.md` | 5 | 4 | 1 | ⚠️ |
| `volume_design_revision.md` | 5 | 3 | 2 | ⚠️ |
| `volume_design_review.md` | 2 | 1 | 1 | ⚠️ |
| `scene_design.md` | 18 | 9 | 9 | 🔴 |
| `scene_design_revision.md` | 3 | 2 | 1 | ⚠️ |
| `scene_design_review.md` | 16 | 1 | 15 | 🔴 |
| `scene_draft.md` | 11 | 10 | 1 | ⚠️ (key mismatch) |
| `scene_revision.md` | 3 | 2 | 1 | ⚠️ |
| `scene_review.md` | 6 | 5 | 1 | ⚠️ (key mismatch) |
| `scene_summary_and_bible_update.md` | 3 | 2 | 1 | ⚠️ |
| `series_plan_concept.md` | 3 | 2 | 1 | ⚠️ |
| `series_plan_concept_revision.md` | 3 | 2 | 1 | ⚠️ |
| `series_plan_concept_review.md` | 2 | 1 | 1 | ⚠️ |
| `series_plan_characters.md` | 4 | 3 | 1 | ⚠️ |
| `series_plan_characters_revision.md` | 3 | 2 | 1 | ⚠️ |
| `series_plan_characters_review.md` | 2 | 1 | 1 | ⚠️ |
| `series_plan_volumes.md` | 3 | 2 | 1 | ⚠️ |
| `series_plan_volumes_revision.md` | 3 | 2 | 1 | ⚠️ |
| `series_plan_volumes_review.md` | 2 | 1 | 1 | ⚠️ |
| `kdp_metadata.md` | 3 | 0 | 3 | 🔴 (orphan) |
| `cover_prompt.md` | 3 | 0 | 3 | 🔴 (orphan) |
