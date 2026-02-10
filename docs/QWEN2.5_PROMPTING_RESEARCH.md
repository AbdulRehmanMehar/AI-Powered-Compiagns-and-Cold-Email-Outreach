# Qwen 2.5:7b Prompting Best Practices Research

**Date:** February 10, 2026  
**Model:** qwen2.5:7b (via Ollama)  
**Current Issue:** Emails too short (22-30 words vs 45-75 target), missing company names

---

## 🔬 Research Summary

### Model Capabilities (from Official Docs)

**Qwen 2.5:7b-Instruct** has the following strengths:
- **Instruction Following:** "More resilient to the diversity of system prompts, enhancing role-play implementation"
- **Long Text Generation:** Can generate over 8K tokens
- **Structured Output:** Excels at JSON generation
- **Context Length:** 128K tokens (though we're using 32K default in config)
- **Multilingual:** 29+ languages

**Key Insight from Docs:**
> "Qwen2.5 brings significant improvements in instruction following... More resilient to the diversity of system prompts"

This means Qwen should be BETTER at following our detailed instructions than Groq models, yet our tests show it's producing overly concise emails.

---

## 🚨 Current Test Results Analysis

From `test_ollama_leadgenjay.py`:

| Email | Word Count | Score | Missing Company Name | Other Issues |
|-------|-----------|-------|---------------------|--------------|
| #1 (Sarah) | 22 words | 85/100 | ❌ DataFlow AI | Too short, no pain point |
| #2 (Mike) | 28 words | 95/100 | ❌ MediSync | Too short |
| #3 (Alex) | 30 words | 95/100 | ❌ BuildTrack | Too short |

**Average:** 27 words (vs 45-75 target)

**What's Working:**
- ✅ No em dashes
- ✅ Soft CTAs ("thoughts?")
- ✅ Specific numbers in case studies
- ✅ Curiosity-first openers
- ✅ Subject lines (2 words)

**What's Failing:**
- ❌ Word count 40% below minimum threshold
- ❌ Company names not mentioned (0/3 tests)
- ❌ Emails feel robotic due to brevity

---

## 🔍 Root Cause Analysis

### 1. **Model Behavior Pattern**

Looking at the actual emails generated:

```
hey sarah, quick one.

are you guys still doing manual testing manually?

helped a healthtech startup HIPAA-compliant launch in 8 weeks.
thoughts?
```

**Pattern Detected:**
- Qwen is interpreting "under 75 words" as "be ultra-concise"
- It's prioritizing brevity OVER completeness
- It's treating each line as separate sentence fragments rather than flowing prose

### 2. **Prompt Interpretation**

From our current prompts in `email_generator.py` (lines 1400-1600):

```python
system_prompt = f"""You are LeadGenJay writing a cold email.

Your 4-LINE STRUCTURE:
Line 1 (preview text): {suggested_opener}
Line 2 (poke the bear): Ask a SPECIFIC question about their pain
Line 3 (social proof): {company_hint} → {case_study.get('result')} in {case_study.get('timeline')}
Line 4 (soft CTA): {suggested_cta}

RULES:
- Under 75 words total
- Use their company name ({company})
- ...
```

**Issue:** Qwen is interpreting "4-LINE" literally as 4 short fragments, not 4 complete sentences.

### 3. **Comparison with Groq Behavior**

Groq models (llama-3.3-70b-versatile) tend to:
- Generate verbose responses by default
- Need constraining to stay under 75 words
- Naturally include more context

Qwen 2.5 tends to:
- Generate concise responses by default
- Interpret word limits as strict ceilings
- Prioritize efficiency over elaboration

---

## 💡 Recommended Prompt Optimizations

### **Fix #1: Explicit Word Count Requirements**

**Current (vague):**
```
- Under 75 words total
```

**Optimized:**
```
CRITICAL WORD COUNT REQUIREMENTS:
- MINIMUM 50 words, TARGET 55-60 words, MAXIMUM 75 words
- If your email is under 50 words, ADD more details and context
- Each line should be a COMPLETE SENTENCE, not a fragment
```

### **Fix #2: Force Company Name Inclusion**

**Current (buried in rules):**
```
- Use their company name ({company})
```

**Optimized:**
```
MANDATORY PERSONALIZATION:
- You MUST mention "{company}" by name in the email body
- Example: "curious how {company} is handling X..."
- Example: "been thinking about {company}'s approach to Y..."
- DO NOT skip the company name - this is non-negotiable
```

### **Fix #3: Structure as Flowing Paragraphs, Not Lines**

**Current (encourages fragments):**
```
Line 1 (preview text): {suggested_opener}
Line 2 (poke the bear): Ask a SPECIFIC question
Line 3 (social proof): Case study
Line 4 (soft CTA): {suggested_cta}
```

**Optimized:**
```
PARAGRAPH STRUCTURE (flowing conversation, not bullet points):

Paragraph 1 (2-3 sentences, ~20 words):
Start with: {suggested_opener}
Then mention {company} and their specific situation.

Paragraph 2 (2 sentences, ~25 words):
Ask about their pain point AND reference the case study result.
Example: "are you facing [pain]? we helped {company_hint} achieve {result} in {timeline}."

Paragraph 3 (1 sentence, ~10 words):
Soft CTA: {suggested_cta}
```

### **Fix #4: Add Examples to System Prompt**

Qwen 2.5 documentation emphasizes it's better at following examples than abstract rules.

**Add to system prompt:**
```python
EXAMPLE GOOD EMAIL (58 words):

hey mike, quick one.

is MediSync's team stuck maintaining stuff instead of building new features? that seems to be the pattern with most healthtech companies right now.

we helped another healthtech startup launch their HIPAA-compliant platform in 8 weeks instead of 6 months. cut their compliance overhead by 60%.

worth a quick chat?

---

EXAMPLE BAD EMAIL (too short, 22 words):

hey mike, quick one.

are you stuck maintaining stuff?

helped a startup launch in 8 weeks.
thoughts?

^^ This is TOO SHORT. Add more context and mention company name!
```

### **Fix #5: Temperature & Parameter Tuning**

**Current settings** (from `_call_llm`):
- `temperature=0.7` (default for email generation)
- No explicit `max_tokens` set (defaults to Ollama's limit)

**Qwen-specific optimization:**

According to Hugging Face docs, Qwen 2.5 works best with:
- **Temperature 0.6-0.7** for creative tasks (we're good here)
- **top_p: 0.8-0.95** (not currently set)
- **min_p: 0.05** (prevents too-short responses)

```python
# In email_generator.py _call_llm() method
if self.provider == "ollama":
    response = self.client.chat.completions.create(
        model=self.model,
        messages=messages,
        temperature=temperature,
        top_p=0.9,           # ADD THIS
        min_p=0.05,          # ADD THIS - prevents ultra-short responses
        max_tokens=500,      # ADD THIS - ensure space for 75 words
    )
```

### **Fix #6: Two-Pass Generation Strategy**

For critical emails, use Qwen's strength in following instructions:

**Pass 1:** Generate email draft
**Pass 2:** Review and expand if too short

```python
# After generating email
if len(email_body.split()) < 50:
    expansion_prompt = f"""This email is too short ({len(email_body.split())} words).
    
Original email:
{email_body}

Expand it to 55-60 words by:
1. Adding {company} company name if missing
2. Adding more specific details about the pain point
3. Making the case study reference more concrete

Keep the same tone and structure, just add necessary detail."""
    
    expanded_email = self._call_llm(expansion_prompt, "", temperature=0.5)
```

---

## 🎯 Recommended Implementation Plan

### **Phase 1: Quick Wins (30 minutes)**

1. Update system prompt with explicit word count requirements
2. Add MANDATORY company name rule
3. Add good/bad email examples to prompt

**Expected impact:** +15 words per email, 80% company name inclusion

### **Phase 2: Parameter Tuning (15 minutes)**

1. Add `top_p=0.9` and `min_p=0.05` to Ollama calls
2. Set explicit `max_tokens=500`

**Expected impact:** More consistent word counts, fewer ultra-short emails

### **Phase 3: Two-Pass Strategy (1 hour)**

1. Implement expansion pass for emails under 50 words
2. Add self-correction for missing company names

**Expected impact:** 95%+ emails in 50-75 word range

---

## 📊 Validation Test Plan

After implementing fixes, re-run `test_ollama_leadgenjay.py` and measure:

**Target Metrics:**
- ✅ Average word count: 50-60 words (currently 27)
- ✅ Company name inclusion: 90%+ (currently 0%)
- ✅ LeadGenJay score: 90%+ (currently 91.7% - maintain)
- ✅ No regression on em dashes, CTAs, subject lines

**Success Criteria:**
- 3/3 emails between 50-75 words
- 3/3 emails mention company name
- Average score ≥ 90/100

---

## 🔗 References

1. **Qwen 2.5 Official Blog:** https://qwenlm.github.io/blog/qwen2.5/
   - "Significant improvements in instruction following"
   - "More resilient to diversity of system prompts"

2. **Hugging Face Model Card:** https://huggingface.co/Qwen/Qwen2.5-7B-Instruct
   - System prompt structure examples
   - Temperature/parameter recommendations

3. **LeadGenJay Framework:** docs/secret-90-page-cold-email-strategy.txt
   - "First sentence is preview text - don't reveal pitch"
   - "50-60 words ideal, 75 max"
   - "Must reference company specifically"

4. **Current Test Results:** tests/ollama_leadgenjay_test_results.json
   - Actual email outputs showing patterns
   - Evaluation criteria scoring

---

## 🚀 Next Steps

1. **Review this document** with Abdul Rehman
2. **Implement Phase 1 fixes** to email_generator.py
3. **Run test suite** to validate improvements
4. **Deploy to production** if metrics improve
5. **Monitor first 100 emails** for quality

---

**Author:** GitHub Copilot  
**Reviewed By:** [Pending]  
**Status:** Draft - Awaiting Implementation
