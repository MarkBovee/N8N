---
applyTo: '**'
---

# Coding Assistant Instructions (Spec-Driven)

The assistant has freedom to design and implement solutions, but must always work like a professional developer:
define expectations, plan steps, implement clean code, and verify results.

---

## Safety Guard

Before proceeding with any task, ensure that the specifications are clear and unambiguous. If there is any room for misinterpretation, ask the user for clarification to obtain the best possible specs.

---

## 🔹 Quick Reference (Checklist)

0. **Task Type** → Determine task type and create branch if new code needed.  
1. **Spec** → Define expected results (what success looks like).  
2. **Risks & Dependencies** → Identify blockers, requirements, and time estimates.  
3. **Plan** → Outline steps and validation points.  
4. **Tasks** → Break down concrete coding tasks.  
5. **Verify Plan** → Confirm plan covers all specs before implementation.  
6. **Implement** → Write full working code (no placeholders).  
7. **Verify** → Self-check that results match the plan.  

---

## Workflow

### 0. Task Type & Branch Setup
- Analyze the user's request to determine task type:
  - **New Feature**: If adding new functionality or significant enhancements
  - **Bug Fix**: If fixing existing issues or simple corrections
  - **Refactor**: If restructuring code without changing behavior
  - **Documentation**: If updating docs or comments
- Create appropriate branch **only if new code will be written**:
  - Feature: `feature/<descriptive-name>`
  - Bug Fix: `fix/<descriptive-name>`
  - Refactor: `refactor/<descriptive-name>`
  - Documentation: `docs/<descriptive-name>`
- Progress tracking is per branch when branches are created; `.github/copilot-progress.md` should not be committed to git

### 1. Spec (Expected Results)
- Start by writing down what the correct outcome should look like.
- Define success in measurable terms (e.g., files downloaded without errors, files exist, files contain content).
- Include performance requirements and success metrics where applicable.
- Consider edge cases and error conditions.
- If the outcome is unclear, ask clarifying questions.

### 2. Risks & Dependencies
- Identify potential blockers, external dependencies, or prerequisites
- Estimate rough time requirements for the task
- Consider resource requirements (APIs, tools, permissions needed)
- Plan for incremental delivery if the task is large
- Define rollback strategy if implementation fails

### 3. Plan (Steps & Checks)
- Outline the logical plan to achieve the expected result.
- Define checkpoints and validation points.
- Include how results will be verified.

### 4. Tasks (Implementation Plan)
- Break the plan into concrete coding tasks.
- Map each task directly to the expected outcome.
- Use the tools for the IDE to display the tasks, todos and progress.

### 5. Plan Verification
- Review the plan against the spec to ensure no requirements were missed
- Confirm all edge cases and validation points are covered
- Include testing strategy (unit tests, integration tests, performance tests)
- Plan for documentation updates if new features or APIs are added
- Consider incremental delivery checkpoints for large features
- If gaps found, revise the plan before proceeding

### 6. Implement (Code / Logic)
- Write full working code with no placeholders.
- Follow professional standards and include basic error handling.
- Only change what is needed; preserve everything else.

### 7. Verify (Self-Check / Test)
- Perform a professional self-check of the code.
- Confirm that the expected results match the plan.
- For tasks like downloading, check that:
  - There are no runtime errors.
  - Files exist after execution.
  - Files are not empty.
  - Content is as expected.
- Include unit tests for new functionality and integration tests where applicable.
- Verify performance impact for performance-sensitive changes.
- If checks cannot be run here, describe how to verify them.

---

## Output Format
Always present work in this order:

1. **Task Type & Branch**  
2. **Spec (Expected Results)**  
3. **Risks & Dependencies**  
4. **Plan (Steps & Validation Points)**  
5. **Tasks (Implementation Breakdown)**  
6. **Plan Verification**  
7. **Code (Full Files or Patches)**  
8. **Verification (Professional Self-Check)**  

Use fenced code blocks with correct language tags.  
For multiple files, provide each file in full.

---

## Clarifications
- If expectations or validations are ambiguous → ask.  
- Do not guess hidden requirements.  
- Keep it light: do not add extras unless explicitly requested.
